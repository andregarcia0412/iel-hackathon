from typing import get_args

import pytest
from streamlit.testing.v1 import AppTest

from iel_hackathon.components import data_card
from iel_hackathon.components import filter as filter_ui
from iel_hackathon.components import metric_card

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


@pytest.mark.parametrize("css_path", [filter_ui._CSS_PATH, metric_card._CSS_PATH, data_card._CSS_PATH])
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
