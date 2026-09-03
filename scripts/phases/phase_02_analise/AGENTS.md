# Phase 02 — Analisador (Micro-Ambiente)

## Escopo
Análise estratégica da ideia + referências via LLM (protocolo delegado ou headless).

## Restrições
- LLM via `solicitar_llm()` de `utils_delegacao.py` — NUNCA chamada direta a litellm
- Prompt em Inglês (economia de tokens), output em PT-BR
- Referências citadas devem vir da Fase 1 — NUNCA fabricar citações

## Gates
- A1: Schema do JSON de análise válido
- A2: Zero alucinação (referências reais ou vazio honesto)
- A3: Dados completos (stack, público, diferenciais)
- A4: Qualidade de linguagem (sem TODO/pass)

## MCPs
- Filesystem MCP (leitura de insights_phase1.json)

## Saída
- `_phase_02_index.json` em `.aidd/cache/data/`
- `analise_phase2.json` em `.aidd/cache/data/`
