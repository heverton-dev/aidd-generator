#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PHASE 8: Implementador com Verificação
aidd-project-generator v2.1

Fecha o gap entre "scaffold AIDD" e "projeto funcional": gera código
real a partir do design da Fase 3 (design.scripts, com pseudocódigo) e
do stack recomendado pela Fase 2, escreve testes reais, RODA os testes
de verdade via subprocess, e corrige iterativamente (reenviando o
traceback real ao LLM) até passar ou esgotar tentativas.

Coordenação de Schema Compartilhado:
Quando o projeto envolve armazenamento (SQLite, etc.), deriva previamente
um schema SQL DDL único e centralizado para TODOS os scripts e testes,
evitando que chamadas isoladas de LLM inventem schemas incompatíveis
(causa raiz diagnosticada na prova com LLM real de 2026-08-30).

Teste de Integração Cross-Script:
Gera um teste de integração de ponta a ponta (tests/test_integracao.py)
que exercita os múltiplos scripts encadeados, garantindo que a composição
real entre eles funcione (não apenas testes unitários isolados).

Executa 5 gates de validação (I1-I5)
Gera _phase_08_index.json com auditoria completa

Tokens: variável (chamadas reais de LLM, incluindo correções) — nunca fabricado
"""

import sys
import os
import re
import json
import ast
import subprocess
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, Dict, List, Any, Tuple

sys.path.insert(0, str(Path(__file__).parent))
from utils_modelo import detectar_modelo_harness, obter_nome_amigavel_modelo
from utils_delegacao import solicitar_llm, extrair_json_resposta, LLMNaoConfiguradoException

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

MAX_TENTATIVAS_POR_SCRIPT = 3
TIMEOUT_PYTEST_SEGUNDOS = 60

PROMPT_GERAR_SCHEMA_COMPARTILHADO = """Defina o SCHEMA SQLite DDL unificado para o projeto. Todos os módulos usarão EXATAMENTE este schema.

PROJETO: {ideia}
STACK: {stack}
SCRIPTS:
{scripts_info}

Regras: CREATE TABLE IF NOT EXISTS, todas as tabelas/colunas/PK/FK necessárias, nomes autoexplicativos, idempotente em SQLite.

SAÍDA (APENAS o JSON abaixo, nada mais, sem markdown/code fence):
{{"schema_sql":"<DDL completo>","tabelas":["t1","t2"]}}
"""

PROMPT_GERAR_TESTE_INTEGRACAO = """Gere UM teste de integração pytest completo encadeando os múltiplos scripts do projeto em um fluxo real de ponta a ponta.

PROJETO: {ideia}
STACK: {stack}
{secao_schema}

SCRIPTS IMPLEMENTADOS:
{scripts_info}

Regras:
- O teste DEVE integrar e encadear os scripts/módulos gerados, usando o retorno ou saída de uma função como entrada de outra (ex: cadastrar/criar registro -> usar id/retorno retornado -> executar ação dependente -> consultar/validar estado final no banco ou serviço).
- NÃO faça apenas testes isolados ou mock de funções internas; exercite o fluxo real que um usuário ou CLI percorreria.
- Imports diretos (ex: from modulo import ...). src/ já está no PYTHONPATH.
- SQLite/banco: use banco em memória ':memory:' ou tmp_path. Inicialize as tabelas no banco de teste antes das operações e ative PRAGMA foreign_keys = ON.
- NUNCA use subprocess.run nos testes (chame funções e classes Python diretamente).
- CONTRATO: chame apenas funções/classes que os scripts realmente definem.
- Se o teste salva e relê JSON, normalize tipos antes de comparar (tupla→lista, None preservado).

SAÍDA (APENAS o JSON abaixo, nada mais, sem markdown/code fence):
{{"teste":"<código Python do teste pytest completo>","caminho_teste":"test_integracao.py"}}
"""

PROMPT_IMPLEMENTAR_SCRIPT = """Implemente o script Python abaixo. Código real, funcional, sem TODO/pass.

PROJETO: {ideia}
STACK: {stack}
{secao_schema}
SCRIPT: {nome}
RESPONSABILIDADE: {responsabilidade}
PSEUDOCÓDIGO: {pseudocodigo}

Regras:
- Código: funções/classes testáveis. Teste: suite pytest (test_*), import direto (from {modulo} import). src/ já no PYTHONPATH.
- CONTRATO: o teste só pode chamar funções que o código realmente define ou importa. NUNCA assuma funções auxiliares (ex: criar_autor, criar_item) sem defini-las no código.
- SQLite: use schema acima, função criar_tabela(conn) com DDL, conn=None opcional, NUNCA conn.close() se recebido.
- FK: se o schema tem FOREIGN KEY, execute PRAGMA foreign_keys = ON logo após criar/abrir a conexão. Valide a existência do registro pai antes de INSERT dependente (SELECT 1 FROM ... WHERE id = ?), retornando erro claro (ex: ValueError) se não existir — NUNCA silencie FK inválida nem reporte sucesso falso.
- Testes: fixture com DDL + PRAGMA foreign_keys=ON antes de INSERT/SELECT, :memory: ou tmp_path (nunca os.remove). Para scripts com FK: inclua pelo menos 1 teste de referência inválida/ID inexistente e verifique que retorna erro.
- Datas SQLite: armazenadas como texto ('YYYY-MM-DD'). Ao recuperar, converta explicitamente para datetime.date (date.fromisoformat(val) if isinstance(val, str) else val) antes de subtrair datas.
- JSON round-trip: se o teste salva e relê JSON, normalize tipos antes de comparar (tupla→lista, None preservado). Use json.loads(json.dumps(x, default=str)) no dado esperado.
- Streak: data_referencia opcional, check-ins duplicados na mesma data não duplicam streak.
- Sem subprocess.run nos testes. UTF-8 no console (sys.stdout.reconfigure se win32).

