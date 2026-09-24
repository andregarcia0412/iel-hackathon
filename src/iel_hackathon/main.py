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
from iel_hackathon.forecast import (
    CONTEXT_HOUR,
    MAPE_BANDS,
    DayContext,
    PeriodSummary,
    load_day_context,
    load_day_forecast,
    load_mape_by_band,
    load_period_summary,
)
from iel_hackathon.login import render_login
from iel_hackathon.sidebar import render_sidebar

SUBMERCADOS = {"Sudeste e Centro-oeste": "SECO", "Sul": "S", "Nordeste": "NE", "Norte": "N"}
PERIODOS = {"Próximo dia": 1, "Próximos 7 dias": 7}
MAPE_ROWS = {"SE/CO": "SECO", "S": "S", "NE": "NE", "N": "N"}

_CSS_PATH = Path(__file__).with_name("dashboard.css")

MAPE_TABLE = {
    "title": "MAPE por submercado e faixa horária",
    "rows_label": "Submercado",
    "rows": list(MAPE_ROWS),
    "columns": [label for label, _, _ in MAPE_BANDS],
    "thresholds": (2, 4, 6),
}


def _metric_cards(summary: PeriodSummary) -> list[dict]:
    return [
        {
            "title": "Valor de energia economizado",
            "value": f"{_number(summary.avoided_error_mwh / 1000, 1)} GWh",
            "caption": "melhor abordagem por hora",
        },
        {
            "title": "Valor estimado de economia",
            "value": _brl_millions(summary.avoided_cost_brl),
            "caption": "Erro evitado × preço da energia na hora",
            "highlight": True,
        },
        {"title": "Direta", "value": f"{_number(summary.mape_direct, 2)}%", "caption": "Prevê a carga líquida direto"},
        {
            "title": "Decomposta",
            "value": f"{_number(summary.mape_decomposed, 2)}%",
            "caption": "carga bruta − MMGD",
        },
    ]


def _period_data(context: DayContext, horizon: int) -> dict:
    when = "amanhã" if horizon == 1 else f"daqui a {horizon} dias"
    capacity = None if context.mmgd_capacity_mw is None else _number(context.mmgd_capacity_mw / 1000, 1)
    return {
        "title": "Dados do período",
        "description": (
            f"Diferença na carga líquida de {when} às {CONTEXT_HOUR}h, comparada à mesma hora da semana passada"
        ),
        "highlight": DataValue(value=_number(context.net_change_mw / 1000, 2, signed=True), unit="GW"),
        "rows": [
            DataRow(label="Irradiância prevista", value=_number(context.radiation_wm2, 0), unit="W/m²", icon="sunny"),
            DataRow(label="Potência de MMGD instalada", value=capacity, unit="GW", icon="power"),
            DataRow(label="Temperatura", value=_number(context.temperature_c, 1), unit="°C", icon="thermometer"),
            DataRow(
                label="Calendário (feriado/emenda)",
                value=f"{context.date:%d/%m} · {context.day_type}",
                icon="calendar_today",
            ),
        ],
        "footer": "Previsão meteorológica e calendário usados pelo modelo; potência instalada no último mês publicado",
    }


def _number(value: float, decimals: int, *, signed: bool = False) -> str:
    text = f"{value:{'+' if signed else ''},.{decimals}f}"
    return text.replace(",", "_").replace(".", ",").replace("_", ".").replace("-", "−")


def _brl_millions(value: float) -> str:
    sign = "−" if value < 0 else ""
    return f"{sign}R$ {_number(abs(value) / 1e6, 1)} mi"


def _login() -> None:
    if render_login():
        st.switch_page(DASHBOARD)


def _dashboard() -> None:
    st.html(_CSS_PATH)
    render_sidebar()

    with filter_bar():
        submercado = render_filter("Submercado", list(SUBMERCADOS), key="filtro_submercado")
        periodo = render_filter("Período", list(PERIODOS), key="filtro_periodo")
    codigo, horizonte = SUBMERCADOS[submercado], PERIODOS[periodo]

    cards = _metric_cards(load_period_summary(codigo, horizonte))
    forecast = load_day_forecast(codigo, horizonte)
    period_data = _period_data(load_day_context(codigo, horizonte), horizonte)
    mape_by_band = load_mape_by_band(horizonte)
    mape_values = {row: mape_by_band[code] for row, code in MAPE_ROWS.items()}

    st.session_state["dashboard_data"] = {
        "submercado": submercado,
        "periodo": periodo,
        "cards": cards,
        "period_data": period_data,
        "mape_table": {**MAPE_TABLE, "values": mape_values},
        "load_chart": {
            "date": f"{forecast.date:%d/%m/%Y}",
            "net": forecast.net,
            "gross": forecast.gross,
        },
    }

    with st.container(key="metric_cards"):
        for card in cards:
            render_metric_card(**card)

    with st.container(key="load_section"):
        render_section_title("Previsão de Cargas")
        with st.container(key="load_row", horizontal=True):
            with st.container(key="load_chart_column"):
                render_load_chart(net=forecast.net, gross=forecast.gross)
            with st.container(key="load_data_column"):
                render_data_card(**period_data)

    with st.container(key="mape_section"):
        render_heatmap_table(**MAPE_TABLE, values=mape_values)

    render_chat()


st.set_page_config(page_title="IEL Hackathon", initial_sidebar_state="locked")

LOGIN = st.Page(_login, title="Login", default=True)
DASHBOARD = st.Page(_dashboard, title="Dashboard", url_path="dashboard")
st.navigation([LOGIN, DASHBOARD], position="hidden").run()
