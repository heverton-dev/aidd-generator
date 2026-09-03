# Phase 08 — Implementador (Micro-Ambiente)

## Escopo
Geração de código funcional real com verificação via pytest + loop de correção.

## Restrições
- LLM via subagente efêmero (Context-Purge Engine) — descarte imediato de contexto
- Schema SQLite compartilhado derivado ANTES de implementar scripts isolados
- Validação AST mecânica (_validar_contrato_ast) antes de pytest real
- Loop de correção: traceback real do pytest reenviado ao LLM (até 3 tentativas)
- UTF-8 explícito na escrita de arquivos gerados

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
