"""Card de dados: título, descrição, valor em destaque, linhas com ícone e rodapé, como o "Dados do período"."""

from collections.abc import Sequence
from dataclasses import dataclass
from html import escape
from pathlib import Path
from typing import Literal

import streamlit as st

IconName = Literal["sunny", "power", "thermometer", "calendar_today"]

_CSS_PATH = Path(__file__).with_name("data_card.css")
# Os ícones do design ficam no static serving (src/iel_hackathon/static/), servidos em app/static/.
_ICONS_DIR = Path(__file__).parent.parent / "static" / "icons"
_ICONS_URL = "app/static/icons"
_MISSING = "—"


@dataclass(frozen=True, kw_only=True)
class DataValue:
    """Valor já formatado + unidade. Sem valor, mostra o placeholder (padrão: "— {unidade}")."""

    value: str | None
    unit: str | None = None
    placeholder: str | None = None

    @property
    def text(self) -> str:
        if self.value is None:
            if self.placeholder is not None:
                return self.placeholder
            return f"{_MISSING} {self.unit}" if self.unit else _MISSING
        return f"{self.value} {self.unit}" if self.unit else self.value


@dataclass(frozen=True, kw_only=True)
class DataRow(DataValue):
    """Linha do card: ícone opcional, rótulo à esquerda e valor à direita."""

    label: str
    icon: IconName | None = None


def render_data_card(
    *,
    title: str | None = None,
    description: str | None = None,
    highlight: DataValue | None = None,
    rows: Sequence[DataRow] | None = None,
    footer: str | None = None,
) -> None:
    """Renderiza o card de dados. Cada parte só aparece se for passada."""
    # CSS só com <style> vai para o container de eventos do Streamlit: repeti-lo a cada card não ocupa espaço.
    st.html(_CSS_PATH)
    st.html(_markup(title=title, description=description, highlight=highlight, rows=rows, footer=footer))


def _markup(
    *,
    title: str | None = None,
    description: str | None = None,
    highlight: DataValue | None = None,
    rows: Sequence[DataRow] | None = None,
    footer: str | None = None,
) -> str:
    parts = []
    if title is not None:
        parts.append(f'<p class="data-card__title">{escape(title)}</p>')
    if description is not None:
        parts.append(f'<p class="data-card__description">{escape(description)}</p>')
    if highlight is not None:
        parts.append(f'<p class="data-card__highlight">{escape(highlight.text)}</p>')
    parts.extend(_row_markup(row) for row in rows or ())
    if footer is not None:
        parts.append(f'<p class="data-card__footer">{escape(footer)}</p>')
    return f'<div class="data-card">{"".join(parts)}</div>'


def _row_markup(row: DataRow) -> str:
    icon = (
        f'<img class="data-card__icon" src="{_ICONS_URL}/{row.icon}.svg" width="24" height="24" alt="">'
        if row.icon
        else ""
    )
    return (
        '<div class="data-card__row">'
        f"{icon}"
        f'<p class="data-card__label">{escape(row.label)}</p>'
        f'<p class="data-card__value">{escape(row.text)}</p>'
        "</div>"
    )
