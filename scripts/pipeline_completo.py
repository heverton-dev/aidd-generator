#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PIPELINE COMPLETO — aidd-project-generator v2.1
Orquestra as Fases 1-7 (ou 1-8 com --implementar-codigo) ponta a ponta,
encadeando os dados reais que cada fase persiste em
<pasta>/.aidd/cache/data/ (não fabrica nem reaproveita dados de outra
execução).

Uso:
    python scripts/pipeline_completo.py "ideia do projeto" --pasta ../MEU-PROJETO
    python scripts/pipeline_completo.py "ideia do projeto" --pasta ../MEU-PROJETO --interativo
    python scripts/pipeline_completo.py "ideia do projeto" --pasta ../MEU-PROJETO --implementar-codigo

Ordem padrão (sem --implementar-codigo): 1→2→3→4→5→6→7
Ordem com --implementar-codigo:           1→2→3→4→5→8→6→7

--implementar-codigo roda a Fase 8 (implementação funcional real com
testes e loop de correção via LLM) logo após a Fase 5, ANTES de
Fase 6/7 — assim a documentação (Fase 6) reflete o código real e a
auto-crítica (Fase 7) audita o projeto funcional completo.

Sem fallback silencioso: se qualquer fase falhar (retornar None), o
pipeline para imediatamente e reporta exatamente qual fase e por quê —
nunca segue adiante com dado fabricado ou fase pulada.

