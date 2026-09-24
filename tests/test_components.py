import base64
import math
import re
from pathlib import Path
from typing import get_args

import pytest
from streamlit.testing.v1 import AppTest

import iel_hackathon
from iel_hackathon.components import data_card, heatmap_table, load_chart, metric_card, section_title
from iel_hackathon.components import filter as filter_ui

OPTIONS = ["Sudeste e Centro-oeste", "Sul", "Nordeste", "Norte"]


def _filter_app() -> None:
    from iel_hackathon.components import filter_bar, render_filter

    with filter_bar():
        render_filter("Submercado", ["Sudeste e Centro-oeste", "Sul", "Nordeste", "Norte"], key="filtro")


@pytest.fixture
def at() -> AppTest:
    return AppTest.from_function(_filter_app).run()


def test_filter_shows_label_and_options_in_order(at):
    pills = at.pills(key="filtro")

    assert pills.label == "Submercado"
    assert pills.options == OPTIONS


def test_filter_selects_first_option_by_default(at):
    assert at.pills(key="filtro").value == "Sudeste e Centro-oeste"
    assert at.session_state.filtro == "Sudeste e Centro-oeste"


def test_clicking_option_makes_it_the_selected_one(at):
    at.pills(key="filtro").set_value("Sul").run()

    assert at.pills(key="filtro").value == "Sul"
    assert at.session_state.filtro == "Sul"


def test_filter_always_has_one_option_selected(at):
    assert at.pills(key="filtro").proto.required


def test_metric_card_markup_shows_title_value_and_caption():
    markup = metric_card._markup("Direta", "—%", "Prevê a carga líquida direto", highlight=False)

    assert '<p class="metric-card__title">Direta</p>' in markup
    assert '<p class="metric-card__value">—%</p>' in markup
    assert '<p class="metric-card__caption">Prevê a carga líquida direto</p>' in markup


def test_metric_card_highlight_makes_only_value_green():
    assert "metric-card__value--highlight" in metric_card._markup("t", "R$ —", "c", highlight=True)
    assert "metric-card__value--highlight" not in metric_card._markup("t", "R$ —", "c", highlight=False)


def test_metric_card_escapes_html():
    markup = metric_card._markup("<b>t</b>", "a & b", "c", highlight=False)

    assert "<b>" not in markup
    assert "&lt;b&gt;t&lt;/b&gt;" in markup
    assert "a &amp; b" in markup


@pytest.mark.parametrize(
    "css_path",
    [
        filter_ui._CSS_PATH,
        metric_card._CSS_PATH,
        data_card._CSS_PATH,
        heatmap_table._CSS_PATH,
        load_chart._CSS_PATH,
        section_title._CSS_PATH,
        # Layout do dashboard, injetado pelo main.py (que não dá para importar sem rodar o app).
        Path(iel_hackathon.__file__).with_name("dashboard.css"),
    ],
)
def test_css_has_no_less_than_sign(css_path):
    # O sanitizador do frontend do Streamlit descarta o <style> inteiro se o CSS contiver "<".
    assert "<" not in css_path.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("data_value", "text"),
    [
        (data_card.DataValue(value="1,2", unit="GW"), "1,2 GW"),
        (data_card.DataValue(value=None, unit="GW"), "— GW"),
        (data_card.DataValue(value=None), "—"),
        (data_card.DataValue(value=None, placeholder="—/—/—"), "—/—/—"),
        (data_card.DataValue(value="25/12/26", placeholder="—/—/—"), "25/12/26"),
    ],
)
def test_data_value_text_uses_placeholder_only_when_value_is_missing(data_value, text):
    assert data_value.text == text


def _full_data_card_markup() -> str:
    return data_card._markup(
        title="Dados do período",
        description="Diferença na carga líquida",
        highlight=data_card.DataValue(value=None, unit="GW"),
        rows=[
            data_card.DataRow(label="Temperatura", value="27", unit="°C", icon="thermometer"),
            data_card.DataRow(label="Calendário (feriado/emenda)", value=None, placeholder="—/—/—"),
        ],
        footer="Contribuições calculadas pela abordagem decomposta",
    )


def test_data_card_markup_shows_every_prop():
    markup = _full_data_card_markup()

    assert '<p class="data-card__title">Dados do período</p>' in markup
    assert '<p class="data-card__description">Diferença na carga líquida</p>' in markup
    assert '<p class="data-card__highlight">— GW</p>' in markup
    assert '<p class="data-card__label">Temperatura</p>' in markup
    assert '<p class="data-card__value">27 °C</p>' in markup
    assert '<p class="data-card__label">Calendário (feriado/emenda)</p>' in markup
    assert '<p class="data-card__value">—/—/—</p>' in markup
    assert '<p class="data-card__footer">Contribuições calculadas pela abordagem decomposta</p>' in markup


