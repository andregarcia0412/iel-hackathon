from pathlib import Path

import streamlit as st

from iel_hackathon.chat import render_chat
from iel_hackathon.components import (
    DataRow,
    DataValue,
    filter_bar,
    render_data_card,
    render_filter,
    render_heatmap_table,
    render_load_chart,
    render_metric_card,
    render_section_title,
)
from iel_hackathon.forecast import load_day_forecast
from iel_hackathon.login import render_login
from iel_hackathon.sidebar import render_sidebar

# Opções dos filtros → código do submercado e horizonte (em dias) nas previsões do modelo.
SUBMERCADOS = {"Sudeste e Centro-oeste": "SECO", "Sul": "S", "Nordeste": "NE", "Norte": "N"}
PERIODOS = {"Próximo dia": 1, "Próximos 7 dias": 7}

# Layout da página: ocupa a janela inteira e reorganiza os cards em telas estreitas.
_CSS_PATH = Path(__file__).with_name("dashboard.css")

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


def _login() -> None:
    # Sem validação: qualquer email e senha, inclusive vazios, levam ao dashboard.
    if render_login():
        st.switch_page(DASHBOARD)


def _dashboard() -> None:
    st.html(_CSS_PATH)
    render_sidebar()

    with filter_bar():
        submercado = render_filter("Submercado", list(SUBMERCADOS), key="filtro_submercado")
        periodo = render_filter("Período", list(PERIODOS), key="filtro_periodo")

    # As keys dos containers são usadas pelo dashboard.css para distribuir a largura e a altura da janela.
    with st.container(key="metric_cards"):
        for card in CARDS:
            render_metric_card(**card)

    with st.container(key="load_section"):
        render_section_title("Previsão de Cargas")
        with st.container(key="load_row", horizontal=True):
            with st.container(key="load_chart_column"):
                forecast = load_day_forecast(SUBMERCADOS[submercado], PERIODOS[periodo])
                render_load_chart(net=forecast.net, gross=forecast.gross)
            with st.container(key="load_data_column"):
                render_data_card(**PERIOD_DATA)

    with st.container(key="mape_section"):
        render_heatmap_table(**MAPE_TABLE)

    render_chat()


# "locked": a barra lateral do design não recolhe.
st.set_page_config(page_title="IEL Hackathon", initial_sidebar_state="locked")

# O app abre no login; o dashboard também pode ser aberto direto em /dashboard.
# A navegação nativa fica oculta: a sidebar do design só aparece no dashboard.
LOGIN = st.Page(_login, title="Login", default=True)
DASHBOARD = st.Page(_dashboard, title="Dashboard", url_path="dashboard")
st.navigation([LOGIN, DASHBOARD], position="hidden").run()
