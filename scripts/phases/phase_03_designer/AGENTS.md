# Phase 03 — Designer (Micro-Ambiente)

## Escopo
Design com 5 subagentes paralelos (arquitetura, scripts, testes, tokens, stack).

## Restrições
- 5 subagentes via ThreadPoolExecutor (não sequencial)
- Cada subagente: prompt isolado com schema da Fase 2
- Consolidação mapeia cada subagente para chave correta do design
- Retry para subagentes com resposta vazia

## Gates
- D1: Camadas AIDD completas (contratos, gates, persistência)
- D2: Scripts com responsabilidade e pseudocódigo
- D3: Determinismo mínimo ≥65% (4/6 fases determinísticas = 66.7%)

## MCPs
- Filesystem MCP (leitura de analise_phase2.json)

## Saída
- `_phase_03_index.json` em `.aidd/cache/data/`
- `design_aidd_phase3.json` em `.aidd/cache/data/`