@pytest.mark.parametrize(
    ("omitted", "css_class"),
    [
        ("title", "data-card__title"),
        ("description", "data-card__description"),
        ("highlight", "data-card__highlight"),
        ("rows", "data-card__row"),
        ("footer", "data-card__footer"),
    ],
)
def test_data_card_omitted_prop_is_not_rendered(omitted, css_class):
    props = {
        "title": "t",
        "description": "d",
        "highlight": data_card.DataValue(value="1", unit="GW"),
        "rows": [data_card.DataRow(label="l", value="1", unit="GW")],
        "footer": "f",
    }
    props[omitted] = None

    assert css_class not in data_card._markup(**props)


def test_data_card_empty_rows_render_nothing():
    assert "data-card__row" not in data_card._markup(title="t", rows=[])


def test_data_card_row_shows_icon_only_when_given():
    with_icon = data_card._markup(rows=[data_card.DataRow(label="l", value=None, icon="sunny")])
    without_icon = data_card._markup(rows=[data_card.DataRow(label="l", value=None)])

    assert 'src="app/static/icons/sunny.svg"' in with_icon
    assert "<img" not in without_icon


def test_data_card_escapes_html():
    markup = data_card._markup(
        title="<b>t</b>",
        description="<b>d</b>",
        highlight=data_card.DataValue(value="<b>1</b>", unit="a & b"),
        rows=[data_card.DataRow(label="<b>l</b>", value=None, placeholder="<b>p</b>")],
        footer="<b>f</b>",
    )

    assert "<b>" not in markup
    for text in ("t", "d", "1", "l", "p", "f"):
        assert f"&lt;b&gt;{text}&lt;/b&gt;" in markup
    assert "a &amp; b" in markup


@pytest.mark.parametrize("icon", get_args(data_card.IconName))
def test_data_card_icons_exist(icon):
    icon_path = data_card._ICONS_DIR / f"{icon}.svg"

    assert icon_path.is_file()
    assert icon_path.stat().st_size > 0


HEATMAP_ROWS = ["SE/CO", "S", "NE", "N"]
HEATMAP_COLUMNS = ["Madrugada 0h–6h", "Manhã 6h–9h", "Sol 9h–16h", "Rampa 16h–19h", "Noite 19h–24h"]
GREEN, YELLOW, ORANGE, RED = heatmap_table.BAND_COLORS
_HEATMAP_CELL = re.compile(r'<p class="heatmap-table__cell" style="background-color: ([^"]*)">([^<]*)</p>')


def _heatmap_cells(markup: str) -> list[tuple[str, str]]:
    """(cor, texto) de cada célula, linha por linha."""
    return _HEATMAP_CELL.findall(markup)


def _heatmap_markup(**props) -> str:
    return heatmap_table._markup(**{"rows": HEATMAP_ROWS, "columns": HEATMAP_COLUMNS, "thresholds": (2, 4, 6), **props})


def test_heatmap_table_shows_title_labels_and_headers_in_order():
    markup = _heatmap_markup(title="MAPE por submercado e faixa horária", rows_label="Submercado")
    texts = [
        '<p class="heatmap-table__title">MAPE por submercado e faixa horária</p>',
        '<p class="heatmap-table__corner">Submercado</p>',
        *(f'<p class="heatmap-table__column">{column}</p>' for column in HEATMAP_COLUMNS),
        *(f'<p class="heatmap-table__row-label">{row}</p>' for row in HEATMAP_ROWS),
    ]

    positions = [markup.index(text) for text in texts]
    assert positions == sorted(positions)


def test_heatmap_table_without_title_renders_no_title():
    assert "heatmap-table__title" not in _heatmap_markup()


def test_heatmap_table_without_values_matches_the_design():
    cells = _heatmap_cells(_heatmap_markup())

    assert [text for _, text in cells] == ["—"] * 20
    assert [color for color, _ in cells] == [color for row in heatmap_table.EMPTY_COLORS for color in row]


def test_heatmap_table_empty_colors_repeat_in_cycle_on_bigger_tables():
    cells = _heatmap_cells(_heatmap_markup(rows=[*HEATMAP_ROWS, "Extra"], columns=[*HEATMAP_COLUMNS, "Extra"]))
    colors = [color for color, _ in cells]
    pattern = heatmap_table.EMPTY_COLORS

    assert colors[:6] == [*pattern[0], pattern[0][0]]
    assert colors[4 * 6 : 5 * 6] == colors[:6]


