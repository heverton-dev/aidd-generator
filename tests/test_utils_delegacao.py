# -*- coding: utf-8 -*-
"""
Testes para utils_delegacao.extrair_json_resposta — Correção: fence markdown
embutido dentro do VALOR de um campo JSON ('codigo'/'teste'), não apenas
envolvendo a resposta inteira.

Achado real: ENTREGA-FINAL-rastreador-habitos gerou test_coletar_habitos.py
com "```python" literal na primeira linha (SyntaxError na coleta do pytest),
porque o LLM colou o bloco de código (fences inclusos) como valor literal do
campo "teste" no JSON, e nada removia o fence antes de escrever em disco.
"""

import json

from utils_delegacao import extrair_json_resposta


def test_extrai_e_remove_fence_embutido_nos_campos_codigo_e_teste():
    payload = {
        "codigo": "```python\ndef f():\n    pass\n```",
        "teste": "```python\nimport pytest\ndef test_f():\n    pass\n```",
        "caminho_relativo": "x.py",
        "caminho_teste": "test_x.py",
    }
    resultado = extrair_json_resposta(json.dumps(payload))
    assert resultado["codigo"] == "def f():\n    pass"
    assert resultado["teste"] == "import pytest\ndef test_f():\n    pass"
    assert "```" not in resultado["codigo"]
    assert "```" not in resultado["teste"]


def test_nao_afeta_campos_sem_fence():
    payload = {
        "codigo": "def f():\n    pass",
        "teste": "def test_f():\n    pass",
        "caminho_relativo": "x.py",
        "caminho_teste": "test_x.py",
    }
    resultado = extrair_json_resposta(json.dumps(payload))
    assert resultado["codigo"] == "def f():\n    pass"
    assert resultado["teste"] == "def test_f():\n    pass"


def test_remove_fence_mesmo_quando_json_envelopado_em_markdown():
    payload = {
        "codigo": "```python\nx = 1\n```",
        "teste": "```python\nassert x == 1\n```",
        "caminho_relativo": "x.py",
        "caminho_teste": "test_x.py",
    }
    texto = "```json\n" + json.dumps(payload) + "\n```"
    resultado = extrair_json_resposta(texto)
    assert resultado["codigo"] == "x = 1"
    assert resultado["teste"] == "assert x == 1"


# =============================================================================
# TESTES DE TIMEOUT E FALLBACK DO MODO DELEGADO (TAREFA 1)
# =============================================================================

def test_solicitar_llm_modo_delegado_timeout_com_fallback_headless(monkeypatch):
    import utils_delegacao

    # Simula timeout da ADE
    monkeypatch.setattr(utils_delegacao.RequisicaoLLMDelegada, 'aguardar_resposta', lambda *a, **kw: None)

    # Configura LLM_MODEL no ambiente
    monkeypatch.setenv('LLM_MODEL', 'provedor/modelo-teste')

    # Mock do solicitar_llm_modo_headless
    headless_chamado = []
    def fake_headless(prompt, contexto, fase, modelo=None, temperatura=0.7):
        headless_chamado.append((prompt, contexto, fase, modelo))
        return {
            'conteudo': 'resposta do fallback headless',
            'tokens_consumidos': 42,
            'modelo_usado': modelo or 'provedor/modelo-teste',
            'timestamp_resposta': '2026-08-30T00:00:00Z',
        }
    monkeypatch.setattr(utils_delegacao, 'solicitar_llm_modo_headless', fake_headless)

    resp = utils_delegacao.solicitar_llm_modo_delegado(
        prompt="Gerar código", contexto="Phase 8", fase="phase_08", timeout=1
    )

    assert resp is not None
    assert resp['conteudo'] == 'resposta do fallback headless'
    assert len(headless_chamado) == 1
    assert headless_chamado[0][0] == "Gerar código"


def test_solicitar_llm_modo_delegado_timeout_sem_headless_retorna_none(monkeypatch):
    import utils_delegacao

    # Simula timeout da ADE
    monkeypatch.setattr(utils_delegacao.RequisicaoLLMDelegada, 'aguardar_resposta', lambda *a, **kw: None)

    # Remove LLM_MODEL do ambiente
    monkeypatch.delenv('LLM_MODEL', raising=False)

    headless_chamado = []
    monkeypatch.setattr(utils_delegacao, 'solicitar_llm_modo_headless', lambda *a, **kw: headless_chamado.append(1))

    resp = utils_delegacao.solicitar_llm_modo_delegado(
        prompt="Gerar código", contexto="Phase 8", fase="phase_08", timeout=1, modelo=None
    )

    assert resp is None
    assert len(headless_chamado) == 0


def test_solicitar_llm_modo_delegado_sucesso_nao_chama_headless(monkeypatch):
    import utils_delegacao

    # Simula ADE respondendo a tempo
    resposta_ade = {
        'id': '123',
        'conteudo': 'resposta delegada oficial',
        'tokens_consumidos': 100,
        'modelo_usado': 'claude-opus-5',
        'timestamp_resposta': '2026-08-30T00:00:00Z',
    }
    monkeypatch.setattr(utils_delegacao.RequisicaoLLMDelegada, 'aguardar_resposta', lambda *a, **kw: resposta_ade)
    monkeypatch.setenv('LLM_MODEL', 'provedor/modelo-teste')

    headless_chamado = []
    monkeypatch.setattr(utils_delegacao, 'solicitar_llm_modo_headless', lambda *a, **kw: headless_chamado.append(1))

    resp = utils_delegacao.solicitar_llm_modo_delegado(
        prompt="Gerar código", contexto="Phase 8", fase="phase_08", timeout=1
    )

    assert resp is not None
    assert resp['conteudo'] == 'resposta delegada oficial'
    assert len(headless_chamado) == 0

