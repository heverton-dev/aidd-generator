# Phase 05 — Criador (Micro-Ambiente)

## Escopo
Criação determinística do projeto: diretórios, configs, SQLite, git init, symlinks.

## Restrições
- 100% determinístico (Zero Token de LLM)
- Métricas medidas via rglob/git (nunca hardcoded)
- AGENTS.md como fonte única; .claude/CLAUDE.md como symlink real
- config_fase4 (GLOBAL/LOCAL) → symlinks reais

## Gates
- E1: Arquivos criados em disco
- E2: Git init + commit bem-sucedido
- E3: SQLite inicializado
- E4: Permissões corretas
- S1: Segurança (.gitignore, sem secrets hardcoded)

## Saída
- `_phase_05_index.json` em `.aidd/cache/data/`