@pytest.mark.parametrize(
    ("value", "color"),
    [(1, GREEN), (2, GREEN), (2.01, YELLOW), (4, YELLOW), (5, ORANGE), (6, ORANGE), (6.5, RED)],
)
def test_heatmap_table_value_gets_the_color_of_its_band(value, color):
    cells = _heatmap_cells(_heatmap_markup(values={"SE/CO": {"Madrugada 0h–6h": value}}))

    assert cells[0][0] == color


@pytest.mark.parametrize(("value", "text"), [(2.13, "2,13%"), (2, "2,00%"), (2.126, "2,13%"), (12.5, "12,50%")])
def test_heatmap_table_formats_value_as_percentage(value, text):
    cells = _heatmap_cells(_heatmap_markup(values={"SE/CO": {"Madrugada 0h–6h": value}}))

    assert cells[0][1] == text


@pytest.mark.parametrize("values", [{"SE/CO": {"Madrugada 0h–6h": None}}, {"SE/CO": {"Madrugada 0h–6h": math.nan}}])
def test_heatmap_table_none_and_nan_are_empty(values):
    cells = _heatmap_cells(_heatmap_markup(values=values))

    assert cells[0] == (heatmap_table.EMPTY_COLORS[0][0], "—")


def test_heatmap_table_missing_cells_stay_empty():
    cells = _heatmap_cells(_heatmap_markup(values={"S": {"Sol 9h–16h": 3}}))

    assert cells[5 + 2] == (YELLOW, "3,00%")
    assert [text for _, text in cells].count("—") == 19


def test_heatmap_table_accepts_custom_bands_and_placeholder():
    cells = _heatmap_cells(
        _heatmap_markup(
            rows=["A"],
            columns=["x", "y", "z", "w"],
            values={"A": {"x": 5, "y": 10, "z": 15}},
            thresholds=(5, 10),
            colors=("#000001", "#000002", "#000003"),
            empty_colors=[["#00000f"]],
            placeholder="n/d",
        )
    )

    assert cells == [("#000001", "5,00%"), ("#000002", "10,00%"), ("#000003", "15,00%"), ("#00000f", "n/d")]


@pytest.mark.parametrize(
    ("thresholds", "colors"),
    [
        ((2, 4, 6), (GREEN, YELLOW, ORANGE)),
        ((2, 4), heatmap_table.BAND_COLORS),
        ((4, 2, 6), heatmap_table.BAND_COLORS),
        ((2, 2, 6), heatmap_table.BAND_COLORS),
    ],
)
def test_heatmap_table_rejects_invalid_bands(thresholds, colors):
    with pytest.raises(ValueError):
        _heatmap_markup(thresholds=thresholds, colors=colors)


def test_heatmap_table_escapes_html():
    markup = heatmap_table._markup(
        title="<b>t</b>",
        rows_label="<b>r</b>",
        rows=["<b>l</b>"],
        columns=["<b>c</b>"],
        thresholds=(),
        colors=['red"><b>x</b>'],
        values={"<b>l</b>": {"<b>c</b>": 1}},
    )

    assert "<b>" not in markup
    for text in ("t", "r", "l", "c", "x"):
        assert f"&lt;b&gt;{text}&lt;/b&gt;" in markup
    assert "red&quot;&gt;" in markup


# Carga líquida e bruta de um dia, em MW: o mínimo da líquida na faixa solar (8h–16h) é às 12h.
NET = [45_000.0] * 8 + [42_000.0, 41_000.0, 40_000.0, 39_000.0, 37_000.0, 38_000.0, 41_000.0, 44_000.0, 46_000.0] + [50_000.0] * 7
GROSS = [value + (10_000.0 if 8 <= hour <= 16 else 100.0) for hour, value in enumerate(NET)]


def _load_chart_markup(**kwargs) -> str:
    return load_chart._markup(**{"net": NET, "gross": GROSS, **kwargs})


def _load_chart_svg(markup: str) -> str:
    """O SVG do gráfico, que vai embutido em base64 no src da imagem."""
    (encoded,) = re.findall(r'src="data:image/svg\+xml;base64,([^"]+)"', markup)
    return base64.b64decode(encoded).decode()


def test_load_chart_shows_legend_and_axis_labels():
    markup = _load_chart_markup()

    for text in (
        "Carga líquida (o que a rede entrega)",
        "Carga bruta (energia total consumida)",
        "MMGD (energia gerada pelos painéis solares)",
    ):
        assert f"<p>{text}</p>" in markup
    assert re.findall(r"<p>(\d+h)</p>", markup) == [f"{hour}h" for hour in range(0, 25, 2)]
    assert len(re.findall(r'class="load-chart__y-label"', markup)) == 8