Inovações v2.1:
- Fleet Discovery: auto-descoberta de agentes instalados no host
- Context-Purge Engine: subagentes efêmeros com descarte imediato de contexto
- Intent Router: detecção de intenção para /generate e linguagem natural
- Micro-ambientes: cada fase tem AGENTS.md com regras isoladas
"""

import sys
import os
import json
import time
import argparse
import importlib.util
from pathlib import Path

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

PHASES_DIR = Path(__file__).parent / 'phases'
sys.path.insert(0, str(PHASES_DIR))

# Pré-voo LLM (verifica LLM_MODEL + credencial antes de rodar o pipeline)
from preflight_llm import verificar_llm_pronto  # noqa: E402
from utils_delegacao import LLMNaoConfiguradoException
from utils_fleet_discovery import resolver_fleet, fleet_status_para_log, persistir_fleet_status
from utils_subagente_ephemero import ContextPurgeEngine


def _carregar_fase(alias: str, filename: str):
    spec = importlib.util.spec_from_file_location(alias, PHASES_DIR / filename)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


p1 = _carregar_fase('pipeline_p1', '01_pesquisador.py')
p2 = _carregar_fase('pipeline_p2', '02_analisador.py')
p3 = _carregar_fase('pipeline_p3', '03_designer.py')
p4 = _carregar_fase('pipeline_p4', '04_decisor.py')
p5 = _carregar_fase('pipeline_p5', '05_criador.py')
p6 = _carregar_fase('pipeline_p6', '06_documentador.py')
p7 = _carregar_fase('pipeline_p7', '07_analisador.py')
p8 = _carregar_fase('pipeline_p8', '08_implementador.py')


def _falhar(resultado: dict, fase: str, t0: float) -> dict:
    resultado['status'] = 'FALHOU'
    resultado['fase_que_falhou'] = fase
    resultado['duracao_segundos'] = time.time() - t0
    return resultado


def executar_pipeline(ideia: str, pasta_projeto: Path, nao_interativo: bool = True,
                       implementar_codigo: bool = False) -> dict:
    """Executa as fases em sequência, real, sem mock, sem fallback silencioso.

    Ordem padrão (sem --implementar-codigo): 1→2→3→4→5→6→7
    Ordem com --implementar-codigo:           1→2→3→4→5→8→6→7

    Fase 8 roda ANTES de Fase 6/7 quando --implementar-codigo é usado,
    assim a documentação (Fase 6) reflete o código real implementado e
    a auto-crítica (Fase 7) audita o projeto funcional completo — não
    apenas a intenção de design.
    """
    pasta_projeto = Path(pasta_projeto)
    cache_dir = pasta_projeto / '.aidd' / 'cache'
    data_dir = cache_dir / 'data'
    total_fases = 8 if implementar_codigo else 7

    resultado = {'ideia': ideia, 'pasta': str(pasta_projeto), 'fases_completas': {}}
    t0 = time.time()

    # Fleet Discovery: auto-detectar agentes instalados no host
    fleet = resolver_fleet()
    resultado['fleet'] = fleet.to_dict()
    print(f"\n🔍 Fleet Discovery:")
    print(fleet_status_para_log(fleet))
    persistir_fleet_status(fleet, pasta_cache=cache_dir)

    # Context-Purge Engine: inicializar para métricas de subagentes efêmeros
    purge_engine = ContextPurgeEngine(pasta_cache=cache_dir)

    print("\n" + "=" * 70)
    print(f"PIPELINE COMPLETO: FASE 1/{total_fases} — Pesquisador")
    print("=" * 70)
    idx1 = p1.PesquisadorFase1(cache_dir).executar(ideia)
    resultado['fases_completas']['fase_1'] = idx1 is not None
    if idx1 is None:
        return _falhar(resultado, 'fase_1_pesquisador', t0)

    insights_path = data_dir / 'insights_phase1.json'
    referencias = json.loads(insights_path.read_text(encoding='utf-8')) if insights_path.exists() else {}

    print("\n" + "=" * 70)
    print(f"PIPELINE COMPLETO: FASE 2/{total_fases} — Analisador")
    print("=" * 70)
    idx2 = p2.AnalisadorFase2(cache_dir).executar(ideia, referencias)
    resultado['fases_completas']['fase_2'] = idx2 is not None
    if idx2 is None:
        return _falhar(resultado, 'fase_2_analisador', t0)

    analise = json.loads((data_dir / 'analise_phase2.json').read_text(encoding='utf-8'))

    print("\n" + "=" * 70)
    print(f"PIPELINE COMPLETO: FASE 3/{total_fases} — Designer")
    print("=" * 70)
    idx3 = p3.DesignerFase3(cache_dir).executar(ideia, analise)
    resultado['fases_completas']['fase_3'] = idx3 is not None
    if idx3 is None:
        return _falhar(resultado, 'fase_3_designer', t0)

    design = json.loads((data_dir / 'design_aidd_phase3.json').read_text(encoding='utf-8'))

    print("\n" + "=" * 70)
    print(f"PIPELINE COMPLETO: FASE 4/{total_fases} — Decisor")
    print("=" * 70)
    idx4 = p4.DecisorFase4(cache_dir).executar(design, nao_interativo=nao_interativo)
    resultado['fases_completas']['fase_4'] = idx4 is not None
    if idx4 is None:
        return _falhar(resultado, 'fase_4_decisor', t0)

    config_fase4 = json.loads((data_dir / 'config_global_local_phase4.json').read_text(encoding='utf-8'))

    print("\n" + "=" * 70)
    print(f"PIPELINE COMPLETO: FASE 5/{total_fases} — Criador")
    print("=" * 70)
    idx5 = p5.CriadorProjetoFase5(pasta_projeto).executar(ideia, config_fase4)
    resultado['fases_completas']['fase_5'] = idx5 is not None
    if idx5 is None:
        return _falhar(resultado, 'fase_5_criador', t0)

    # Fase 8 roda ANTES de Fase 6/7 quando --implementar-codigo é usado,
    # para que documentação e auto-crítica reflitam o código real.
    if implementar_codigo:
        print("\n" + "=" * 70)
        print(f"PIPELINE COMPLETO: FASE 8/{total_fases} — Implementador com Verificação")
        print("=" * 70)
        idx8 = p8.ImplementadorFase8(pasta_projeto).executar(ideia, analise, design)
        resultado['fases_completas']['fase_8'] = idx8 is not None and idx8.get('status') == 'COMPLETO'
        if not resultado['fases_completas']['fase_8']:
            return _falhar(resultado, 'fase_8_implementador', t0)

    print("\n" + "=" * 70)
    print(f"PIPELINE COMPLETO: FASE 6/{total_fases} — Documentador")
    print("=" * 70)
    contexto_doc = {**analise, **design}
    idx6 = p6.DocumentadorFase6(
        pasta_cache=cache_dir, output_base=pasta_projeto / 'output'
    ).executar(pasta_projeto.name, contexto_doc, titulo=ideia)
    resultado['fases_completas']['fase_6'] = idx6 is not None and idx6.get('status') == 'COMPLETO'
    if not resultado['fases_completas']['fase_6']:
        return _falhar(resultado, 'fase_6_documentador', t0)

    print("\n" + "=" * 70)
    print(f"PIPELINE COMPLETO: FASE 7/{total_fases} — Auto-crítica")
    print("=" * 70)
    idx7 = p7.AnalisadorCriticoAutomatico(pasta_projeto).executar()
    resultado['fases_completas']['fase_7'] = idx7.get('status') == 'COMPLETO'
    resultado['score_final'] = idx7.get('score')

    resultado['status'] = 'COMPLETO'
    resultado['duracao_segundos'] = time.time() - t0

    # Persistir métricas do Context-Purge Engine
    resultado['context_purge'] = purge_engine.metricas.to_dict()
    purge_engine.persistir_metricas()

    return resultado


def main():
    parser = argparse.ArgumentParser(
        description='Pipeline completo aidd-project-generator (Fases 1-7, ou 1-8 com --implementar-codigo)'
    )
    parser.add_argument('ideia', help='Descrição da ideia do projeto a ser gerado')
    parser.add_argument('--pasta', required=True, help='Pasta onde o projeto será criado')
    parser.add_argument('--interativo', action='store_true',
                       help='Usar modal interativo (input()) na Fase 4 em vez da heurística automática')
    parser.add_argument('--implementar-codigo', action='store_true',
                       help='Rodar também a Fase 8 (implementa código funcional real a partir do design, com testes e loop de correção)')

    args = parser.parse_args()

    # --- Pré-voo: verificar LLM antes de gastar tempo com Fase 1 ---
    ok, msg = verificar_llm_pronto()
    if not ok:
        print("\n" + "=" * 70)
        print("❌ PREFLIGHT FALHOU — " + msg)
        print("=" * 70 + "\n")
        sys.exit(1)

    print(f"✓ {msg}")

    # Rede de segurança: mesmo com o pré-voo passando (checa só presença de
    # env vars), uma chave presente mas inválida só falha na chamada real —
    # captura aqui pra nunca vazar o stack trace cru do litellm.
    try:
        resultado = executar_pipeline(
            args.ideia, Path(args.pasta), nao_interativo=not args.interativo,
            implementar_codigo=args.implementar_codigo
        )
    except LLMNaoConfiguradoException as e:
        print(f"\n❌ {e.mensagem_usuario}")
        sys.exit(1)

    print("\n" + "=" * 70)
    if resultado['status'] == 'COMPLETO':
        print(f"✅ PIPELINE COMPLETO — score final: {resultado.get('score_final')}/100")
        # Fleet info
        fleet_info = resultado.get('fleet', {})
        print(f"   Fleet: {fleet_info.get('modo', '?')} ({fleet_info.get('total_detectados', 0)} agente(s))")
        # Context-Purge metrics
        purge_info = resultado.get('context_purge', {})
        if purge_info:
            print(f"   Context-Purge: {purge_info.get('total_subagentes_criados', 0)} subagentes, "
                  f"{purge_info.get('total_tokens_consumidos', 0)} tokens, "
                  f"{purge_info.get('taxa_sucesso', 0)}% sucesso")
    else:
        print(f"❌ PIPELINE FALHOU na {resultado['fase_que_falhou']}")
    print(f"   Duração: {resultado['duracao_segundos']:.1f}s")
    print("=" * 70 + "\n")

    sys.exit(0 if resultado['status'] == 'COMPLETO' else 1)


if __name__ == '__main__':
    main()
