"""Configuração da integração com o Ollama Cloud.

Ordem de leitura: `st.secrets` (Streamlit Community Cloud e `.streamlit/secrets.toml`
em desenvolvimento local), depois variáveis de ambiente / arquivo `.env`.
Nunca commite valores reais — secrets.toml e .env estão no .gitignore.
"""

import os

from dotenv import load_dotenv

load_dotenv()


def _setting(name: str, default: str | None = None) -> str | None:
    return _secret(name) or os.environ.get(name) or default


def _secret(name: str) -> str | None:
    try:
        import streamlit as st

        return st.secrets.get(name)
    except Exception:
        # Sem arquivo de secrets (testes, bare mode) ou sem runtime do Streamlit.
        return None


OLLAMA_MODEL = _setting("OLLAMA_MODEL", "gemma4:31b-cloud")
OLLAMA_HOST = _setting("OLLAMA_HOST", "https://ollama.com")


def api_key() -> str | None:
    """Chave do Ollama Cloud, ou `None` se não configurada (o chat avisa o usuário)."""
    return _setting("OLLAMA_API_KEY")