def test_load_chart_marks_valley_at_lowest_net_load_in_solar_window():
    markup = _load_chart_markup()

    # 12h = 50% da largura; a linha tracejada do vale sai de x = 12h no viewBox.
    assert (
        '<p class="load-chart__annotation load-chart__annotation--center" style="left: 50%">'
        "Vale da carga líquida</p>"
    ) in markup
    assert '<line x1="120" y1="38"' in _load_chart_svg(markup)


def test_load_chart_ramp_text_starts_at_ramp_start():
    markup = _load_chart_markup(ramp=(16, 19))

    # 16h = 66,67% da largura: o texto começa no início do traço da rampa, como no design.
    assert (
        '<p class="load-chart__annotation load-chart__annotation--start" style="left: 66.67%">'
        "Rampa 16h–19h</p>"
    ) in markup


def test_load_chart_missing_hour_breaks_the_lines():
    net = list(NET)
    net[5] = None
    svg = _load_chart_svg(_load_chart_markup(net=net))

    net_lines = re.findall(r'<polyline points="([^"]+)"[^>]*url\(#load-chart-net\)', svg)
    assert [len(points.split()) for points in net_lines] == [5, 18]
    # A área da MMGD também para onde falta a líquida.
    assert len(re.findall(r"<polygon ", svg)) == 2


def _tooltip_values(markup: str) -> list[list[str]]:
    """Os três valores (líquida, bruta, MMGD) do card de cada hora."""
    zones = markup.split('class="load-chart__hover"')[1:]
    return [re.findall(r'class="load-chart__tooltip-value">([^<]+)</p>', zone) for zone in zones]


def test_load_chart_tooltip_shows_net_gross_and_mmgd_for_every_hour():
    markup = _load_chart_markup()

    values = _tooltip_values(markup)
    assert len(values) == 24
    # 12h: líquida 37 GW, bruta 47 GW, MMGD = bruta − líquida.
    assert values[12] == ["37,00 GW", "47,00 GW", "10,00 GW"]
    assert re.findall(r'class="load-chart__tooltip-hour">(\d+h)</p>', markup) == [f"{hour}h" for hour in range(24)]
    for label in ("Carga líquida", "Carga bruta", "MMGD"):
        assert markup.count(f"<p>{label}</p>") == 24


def test_load_chart_tooltip_zones_cover_the_plot_without_overflowing():
    markup = _load_chart_markup()

    zones = re.findall(r'class="load-chart__hover" style="left: ([\d.]+)%; width: ([\d.]+)%"', markup)
    assert zones[0] == ("0", "2.083")
    assert zones[12] == ("47.92", "4.167")
    left, width = map(float, zones[-1])
    assert left + width == pytest.approx(100, abs=0.01)
    # Até o meio do dia o card abre à direita; depois, à esquerda.
    sides = re.findall(r"load-chart__tooltip--(right|left)", markup)
    assert sides == ["right"] * 12 + ["left"] * 12


def test_load_chart_tooltip_missing_value_shows_placeholder():
    net = list(NET)
    net[5] = None
    markup = _load_chart_markup(net=net)

    assert _tooltip_values(markup)[5] == ["-- GW", f"{GROSS[5] / 1000:.2f}".replace(".", ",") + " GW", "-- GW"]
    zone = markup.split('class="load-chart__hover"')[6]
    assert "load-chart__dot--net" not in zone
    assert "load-chart__dot--gross" in zone


def test_load_chart_without_data_shows_placeholder_axis():
    markup = _load_chart_markup(net=[None] * 24, gross=[None] * 24)

    assert markup.count(">--GW</p>") == 8
    assert "<img" not in markup
    assert "load-chart__hover" not in markup


def test_load_chart_rejects_wrong_number_of_hours():
    with pytest.raises(ValueError):
        _load_chart_markup(net=NET[:23])


@pytest.mark.parametrize(("minimum", "maximum"), [(36.79, 55.2), (7.51, 16.97), (7.16, 11.24), (0.2, 0.9), (40, 40)])
def test_load_chart_y_scale_fits_data_below_annotations(minimum, maximum):
    low, step = load_chart._y_scale(minimum, maximum)

    assert low <= minimum
    assert low + 7 * step * (1 - load_chart._HEADROOM) >= maximum
    mantissa = step / 10 ** math.floor(math.log10(step))
    assert any(math.isclose(mantissa, nice) for nice in load_chart._NICE_STEPS)


@pytest.mark.parametrize(("value", "text"), [(38, "38GW"), (7.5, "7,5GW"), (12.25, "12,25GW"), (0.0, "0GW")])
def test_load_chart_formats_gw_in_pt_br(value, text):
    assert load_chart._format_gw(value) == text


def test_section_title_escapes_html():
    assert section_title._markup("<b>Previsão</b>") == '<p class="section-title">&lt;b&gt;Previsão&lt;/b&gt;</p>'
