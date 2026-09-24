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
        return None


OLLAMA_MODEL = _setting("OLLAMA_MODEL", "gemma4:31b-cloud")
OLLAMA_HOST = _setting("OLLAMA_HOST", "https://ollama.com")


def api_key() -> str | None:
    return _setting("OLLAMA_API_KEY")