SAÍDA (APENAS o JSON abaixo, nada mais, sem markdown/code fence):
{{"codigo":"<código Python completo>","teste":"<teste pytest completo>","caminho_relativo":"{caminho_sugerido}","caminho_teste":"{caminho_teste_sugerido}"}}
"""

PROMPT_CORRIGIR_SCRIPT = """Corrija o código/teste que falhou no pytest.

{secao_schema}
MÓDULO: {modulo}

CÓDIGO:
{codigo}

TESTE:
{teste}

ERROS (apenas falhas):
{erro}

Regras: import direto (from {modulo} import), nomes coerentes, schema DDL + PRAGMA foreign_keys = ON na fixture antes de INSERT/SELECT, conn=None opcional, NUNCA conn.close() se recebido, :memory: ou tmp_path (nunca os.remove), data_referencia opcional para streak. Se houver FOREIGN KEY: valide existência do registro pai antes de operação dependente, retorne erro claro se não existir, garanta ao menos 1 teste de referência inválida/ID inexistente. Se houver erro de data (str vs date): converta com date.fromisoformat antes de subtrair. Se houver erro de assert de contagem: confira que o valor esperado é matematicamente exato (N+1, não fixo).

SAÍDA (APENAS o JSON, nada mais, sem markdown/code fence):
{{"codigo":"<código corrigido>","teste":"<teste corrigido>","caminho_relativo":"...","caminho_teste":"..."}}
"""


# =============================================================================
# GATES DE VALIDAÇÃO (I1-I5)
# =============================================================================

class Gate:
    """Estrutura de resultado de gate"""
    def __init__(self, gate_id: str, descricao: str, passou: bool, detalhes: str):
        self.gate_id = gate_id
        self.descricao = descricao
        self.passou = passou
        self.detalhes = detalhes

    def to_dict(self):
        return {
            'gate_id': self.gate_id,
            'descricao': self.descricao,
            'status': 'PASSOU' if self.passou else 'FALHOU',
            'detalhes': self.detalhes
        }


class ValidadorGatesPhase8:
    """Valida a implementação real (não a intenção) da Fase 8"""

    @staticmethod
    def executar_todos(pasta_projeto: Path, scripts_implementados: List[Dict],
                        resultado_pytest: Optional[Dict],
                        resultado_integracao: Optional[Dict] = None,
                        teste_integracao_gerado: bool = False) -> Tuple[List[Gate], bool]:
        gates = [
            ValidadorGatesPhase8._gate_i1_scripts_implementados(pasta_projeto, scripts_implementados),
            ValidadorGatesPhase8._gate_i2_testes_coletam(resultado_pytest),
            ValidadorGatesPhase8._gate_i3_testes_passam(resultado_pytest),
            ValidadorGatesPhase8._gate_i4_cli_executa(pasta_projeto),
            ValidadorGatesPhase8._gate_i5_teste_integracao(resultado_integracao, teste_integracao_gerado),
        ]
        return gates, all(g.passou for g in gates)

    @staticmethod
    def _gate_i1_scripts_implementados(pasta_projeto: Path, scripts_implementados: List[Dict]) -> Gate:
        """I1: Todo script do design tem arquivo real em src/"""
        total = len(scripts_implementados)
        criados = sum(
            1 for s in scripts_implementados
            if (pasta_projeto / 'src' / s.get('caminho_relativo', '')).exists()
        )
        passou = total > 0 and criados == total
        return Gate('I1_scripts_implementados',
                   'Validar todos os scripts do design foram implementados',
                   passou, f"{criados}/{total} scripts implementados em disco")

    @staticmethod
    def _gate_i2_testes_coletam(resultado_pytest: Optional[Dict]) -> Gate:
        """I2: pytest consegue coletar os testes sem erro de import"""
        if resultado_pytest is None:
            return Gate('I2_testes_coletam', 'Validar pytest coleta sem erro', False, 'pytest nunca rodou')
        passou = not resultado_pytest.get('erro_coleta', True)
        detalhes = 'Coleta OK' if passou else 'Erro de coleta (ver detalhes_coleta no index)'
        return Gate('I2_testes_coletam', 'Validar pytest coleta sem erro', passou, detalhes)

    @staticmethod
    def _gate_i3_testes_passam(resultado_pytest: Optional[Dict]) -> Gate:
        """I3: 100% dos testes reais passam — nunca estimado"""
        if resultado_pytest is None:
            return Gate('I3_testes_passam', 'Validar 100% dos testes passam', False, 'pytest nunca rodou')
        total = resultado_pytest.get('total', 0)
        passaram = resultado_pytest.get('passaram', 0)
        falharam = resultado_pytest.get('falharam', 0)
        erros = resultado_pytest.get('erros', 0)
        passou = total > 0 and falharam == 0 and erros == 0 and passaram == total
        detalhes_falha = f" ({falharam} falha(s), {erros} erro(s))" if (falharam > 0 or erros > 0) else ""
        return Gate('I3_testes_passam', 'Validar 100% dos testes passam', passou,
                   f"{passaram}/{total} testes passando{detalhes_falha}")

    @staticmethod
    def _gate_i4_cli_executa(pasta_projeto: Path) -> Gate:
        """I4: se houver CLI entry-point (main.py), roda smoke-test real"""
        main_py = pasta_projeto / 'main.py'
        if not main_py.exists():
            return Gate('I4_cli_executa', 'Validar CLI executa smoke-test', True,
                       'Sem main.py — gate não aplicável, não bloqueia')
        try:
            resultado = subprocess.run(
                [sys.executable, str(main_py), '--help'],
                cwd=str(pasta_projeto), capture_output=True, timeout=10
            )
            passou = resultado.returncode == 0
            return Gate('I4_cli_executa', 'Validar CLI executa smoke-test', passou,
                       f"main.py --help retornou exit code {resultado.returncode}")
        except Exception as e:
            return Gate('I4_cli_executa', 'Validar CLI executa smoke-test', False, f"Erro ao rodar: {e}")

    @staticmethod
    def _gate_i5_teste_integracao(resultado_integracao: Optional[Dict], teste_gerado: bool) -> Gate:
        """I5: Teste de integração entre scripts gerado e passando"""
        if not teste_gerado or resultado_integracao is None:
            return Gate('I5_teste_integracao',
                       'Validar teste de integração entre scripts',
                       False, 'Teste de integração não gerado ou não executado')
        if resultado_integracao.get('erro_coleta', False):
            return Gate('I5_teste_integracao',
                       'Validar teste de integração entre scripts',
                       False, 'Erro de coleta no teste de integração')
        passaram = resultado_integracao.get('passaram', 0)
        falharam = resultado_integracao.get('falharam', 0)
        erros = resultado_integracao.get('erros', 0)
        total = resultado_integracao.get('total', 0)
        passou = total > 0 and falharam == 0 and erros == 0 and passaram == total
        detalhes_falha = f" ({falharam} falha(s), {erros} erro(s))" if (falharam > 0 or erros > 0) else ""
        return Gate('I5_teste_integracao',
                   'Validar teste de integração entre scripts',
                   passou, f"{passaram}/{total} teste(s) de integração passando{detalhes_falha}")


# =============================================================================
# IMPLEMENTADOR PRINCIPAL
# =============================================================================

class ImplementadorFase8:
    """Orquestrador da Fase 8: código real + verificação real + correção real + schema unificado"""

    def __init__(self, pasta_projeto: Path, model_override: str = None):
        self.pasta_projeto = Path(pasta_projeto)
        self.pasta_cache = self.pasta_projeto / '.aidd' / 'cache'
        self.modelo_harness = detectar_modelo_harness()
        self.modelo_final = model_override or self.modelo_harness
        self.modelo_nome_amigavel = obter_nome_amigavel_modelo(self.modelo_final)
        self._tokens_totais = 0
        self.schema_compartilhado: Optional[str] = None

    def executar(self, ideia_projeto: str, analise: Dict, design: Dict) -> Optional[Dict]:
        """Executa pipeline completo da Fase 8"""
        print(f"\n🛠️  PHASE 8: Implementador com Verificação")
        print(f"   Modelo: {self.modelo_nome_amigavel}")
        print(f"   {'-' * 60}")

        tempo_inicio = datetime.now()
        stack = analise.get('stack_recomendado', {}) if analise else {}
        scripts_design = (design.get('design', {}) if design else {}).get('scripts', [])

        if not scripts_design:
            print("   ❌ Nenhum script no design — nada para implementar (Fase 3 rodou?)")
            return None

        # Coordenação de Schema Compartilhado
        if self._precisa_schema_compartilhado(stack, scripts_design):
            print("\n   🗄️  Derivando schema de banco de dados unificado para todos os scripts...")
            self.schema_compartilhado = self._gerar_schema_compartilhado(ideia_projeto, stack, scripts_design)
            if self.schema_compartilhado:
                print("   ✓ Schema compartilhado derivado com sucesso.")
            else:
                print("   ⚠️ Não foi possível derivar schema centralizado, prosseguindo com heurística padrão.")

        scripts_implementados = []
        for script_spec in scripts_design:
            nome = script_spec.get('nome', 'sem_nome')
            print(f"\n   🤖 Implementando {nome}...")
            resultado = self._implementar_script_com_verificacao(ideia_projeto, stack, script_spec)
            if resultado is None:
                print(f"   ❌ Falha ao obter implementação de {nome} (LLM não respondeu)")
                return None
            status = "✓" if resultado.get('tentativas', 1) and not resultado.get('falhou_apos_tentativas') else "⚠️"
            print(f"   {status} {nome}: {resultado.get('tentativas', 1)} tentativa(s)")
            scripts_implementados.append(resultado)

        print(f"\n   🔗 Gerando teste de integração entre scripts...")
        teste_integracao_gerado, resultado_integracao = self._gerar_e_escrever_teste_integracao(
            ideia_projeto, stack, scripts_implementados
        )
        if teste_integracao_gerado and resultado_integracao:
            status_int = "✓" if resultado_integracao.get('passaram', 0) > 0 and resultado_integracao.get('falharam', 0) == 0 and resultado_integracao.get('erros', 0) == 0 and not resultado_integracao.get('erro_coleta', False) else "✗"
            print(f"   {status_int} Teste de integração: {resultado_integracao.get('passaram', 0)}/{resultado_integracao.get('total', 0)} passando")

        print(f"\n✅ Rodando suite de testes completa...")
        resultado_pytest = self._rodar_pytest(caminho_relativo=None)

        gates, todos_passaram = ValidadorGatesPhase8.executar_todos(
            self.pasta_projeto, scripts_implementados, resultado_pytest,
            resultado_integracao=resultado_integracao,
            teste_integracao_gerado=teste_integracao_gerado
        )
        for gate in gates:
            icon = "✓" if gate.passou else "✗"
            print(f"   {icon} {gate.gate_id}: {gate.detalhes}")

        tempo_execucao = (datetime.now() - tempo_inicio).total_seconds()
        index = self._gerar_index(
            scripts_implementados, resultado_pytest, gates, tempo_execucao,
            teste_integracao_gerado=teste_integracao_gerado,
            resultado_integracao=resultado_integracao
        )

        path_index = self.pasta_cache / '_phase_08_index.json'
        path_index.parent.mkdir(parents=True, exist_ok=True)
        with open(path_index, 'w', encoding='utf-8') as f:
            json.dump(index, f, indent=2, ensure_ascii=False)

        if not todos_passaram:
            print(f"\n❌ FASE FALHOU: Gates não passaram")
            return None

        print(f"\n{'=' * 60}")
        print(f"✅ PHASE 8 COMPLETO — {len(scripts_implementados)} script(s) implementados e verificados")
        print(f"   Tokens (reais): {self._tokens_totais}")
        print(f"{'=' * 60}\n")

        return index

    def _precisa_schema_compartilhado(self, stack: Dict, scripts_design: List[Dict]) -> bool:
        """Detecta se o projeto envolve persistência SQLite ou banco de dados compartilhado"""
        if stack:
            banco_val = str(stack.get('banco', '')).strip().lower()
            if banco_val and banco_val not in ['none', 'null', 'nenhum', 'sem', 'false', 'n/a', '{}', '']:
                return True
            for k, v in stack.items():
                v_str = str(v).lower()
                if v_str in ['none', 'null', 'nenhum', 'sem', 'false', 'n/a', '{}', '']:
                    continue
                if any(termo in v_str for termo in ['sqlite', 'database', 'sql', 'storage']):
                    return True

        for s in scripts_design:
            texto = (s.get('nome', '') + ' ' + s.get('responsabilidade', '') + ' ' + s.get('pseudocodigo', '')).lower()
            if any(termo in texto for termo in ['sqlite', 'tabela', 'table', 'checkin', 'habito', 'create table', 'insert into', 'banco de dados']):
                return True

        return False

    def _gerar_schema_compartilhado(self, ideia: str, stack: Dict, scripts_design: List[Dict]) -> Optional[str]:
        """Gera um schema SQL SQLite unificado e consistente para todo o projeto"""
        scripts_info = "\n".join([
            f"- {s.get('nome')}: {s.get('responsabilidade')} | Pseudocódigo: {s.get('pseudocodigo')}"
            for s in scripts_design
        ])

        prompt = PROMPT_GERAR_SCHEMA_COMPARTILHADO.format(
            ideia=ideia,
            stack=json.dumps(stack, ensure_ascii=False),
            scripts_info=scripts_info,
        )
        contexto = "Phase 8: Arquiteto de Banco de Dados / Schema Centralizado"

        try:
            resposta = solicitar_llm(
                prompt=prompt, contexto=contexto, fase="phase_08_schema",
                modelo=os.getenv('LLM_MODEL', self.modelo_final), timeout_delegacao=60
            )
        except LLMNaoConfiguradoException as e:
            print(f"   ❌ {e.mensagem_usuario}")
            return None
        if resposta is None:
            return None

        self._tokens_totais += resposta.get('tokens_consumidos') or 0
        try:
            dados = extrair_json_resposta(resposta['conteudo'])
            if isinstance(dados, dict) and 'schema_sql' in dados:
                return str(dados['schema_sql']).strip()
            elif isinstance(dados, str):
                return dados.strip()
        except Exception as e:
            print(f"   ⚠️ Erro ao extrair schema compartilhado ({e})")

        return None

    def _montar_secao_schema(self) -> str:
        """Monta o bloco de instruções de schema compartilhado para injeção no prompt"""
        if not self.schema_compartilhado:
            return ""

        return (
            "SCHEMA DE BANCO DE DADOS UNIFICADO DO PROJETO (OBRIGATÓRIO):\n"
            "Todos os scripts e testes DEVEM usar EXATAMENTE a estrutura e nomes de tabelas/colunas abaixo:\n"
            "```sql\n"
            f"{self.schema_compartilhado}\n"
            "```\n"
            "Atenção: NUNCA invente tabelas ou colunas diferentes deste schema unificado."
        )

    def _gerar_e_escrever_teste_integracao(
        self, ideia: str, stack: Dict, scripts_implementados: List[Dict]
    ) -> Tuple[bool, Optional[Dict]]:
        """Gera e escreve teste de integração que encadeia os scripts implementados."""
        scripts_info_linhas = []
        for s in scripts_implementados:
            caminho = s.get('caminho_relativo', '')
            cod = s.get('codigo', '')
            scripts_info_linhas.append(f"MÓDULO: src/{caminho}\nCÓDIGO:\n{cod}\n")
        scripts_info = "\n".join(scripts_info_linhas)

        secao_schema = self._montar_secao_schema()
        prompt = PROMPT_GERAR_TESTE_INTEGRACAO.format(
            ideia=ideia,
            stack=json.dumps(stack, ensure_ascii=False),
            secao_schema=secao_schema,
            scripts_info=scripts_info,
        )
        contexto = "Phase 8: Teste de Integração / Fluxo End-to-End entre Scripts"

        try:
            resposta = solicitar_llm(
                prompt=prompt, contexto=contexto, fase="phase_08_integracao",
                modelo=os.getenv('LLM_MODEL', self.modelo_final), timeout_delegacao=60
            )
        except LLMNaoConfiguradoException as e:
            print(f"   ❌ {e.mensagem_usuario}")
            return False, None
        if resposta is None:
            print("   ⚠️ LLM não respondeu para o teste de integração")
            return False, None

        self._tokens_totais += resposta.get('tokens_consumidos') or 0
        try:
            dados = extrair_json_resposta(resposta['conteudo'])
            if not isinstance(dados, dict) or 'teste' not in dados:
                print(f"   ⚠️ Resposta sem chave 'teste': {resposta.get('conteudo', '')[:150]}...")
                return False, None

            caminho_teste = dados.get('caminho_teste') or 'test_integracao.py'
            nome_teste = Path(str(caminho_teste).replace('\\', '/')).name
            if 'integracao' not in nome_teste and 'integration' not in nome_teste:
                nome_teste = 'test_integracao.py'
            else:
                if not nome_teste.startswith('test_'):
                    nome_teste = f"test_{nome_teste}"
                if not nome_teste.endswith('.py'):
                    nome_teste += '.py'

            # Escreve arquivo de teste de integração
            arq_teste = self.pasta_projeto / 'tests' / nome_teste
            arq_teste.parent.mkdir(parents=True, exist_ok=True)
            arq_teste.write_text(dados['teste'], encoding='utf-8')
            print(f"   ✓ Teste de integração gerado e salvo em tests/{nome_teste}")

            # Roda pytest no teste de integração
            resultado_integracao = self._rodar_pytest(caminho_relativo=nome_teste)
            return True, resultado_integracao
        except Exception as e:
            print(f"   ⚠️ Erro ao processar teste de integração ({e})")
            return False, None

    def _implementar_script_com_verificacao(self, ideia: str, stack: Dict, script_spec: Dict) -> Optional[Dict]:
        """Implementa 1 script, roda o teste real, corrige até passar (ou esgota tentativas)"""
        nome_raw = script_spec.get('nome', 'script.py')
        nome_base = Path(str(nome_raw).replace('\\', '/')).name
        if nome_base.endswith('.py'):
            modulo = nome_base[:-3]
            caminho_sugerido = nome_base
        else:
            modulo = nome_base
            caminho_sugerido = f"{nome_base}.py"
        caminho_teste_sugerido = f"test_{caminho_sugerido}"

        # Retomada inteligente: se script e teste já existem em disco e passam no pytest
        arq_codigo = self.pasta_projeto / 'src' / caminho_sugerido
        arq_teste = self.pasta_projeto / 'tests' / caminho_teste_sugerido
        if arq_codigo.exists() and arq_teste.exists():
            resultado_existente = self._rodar_pytest(caminho_relativo=caminho_teste_sugerido)
            if resultado_existente['passaram'] > 0 and resultado_existente['falharam'] == 0 and resultado_existente['erros'] == 0 and not resultado_existente['erro_coleta']:
                print(f"   ✓ {caminho_sugerido} já implementado e com testes passando ({resultado_existente['passaram']} testes)")
                return {
                    'codigo': arq_codigo.read_text(encoding='utf-8'),
                    'teste': arq_teste.read_text(encoding='utf-8'),
                    'caminho_relativo': caminho_sugerido,
                    'caminho_teste': caminho_teste_sugerido,
                    'tentativas': 1,
                    'reutilizado_existente': True
                }

        secao_schema = self._montar_secao_schema()

        prompt = PROMPT_IMPLEMENTAR_SCRIPT.format(
            ideia=ideia,
            stack=json.dumps(stack, ensure_ascii=False),
            secao_schema=secao_schema,
            nome=nome_raw,
            responsabilidade=script_spec.get('responsabilidade', ''),
            pseudocodigo=script_spec.get('pseudocodigo', ''),
            modulo=modulo,
            caminho_sugerido=caminho_sugerido,
            caminho_teste_sugerido=caminho_teste_sugerido,
        )
        contexto = f"Phase 8: Implementador. Script: {script_spec.get('nome')}"

        try:
            resposta = solicitar_llm(
                prompt=prompt, contexto=contexto, fase="phase_08",
                modelo=os.getenv('LLM_MODEL', self.modelo_final), timeout_delegacao=60
            )
        except LLMNaoConfiguradoException as e:
            print(f"   ❌ {e.mensagem_usuario}")
            return None
        if resposta is None:
            return None

        self._tokens_totais += resposta.get('tokens_consumidos') or 0
        try:
            impl = extrair_json_resposta(resposta['conteudo'])
            if not isinstance(impl, dict) or 'codigo' not in impl or 'teste' not in impl:
                print(f"   ⚠️ Resposta sem chaves 'codigo'/'teste': {resposta.get('conteudo', '')[:150]}...")
                return None
        except Exception as e:
            print(f"   ⚠️ Erro parse JSON ({e}): {resposta.get('conteudo', '')[:150]}...")
            return None

        # Normalização rigorosa de caminhos (fixados para este script em todas as tentativas)
        caminho_relativo = self._normalizar_caminho_codigo(
            impl.get('caminho_relativo'), caminho_sugerido
        )
        caminho_teste = self._normalizar_caminho_teste(
            impl.get('caminho_teste'), caminho_relativo
        )
        impl['caminho_relativo'] = caminho_relativo
        impl['caminho_teste'] = caminho_teste

        for tentativa in range(1, MAX_TENTATIVAS_POR_SCRIPT + 1):
            # GAP 1: validação AST do contrato antes de rodar pytest
            problema_contrato = self._validar_contrato_ast(impl.get('codigo', ''), impl.get('teste', ''), modulo)
            if problema_contrato:
                print(f"   ⚠️ Contrato AST: {problema_contrato[:100]}...")
                # Tratar como falha real — pular pytest e ir direto para correção
                erro_compacto = problema_contrato
                if tentativa == MAX_TENTATIVAS_POR_SCRIPT:
                    impl['tentativas'] = tentativa
                    impl['falhou_apos_tentativas'] = True
                    return impl
                # Cair direto no fluxo de correção abaixo
            else:
                self._escrever_implementacao(impl)
                resultado_teste = self._rodar_pytest(caminho_relativo=impl.get('caminho_teste'))

                if resultado_teste['passaram'] > 0 and resultado_teste['falharam'] == 0 and resultado_teste['erros'] == 0 and not resultado_teste['erro_coleta']:
                    impl['tentativas'] = tentativa
                    return impl

                if tentativa == MAX_TENTATIVAS_POR_SCRIPT:
                    impl['tentativas'] = tentativa
                    impl['falhou_apos_tentativas'] = True
                    return impl

                # Economia de tokens: enviar apenas falhas do pytest, não saída completa
                erro_compacto = self._extrair_falhas_pytest(resultado_teste.get('saida', ''))
            prompt_fix = PROMPT_CORRIGIR_SCRIPT.format(
                secao_schema=secao_schema,
                codigo=impl.get('codigo', ''),
                teste=impl.get('teste', ''),
                erro=erro_compacto,
                modulo=modulo,
            )
            try:
                resposta_fix = solicitar_llm(
                    prompt=prompt_fix, contexto=contexto, fase="phase_08_fix",
                    modelo=os.getenv('LLM_MODEL', self.modelo_final), timeout_delegacao=60
                )
            except LLMNaoConfiguradoException as e:
                print(f"   ❌ {e.mensagem_usuario}")
                impl['tentativas'] = tentativa
                impl['falhou_apos_tentativas'] = True
                return impl
            if resposta_fix is None:
                impl['tentativas'] = tentativa
                impl['falhou_apos_tentativas'] = True
                return impl

            self._tokens_totais += resposta_fix.get('tokens_consumidos') or 0
            try:
                impl_corrigido = extrair_json_resposta(resposta_fix['conteudo'])
                if isinstance(impl_corrigido, dict) and 'codigo' in impl_corrigido and 'teste' in impl_corrigido:
                    impl_corrigido['caminho_relativo'] = caminho_relativo
                    impl_corrigido['caminho_teste'] = caminho_teste
                    impl = impl_corrigido
                else:
                    impl['tentativas'] = tentativa
                    impl['falhou_apos_tentativas'] = True
                    return impl
            except Exception:
                impl['tentativas'] = tentativa
                impl['falhou_apos_tentativas'] = True
                return impl

    @staticmethod
    def _normalizar_caminho_codigo(caminho: Optional[str], nome_padrao: str = "script.py") -> str:
        c = str(caminho or nome_padrao).replace('\\', '/').strip()
        while c.startswith('src/'):
            c = c[4:]
        if not c.endswith('.py'):
            c += '.py'
        return c

    @staticmethod
    def _normalizar_caminho_teste(caminho: Optional[str], caminho_codigo: str) -> str:
        nome_codigo = Path(caminho_codigo).name
        nome_teste_esperado = f"test_{nome_codigo}"
        c = str(caminho or '').replace('\\', '/').strip()
        while c.startswith('tests/') or c.startswith('test/'):
            if c.startswith('tests/'):
                c = c[6:]
            elif c.startswith('test/'):
                c = c[5:]
        nome_base = Path(c).name if c else ''
        if not nome_base or nome_base in ['test_tests.py', 'test_teste.py', 'test_script.py', 'test_.py']:
            return nome_teste_esperado
        if not nome_base.startswith('test_'):
            nome_base = f"test_{nome_base}"
        if not nome_base.endswith('.py'):
            nome_base += '.py'
        return nome_base

    def _escrever_implementacao(self, impl: Dict):
        """Escreve código + teste em disco de verdade em UTF-8"""
        caminho_codigo = self.pasta_projeto / 'src' / impl['caminho_relativo']
        caminho_codigo.parent.mkdir(parents=True, exist_ok=True)
        caminho_codigo.write_text(impl['codigo'], encoding='utf-8')

        init_src = self.pasta_projeto / 'src' / '__init__.py'
        if not init_src.exists():
            init_src.write_text('', encoding='utf-8')

        init_parent = caminho_codigo.parent / '__init__.py'
        if not init_parent.exists():
            init_parent.write_text('', encoding='utf-8')

        caminho_teste = self.pasta_projeto / 'tests' / impl['caminho_teste']
        caminho_teste.parent.mkdir(parents=True, exist_ok=True)
        caminho_teste.write_text(impl['teste'], encoding='utf-8')

        init_tests = self.pasta_projeto / 'tests' / '__init__.py'
        if not init_tests.exists():
            init_tests.write_text('', encoding='utf-8')

    @staticmethod
    def _extrair_falhas_pytest(saida_completa: str) -> str:
        """Extrai apenas seções de falha/erro do pytest, descartando testes que passaram.
        Reduz ~3000 chars de saída completa para ~500 chars de apenas erros relevantes."""
        linhas = saida_completa.split('\n')
        falhas = []
        capturando = False
        for linha in linhas:
            # Captura blocos de FAILED, ERROR, e short test summary
            if 'FAILED' in linha or 'ERROR' in linha or 'short test summary' in linha.lower():
                capturando = True
            elif linha.startswith('=') and ('passed' in linha or 'failed' in linha or 'error' in linha):
                # Linha de resumo final — sempre incluir
                falhas.append(linha.strip())
                capturando = False
                continue
            elif capturando and linha.startswith('PASSED'):
                capturando = False
                continue
            if capturando:
                falhas.append(linha)
        resultado = '\n'.join(falhas).strip()
        # Fallback: se não conseguiu extrair nada específico, pegar últimos 800 chars
        if not resultado or len(resultado) < 50:
            return saida_completa[-800:]
        return resultado[:1500]  # Cap em 1500 chars (vs 3000 original)

    @staticmethod
    def _validar_contrato_ast(codigo: str, teste: str, modulo: str = '') -> Optional[str]:
        """Valida mecanicamente que o teste só chama funções que o código define/exporta.
        Retorna None se OK, ou string descrevendo o problema (para injeção no prompt de correção).
        Usa AST parsing — não depende de rodar o código."""
        try:
            arvore_codigo = ast.parse(codigo)
            arvore_teste = ast.parse(teste)
        except SyntaxError:
            return None  # SyntaxError será pego pelo pytest, não duplicar aqui

        # Coletar nomes definidos no código: funções, classes, imports, e métodos por classe
        nomes_definidos = set()
        metodos_por_classe = {}  # nome_classe -> {metodo1, metodo2, ...}
        autoimports_suspeitos = set()  # nomes importados de um modulo com o MESMO nome (from X import X)
        for node in ast.walk(arvore_codigo):
            if isinstance(node, ast.FunctionDef):
                nomes_definidos.add(node.name)
            elif isinstance(node, ast.ClassDef):
                nomes_definidos.add(node.name)
                metodos = set()
                for item in ast.walk(node):
                    if isinstance(item, ast.FunctionDef):
                        metodos.add(item.name)
                        nomes_definidos.add(item.name)
                metodos_por_classe[node.name] = metodos
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    nomes_definidos.add(alias.asname or alias.name)
            elif isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    nome_importado = alias.asname or alias.name
                    # Autoimportação (from <proprio_modulo> import qualquer_nome):
                    # sintaticamente parece um import valido mas nao prova que a funcao existe de
                    # verdade em lugar nenhum — achado real: LLM as vezes gera 'from coletar_dados
                    # import coletar_habitos, coletar_checkins' dentro do proprio coletar_dados.py,
                    # sem nunca definir essas funcoes (so escreve o corpo do teste em ambos os lados).
                    # Cobre tanto 'from X import X' quanto 'from X import Y, Z' onde X e o modulo atual.
                    if node.module and modulo and node.module == modulo:
                        autoimports_suspeitos.add(nome_importado)
                        continue
                    if node.module and node.module == alias.name:
                        autoimports_suspeitos.add(nome_importado)
                        continue
                    nomes_definidos.add(nome_importado)

        # Nomes built-in e do pytest que sempre existem
        builtins_permitidos = {
            'print', 'len', 'range', 'int', 'str', 'float', 'list', 'dict',
            'set', 'tuple', 'bool', 'type', 'isinstance', 'hasattr', 'getattr',
            'setattr', 'enumerate', 'zip', 'map', 'filter', 'sorted', 'reversed',
            'min', 'max', 'sum', 'abs', 'round', 'any', 'all', 'open', 'super',
            'property', 'staticmethod', 'classmethod', 'Exception', 'ValueError',
            'TypeError', 'KeyError', 'IndexError', 'AttributeError', 'RuntimeError',
            'NotImplementedError', 'OSError', 'IOError', 'FileNotFoundError',
            'datetime', 'date', 'timedelta', 'Path', 'os', 'sys', 'json',
            'sqlite3', 're', 'math', 'time', 'uuid', 'copy', 'pytest',
            'fixture', 'tmp_path', 'monkeypatch',
            'TestClient', 'BaseModel', 'Field',
        }

        # Funções de teste pytest definidas no próprio teste
        nomes_teste_pytest = set()
        for node in ast.walk(arvore_teste):
            if isinstance(node, ast.FunctionDef):
                nomes_teste_pytest.add(node.name)

        # Mapear variáveis do teste para classes (ex: repo = LivroRepo() → repo é LivroRepo)
        vars_com_classe = {}  # var_name -> class_name
        for node in ast.walk(arvore_teste):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and isinstance(node.value, ast.Call):
                        if isinstance(node.value.func, ast.Name) and node.value.func.id in metodos_por_classe:
                            vars_com_classe[target.id] = node.value.func.id

        # Coletar nomes chamados no teste e verificar contrato
        nomes_faltando = []
        for node in ast.walk(arvore_teste):
            if not isinstance(node, ast.Call):
                continue
            if isinstance(node.func, ast.Name):
                # Chamada direta: funcao()
                nome = node.func.id
                if nome not in builtins_permitidos and nome not in nomes_definidos and nome not in nomes_teste_pytest:
                    if not nome.startswith('_') and nome not in ('conn', 'db_path', 'tmp_path'):
                        nomes_faltando.append(nome)
            elif isinstance(node.func, ast.Attribute):
                # Chamada método: obj.metodo()
                if isinstance(node.func.value, ast.Name):
                    var_nome = node.func.value.id
                    metodo = node.func.attr
                    if var_nome in vars_com_classe:
                        classe = vars_com_classe[var_nome]
                        if classe in metodos_por_classe and metodo not in metodos_por_classe[classe]:
                            nomes_faltando.append(f"{var_nome}.{metodo}() (método de {classe})")

        if nomes_faltando:
            aviso_autoimport = ""
            faltando_via_autoimport = set(nomes_faltando) & autoimports_suspeitos
            if faltando_via_autoimport:
                aviso_autoimport = (
                    f" ATENÇÃO: {', '.join(sorted(faltando_via_autoimport))} aparece(m) como "
                    f"'from <modulo> import {sorted(faltando_via_autoimport)[0]}' DENTRO DO PRÓPRIO "
                    f"módulo — isso é uma autoimportação inválida (o módulo não pode importar de si "
                    f"mesmo). A função/classe precisa ser DEFINIDA de verdade no código, não importada."
                )
            return (
                f"CONTRATO QUEBRADO: o teste chama funções que o código NÃO define: "
                f"{', '.join(sorted(set(nomes_faltando)))}.{aviso_autoimport} "
                f"Defina essas funções no código OU remova as chamadas do teste. "
                f"Funções disponíveis no código: {', '.join(sorted(nomes_definidos)[:20])}"
            )
        return None

    def _rodar_pytest(self, caminho_relativo: Optional[str]) -> Dict:
        """Roda pytest de verdade via subprocess com UTF-8 estrito — nunca estima resultado"""
        alvo = f'tests/{Path(caminho_relativo).name}' if caminho_relativo else 'tests/'
        env = {
            **os.environ,
            'PYTHONIOENCODING': 'utf-8',
            'PYTHONUTF8': '1',
            'PYTHONPATH': str(self.pasta_projeto / 'src') + os.pathsep + os.environ.get('PYTHONPATH', '')
        }

        try:
            resultado = subprocess.run(
                [sys.executable, '-m', 'pytest', alvo, '-v'],
                cwd=str(self.pasta_projeto), capture_output=True, text=True,
                encoding='utf-8', errors='replace', timeout=TIMEOUT_PYTEST_SEGUNDOS,
                env=env
            )
            saida = resultado.stdout + resultado.stderr
            erro_coleta = 'error' in saida.lower() and (
                'modulenotfounderror' in saida.lower() or 'error collecting' in saida.lower()
                or 'errors during collection' in saida.lower()
                or 'indentationerror' in saida.lower() or 'syntaxerror' in saida.lower()
            )

            m_passou = re.search(r'(\d+) passed', saida)
            m_falhou = re.search(r'(\d+) failed', saida)
            m_erros = re.search(r'(\d+) error', saida)
            passaram = int(m_passou.group(1)) if m_passou else 0
            falharam = int(m_falhou.group(1)) if m_falhou else 0
            erros = int(m_erros.group(1)) if m_erros else 0
            total_falhas = falharam + erros
            total = passaram + total_falhas

            if total == 0 and resultado.returncode != 0:
                erro_coleta = True

            return {
                'passaram': passaram, 'falharam': falharam, 'erros': erros, 'total': total,
                'erro_coleta': erro_coleta, 'detalhes_coleta': saida[-2000:],
                'saida': saida[-3000:], 'returncode': resultado.returncode,
            }
        except Exception as e:
            return {
                'passaram': 0, 'falharam': 0, 'erros': 1, 'total': 0, 'erro_coleta': True,
                'detalhes_coleta': str(e), 'saida': str(e), 'returncode': -1,
            }

    def _gerar_index(self, scripts_implementados: List[Dict], resultado_pytest: Optional[Dict],
                     gates: List[Gate], tempo_execucao: float,
                     teste_integracao_gerado: bool = False,
                     resultado_integracao: Optional[Dict] = None) -> Dict:
        return {
            'fase_id': 'phase_08_implementacao',
            'versao': '2.1',
            'status': 'COMPLETO' if all(g.passou for g in gates) else 'FALHOU',

            'timestamps': {
                'data_inicio': datetime.now(timezone.utc).isoformat(),
                'data_conclusao': datetime.now(timezone.utc).isoformat(),
                'duracao_segundos': tempo_execucao
            },

            'tokens': {
                'consumidos': self._tokens_totais,
                'medicao': 'real (soma de todas as chamadas LLM, incluindo correções)',
                'percentual_determinismo': 0
            },

            'schema_compartilhado': self.schema_compartilhado,

            'processamento': {
                'scripts_implementados': len(scripts_implementados),
                'tentativas_totais': sum(s.get('tentativas', 1) for s in scripts_implementados),
                'scripts_com_falha_apos_tentativas': sum(
                    1 for s in scripts_implementados if s.get('falhou_apos_tentativas')
                ),
                'teste_integracao_gerado': teste_integracao_gerado,
                'teste_integracao_passou': (
                    resultado_integracao.get('passaram', 0) > 0 and
                    resultado_integracao.get('falharam', 0) == 0 and
                    resultado_integracao.get('erros', 0) == 0 and
                    not resultado_integracao.get('erro_coleta', False)
                ) if resultado_integracao else False,
                'testes_passaram': resultado_pytest.get('passaram', 0) if resultado_pytest else 0,
                'testes_falharam': resultado_pytest.get('falharam', 0) if resultado_pytest else 0,
                'testes_erros': resultado_pytest.get('erros', 0) if resultado_pytest else 0,
                'testes_total': resultado_pytest.get('total', 0) if resultado_pytest else 0,
            },

            'gates_executados': [g.to_dict() for g in gates],

            'resume_info': {
                'proxima_fase': 'Nenhuma (projeto funcional completo)',
                'pode_prosseguir': all(g.passou for g in gates),
                'requer_intervencao_manual': not all(g.passou for g in gates)
            }
        }


# =============================================================================
# ENTRY POINT
# =============================================================================

def main():
    import argparse

    parser = argparse.ArgumentParser(
        description='Phase 8: Implementador com Verificação - aidd-project-generator v2.1'
    )
    parser.add_argument('pasta', help='Pasta do projeto (já com scaffold criado pela Fase 5)')
    parser.add_argument('--ideia', required=True, help='Descrição da ideia do projeto')
    parser.add_argument('--analise', default='{}', help='JSON da análise da Fase 2')
    parser.add_argument('--design', default='{}', help='JSON do design da Fase 3')

    args = parser.parse_args()
    pasta = Path(args.pasta)
    analise = json.loads(args.analise) if args.analise != '{}' else {}
    design = json.loads(args.design) if args.design != '{}' else {}

    if not analise and (pasta / '.aidd' / 'cache' / 'data' / 'analise_phase2.json').exists():
        analise = json.loads((pasta / '.aidd' / 'cache' / 'data' / 'analise_phase2.json').read_text(encoding='utf-8'))
    if not design and (pasta / '.aidd' / 'cache' / 'data' / 'design_aidd_phase3.json').exists():
        design = json.loads((pasta / '.aidd' / 'cache' / 'data' / 'design_aidd_phase3.json').read_text(encoding='utf-8'))

    implementador = ImplementadorFase8(pasta)
    resultado = implementador.executar(args.ideia, analise, design)

    if resultado is None:
        sys.exit(1)

    sys.exit(0)


if __name__ == '__main__':
    main()
