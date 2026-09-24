import streamlit as st

from iel_hackathon.chat import render_chat
from iel_hackathon.components import (
    DataRow,
    DataValue,
    filter_bar,
    render_data_card,
    render_filter,
    render_heatmap_table,
    render_metric_card,
)
from iel_hackathon.sidebar import render_sidebar

SUBMERCADOS = ["Sudeste e Centro-oeste", "Sul", "Nordeste", "Norte"]
PERIODOS = ["Próximo dia", "Próximos 7 dias"]

# Página de teste dos componentes, com os textos de exemplo do design.
CARDS = [
    {
        "title": "Valor de energia economizado",
        "value": "—GW",
        "caption": "melhor abordagem por hora",
    },
    {
        "title": "Valor estimado de economia",
        "value": "R$ —",
        "caption": "Erro evitado × preço da energia na hora",
        "highlight": True,
    },
    {"title": "Direta", "value": "—%", "caption": "Prevê a carga líquida direto"},
    {"title": "Decomposta", "value": "—%", "caption": "carga bruta − MMGD"},
]

PERIOD_DATA = {
    "title": "Dados do período",
    "description": "Diferença na carga líquida de amanhã às 13h, comparada à mesma hora da semana passada",
    "highlight": DataValue(value=None, unit="GW"),
    "rows": [
        DataRow(label="Irradiância prevista", value=None, unit="GW", icon="sunny"),
        DataRow(
            label="Potência de MMGD instalada", value=None, unit="GW", icon="power"
        ),
        DataRow(label="Temperatura", value=None, unit="°C", icon="thermometer"),
        DataRow(
            label="Calendário (feriado/emenda)",
            value=None,
            placeholder="—/—/—",
            icon="calendar_today",
        ),
    ],
    "footer": "Contribuições calculadas pela abordagem decomposta",
}

MAPE_TABLE = {
    "title": "MAPE por submercado e faixa horária",
    "rows_label": "Submercado",
    "rows": ["SE/CO", "S", "NE", "N"],
    "columns": [
        "Madrugada 0h–6h",
        "Manhã 6h–9h",
        "Sol 9h–16h",
        "Rampa 16h–19h",
        "Noite 19h–24h",
    ],
    # Verde até 2%, amarelo até 4%, laranja até 6%, vermelho acima.
    "thresholds": (2, 4, 6),
}

# "locked": a barra lateral do design não recolhe.
st.set_page_config(page_title="IEL Hackathon", initial_sidebar_state="locked")

render_sidebar()

with filter_bar():
    render_filter("Submercado", SUBMERCADOS, key="filtro_submercado")
    render_filter("Período", PERIODOS, key="filtro_periodo")

for column, card in zip(st.columns(len(CARDS), gap=12), CARDS):
    with column:
        render_metric_card(**card)

# Largura do card no design; sem ela o card esticaria na página toda.
with st.container(width=370):
    render_data_card(**PERIOD_DATA)

render_heatmap_table(**MAPE_TABLE)

render_chat()
