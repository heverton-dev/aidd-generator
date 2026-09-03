# Phase 04 — Decisor (Micro-Ambiente)

## Escopo
Decisões GLOBAL vs LOCAL para skills, MCPs e hooks. Modal interativo ou heurística automática.

## Restrições
- input() real para modo interativo
- Heurística coerente para --nao-interativo (baseada em subagentes do design)
- Gate C2: Path.resolve().exists() real (não vacuamente True)

## Gates
- C1: Decisões válidas (GLOBAL/LOCAL para cada item)
- C2: Symlinks resolvem para caminhos reais existentes
- C3: Configuração completa (todas as decisões tomadas)

## Saída
- `_phase_04_index.json` em `.aidd/cache/data/`
- `config_global_local_phase4.json` em `.aidd/cache/data/`
