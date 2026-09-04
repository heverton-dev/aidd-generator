# PLANO DE BACKPORT — Correções feitas no monorepo ecossistema-aidd

> **Origem:** `C:\Users\trcnologia\Desktop\ecossistema-aidd\tools\aidd-generator`
> **Repositório:** `heverton-dev/aidd-generator` (padrão neste repositório)
> **Status:** PRONTO PARA EXECUÇÃO
> **Dificuldade:** Baixa — sem dependência externa (Docker, Helm, etc.)

---

## 1. CONTEXTO

O `ecossistema-aidd` é uma cópia deste repositório dentro de um monorepo (feita em 03/09/2026). Uma auditoria de correção de riscos rodada nessa cópia encontrou e corrigiu 2 bugs reais que **também existem aqui**, confirmado por `diff` direto entre os dois. Nenhuma das correções abaixo foi aplicada ainda neste repositório.

## 2. O QUE MUDA

### 2.1. `tests/test_preflight_llm.py` — teste não-hermético (causa raiz confirmada)

`test_sem_llm_model_falha` não limpava a variável de ambiente `CLAUDECODE` antes de chamar `preflight_llm.verificar_llm_pronto()`. Quando o pytest roda de dentro de uma sessão real do Claude Code (`CLAUDECODE=1` genuinamente setado no shell), `verificar_llm_pronto()` detecta corretamente o Protocolo Delegado ativo e retorna sucesso — mas o teste esperava falha, então quebra. **Não é bug de produto**, é premissa de teste incompleta.

**Mudança:** adicionar limpeza de `CLAUDECODE`, `MIMOCODE`, `MIMO_SESSION`, `MIMO_WORKSPACE`, `OPENCODE`, `OPENCODE_SESSION`, `ANTIGRAVITY_CLI`, `AGY_SESSION`, `ORCA_WORKSPACE`, `AIDD_HARNESS_NAME` no início do teste (via `monkeypatch.delenv(..., raising=False)`).

### 2.2. `tests/test_phase_05.py` — mesma causa raiz, sinal diferente

`test_criar_arquivos_configuracao_sem_env_e_honesto` limpava uma lista fixa de variáveis, mas `detectar_harness_nome()` (em `scripts/phases/utils_modelo.py`) trata **qualquer** variável terminada em `_SESSION`/`_HARNESS` do ambiente real como sinal de harness ativo (detecção agnóstica por design). `CLAUDE_CODE_CHILD_SESSION` (setada pelo próprio Claude Code para rastrear subprocessos) não estava na lista limpa pelo teste.

**Mudança:** depois da lista fixa de `monkeypatch.delenv`, adicionar um loop que limpa qualquer variável do ambiente real terminada em `_SESSION` ou `_HARNESS`.

### 2.3. `scripts/phases/05_criador.py` — detecção de drift em cópias de fallback (funcionalidade nova)

Quando o SO nega criação de symlink (comum no Windows sem Modo Desenvolvedor), `_criar_symlink_ou_copia` cai para cópia de conteúdo de `AGENTS.md` para `.claude/CLAUDE.md`, `.agent/AGENT.md` etc. Essa cópia só é honesta no instante da criação — se `AGENTS.md` for editado depois, as cópias ficam obsoletas em silêncio, sem nada avisar.

**Mudança:**
- `_criar_symlink_ou_copia` passa a retornar `bool` (`True` = symlink real, `False` = cópia de fallback).
- Novo método `_registrar_sync_manifest`: quando há pelo menos 1 fallback, grava `.aidd/sync_manifest.json` e `scripts/gates/G_SYNC_HARNESS.py` (script standalone, sem depender de nada externo) **dentro do projeto gerado** — o dono do projeto gerado pode rodar esse gate a qualquer momento pra checar se as cópias ainda batem com `AGENTS.md`.
- Novo gate `E5_sincronizacao_harness` em `ValidadorGatesPhase5` (reaproveita o mesmo script gerado, sem duplicar lógica) — completa o contrato "E1-E5 + S1" que a docstring do módulo já dizia ter, mas só existia E1-E4.

## 3. COMO APLICAR

Copiar o conteúdo atualizado dos 3 arquivos de `ecossistema-aidd/tools/aidd-generator/` para este repositório:
- `scripts/phases/05_criador.py`
- `tests/test_phase_05.py`
- `tests/test_preflight_llm.py`

## 4. VALIDAÇÃO (critério de aceite)

```bash
python -m pytest -q
```
Esperado: **756 passed, 0 failed** (mesmo número medido no monorepo). Se o número de testes totais aqui for diferente (repositório pode ter evoluído desde a cópia), o critério real é: **0 failed, 0 error**.

## 5. COMMIT E PUSH

Commit único, mensagem no mesmo padrão do monorepo, depois `git push origin main`.
