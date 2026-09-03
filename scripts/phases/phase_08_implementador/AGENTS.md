# Phase 08 — Implementador (Micro-Ambiente)

## Escopo
Geração de código funcional real com verificação via pytest + loop de correção.

## Restrições
- LLM via subagente efêmero (Context-Purge Engine) — descarte imediato de contexto
- Schema SQLite compartilhado derivado ANTES de implementar scripts isolados
- Validação AST mecânica (_validar_contrato_ast) antes de pytest real
- Loop de correção: traceback real do pytest reenviado ao LLM (até 3 tentativas)
- UTF-8 explícito na escrita de arquivos gerados

## Result Monad
- Toda operação de implementação DEVE usar o padrão Result Monad:
  - `Ok(valor)` para sucesso — contém o artefato gerado
  - `Err(erro)` para falha — contém mensagem + traceback
- Funções NUNCA levantam exceções para controle de fluxo — retornam Result
- O pipeline encadeia Results: se qualquer etapa retorna Err, o pipeline para
- Result é inspecionável: `result.is_ok()`, `result.is_err()`, `result.unwrap()`

## pytest
- Testes DEVE ser executados via `subprocess.run([sys.executable, '-m', 'pytest', ...])`
- Traceback real capturado e reenviado ao LLM para correção
- 100% dos testes DEVE passar — nunca estimado, sempre medido
- Testes gerados incluem: unitários por script + integração cross-script

## Gates
- I1: Todos os scripts do design implementados em disco
- I2: pytest coleta sem erro de import
- I3: 100% dos testes passando (nunca estimado)
- I4: CLI smoke-test (--help exit code 0)
- I5: Teste de integração cross-script gerado e passando

## MCPs
- Database MCP (para inspeção de schema SQLite)

## Saída
- `_phase_08_index.json` em `.aidd/cache/data/`
- `src/` com scripts implementados
- `tests/` com testes gerados

## Tokens
- Consumo: variável (chamadas reais de LLM, incluindo correções)
- Determinismo: 0% (pura LLM com verificação mecânica)
