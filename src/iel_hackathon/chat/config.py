"""Configuração da integração com o Ollama Cloud, lida de variáveis de ambiente.

Crie um arquivo `.env` na raiz (já coberto pelo .gitignore) a partir do
`.env.example`, ou exporte as variáveis no shell antes de rodar o app.
"""

import os

from dotenv import load_dotenv

load_dotenv()

OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "gemma4:31b-cloud")
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "https://ollama.com")


def api_key() -> str | None:
    """Chave do Ollama Cloud, ou `None` se não configurada (o chat avisa o usuário)."""
    return os.environ.get("OLLAMA_API_KEY") or None
