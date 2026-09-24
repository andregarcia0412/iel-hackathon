"""Gráfico de cargas do dia: carga líquida, carga bruta e MMGD (a área entre as duas), hora a hora, como o "Previsão de Cargas"."""

import base64
import math
from collections.abc import Sequence
from html import escape
from pathlib import Path
from typing import Literal

import streamlit as st

_CSS_PATH = Path(__file__).with_name("load_chart.css")

_HOURS = 24
_Y_TICKS = 8
# Altura da área do gráfico no design, em px.
_HEIGHT = 254
# Fração do topo reservada às anotações: no design, o pico das curvas fica a 71 dos 254 px.
_HEADROOM = 0.28
# Largura de cada hora no viewBox do SVG. O SVG estica na largura do card; as linhas não engrossam (non-scaling-stroke).
_HOUR_WIDTH = 10
# Altura, em px, do traço da rampa e do início da linha do vale (logo abaixo dos textos).
_ANNOTATION_Y = 38
# Passos "redondos" do eixo Y, multiplicados por potências de 10.
_NICE_STEPS = (1, 2, 2.5, 4, 5)
_MISSING = "--"


def render_load_chart(
    *,
    net: Sequence[float | None],
    gross: Sequence[float | None],
    solar_window: tuple[int, int] = (8, 16),
    ramp: tuple[int, int] = (16, 19),
) -> None:
    """Renderiza o gráfico de um dia, com `net` e `gross` em MW para cada hora (0h–23h); `None` deixa a hora vazia.

    A faixa `solar_window` (horas de início e fim) é destacada e marca o vale: a hora de menor carga líquida dentro dela.
    `ramp` marca o intervalo da rampa de fim de tarde.
    Com o mouse sobre uma hora, um card mostra a carga líquida, a bruta e a MMGD (bruta − líquida) daquela hora.
    """
    # CSS só com <style> vai para o container de eventos do Streamlit: repeti-lo a cada gráfico não ocupa espaço.
    st.html(_CSS_PATH)
    st.html(_markup(net=net, gross=gross, solar_window=solar_window, ramp=ramp))


def _markup(
    *,
    net: Sequence[float | None],
    gross: Sequence[float | None],
    solar_window: tuple[int, int] = (8, 16),
    ramp: tuple[int, int] = (16, 19),
) -> str:
    if len(net) != _HOURS or len(gross) != _HOURS:
        raise ValueError(f"São {_HOURS} valores por série (0h–23h), não {len(net)} e {len(gross)}.")
    net_gw = [_to_gw(value) for value in net]
    gross_gw = [_to_gw(value) for value in gross]
    known = [value for value in (*net_gw, *gross_gw) if value is not None]

    if known:
        low, step = _y_scale(min(known), max(known))
        labels = [_format_gw(low + i * step) for i in range(_Y_TICKS)]

        def y(value: float) -> float:
            return _HEIGHT * (1 - (value - low) / (step * (_Y_TICKS - 1)))
    else:
        labels = [f"{_MISSING}GW"] * _Y_TICKS
        y = None

    y_labels = "".join(
        f'<p class="load-chart__y-label" style="top: {_percent(1 - i / (_Y_TICKS - 1))}">{escape(label)}</p>'
        for i, label in enumerate(labels)
    )
    x_labels = "".join(f"<p>{hour}h</p>" for hour in range(0, _HOURS + 1, 2))
    plot = _plot(net_gw, gross_gw, y, solar_window, ramp) if y else ""
    return (
        '<div class="load-chart">'
        f"{_legend()}"
        '<div class="load-chart__chart">'
        '<div class="load-chart__body">'
        f'<div class="load-chart__y-axis">{y_labels}</div>'
        f'<div class="load-chart__plot">{plot}</div>'
        "</div>"
        '<div class="load-chart__x-axis">'
        f'<div class="load-chart__x-labels">{x_labels}</div>'
        "</div>"
        "</div>"
        "</div>"
    )


def _legend() -> str:
    items = (
        ("net", "Carga líquida (o que a rede entrega)"),
        ("gross", "Carga bruta (energia total consumida)"),
        ("mmgd", "MMGD (energia gerada pelos painéis solares)"),
    )
    return (
        '<div class="load-chart__legend">'
        + "".join(
            f'<div class="load-chart__legend-item">'
            f'<span class="load-chart__swatch load-chart__swatch--{kind}"></span><p>{escape(text)}</p>'
            "</div>"
            for kind, text in items
        )
        + "</div>"
    )


def _plot(net, gross, y, solar_window, ramp) -> str:
    solar_start, solar_end = solar_window
    band_top = _HEIGHT * _HEADROOM
    band = (
        f'<rect x="{_x(solar_start)}" y="{band_top:.2f}" width="{_x(solar_end) - _x(solar_start)}" '
        f'height="{_HEIGHT - band_top:.2f}" fill="#CAE300" fill-opacity="0.1"/>'
        + "".join(
            f'<line x1="{_x(hour)}" y1="{band_top:.2f}" x2="{_x(hour)}" y2="{_HEIGHT}" '
            'stroke="#09D075" stroke-width="2.871" vector-effect="non-scaling-stroke"/>'
            for hour in solar_window
        )
    )
    # MMGD: a área entre a carga bruta (em cima) e a líquida (embaixo), em cada trecho com as duas séries.
    both = [(n, g) if n is not None and g is not None else None for n, g in zip(net, gross)]
    area = "".join(
        f'<polygon points="{_points([(h, g) for h, (_, g) in run] + [(h, n) for h, (n, _) in reversed(run)], y)}" '
        'fill="#09D075" fill-opacity="0.25"/>'
        for run in _runs(both)
        if len(run) > 1
    )
    gross_line = "".join(
        f'<polyline points="{_points(run, y)}" fill="none" stroke="#044947" stroke-width="1.914" '
        'stroke-dasharray="7.66 4.78" vector-effect="non-scaling-stroke"/>'
        for run in _runs(gross)
    )
    net_line = "".join(
        f'<polyline points="{_points(run, y)}" fill="none" stroke="url(#load-chart-net)" stroke-width="2.871" '
        'vector-effect="non-scaling-stroke"/>'
        for run in _runs(net)
    )
    gradient = (
        '<defs><linearGradient id="load-chart-net" gradientUnits="userSpaceOnUse" '
        f'x1="0" y1="0" x2="{_x(_HOURS)}" y2="0">'
        '<stop offset="0" stop-color="#CAE300"/><stop offset="1" stop-color="#2BDCD1"/>'
        "</linearGradient></defs>"
    )

    # Vale: linha tracejada do texto até a carga líquida, na hora de menor carga líquida da faixa solar.
    valley = _valley(net, solar_window)
    valley_line = ""
    annotations = []
    if valley is not None:
        valley_line = (
            f'<line x1="{_x(valley)}" y1="{_ANNOTATION_Y}" x2="{_x(valley)}" y2="{y(net[valley]):.2f}" '
            'stroke="#9A9A94" stroke-width="0.957" stroke-dasharray="3.83 3.83" vector-effect="non-scaling-stroke"/>'
        )
        annotations.append(_annotation("Vale da carga líquida", valley, align="center"))
    ramp_start, ramp_end = ramp
    ramp_line = (
        f'<line x1="{_x(ramp_start)}" y1="{_ANNOTATION_Y}" x2="{_x(ramp_end)}" y2="{_ANNOTATION_Y}" '
        'stroke="#9A9A94" stroke-width="1.439" vector-effect="non-scaling-stroke"/>'
    )
    # Como no design, o texto da rampa começa junto do traço, e não no meio dele.
    annotations.append(_annotation(f"Rampa {ramp_start}h–{ramp_end}h", ramp_start, align="start"))

    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {_x(_HOURS)} {_HEIGHT}" preserveAspectRatio="none">'
        f"{gradient}{band}{area}{gross_line}{net_line}{valley_line}{ramp_line}"
        "</svg>"
    )
    # O st.html descarta <svg> embutido; como imagem, o SVG passa e estica na largura do card.
    src = "data:image/svg+xml;base64," + base64.b64encode(svg.encode()).decode()
    image = (
        f'<img class="load-chart__svg" src="{src}" '
        'alt="Carga líquida, carga bruta e MMGD previstas por hora">'
    )
    return image + "".join(annotations) + _tooltips(net, gross, y)


def _tooltips(net, gross, y) -> str:
    """Uma faixa por hora que, com o mouse em cima, mostra a linha da hora, os pontos das curvas e os três valores.

    Só HTML e CSS: o st.html não roda JavaScript. A MMGD é a bruta − a líquida, a mesma área desenhada no gráfico.
    """
    zones = []
    for hour in range(_HOURS):
        # A faixa vai de meia hora antes a meia hora depois; a primeira começa em 0h e a última vai até 24h.
        start = max(hour - 0.5, 0)
        end = _HOURS if hour == _HOURS - 1 else hour + 0.5
        guide = _percent((hour - start) / (end - start))
        dots = "".join(
            f'<span class="load-chart__dot load-chart__dot--{kind}" '
            f'style="left: {guide}; top: {_percent(y(value) / _HEIGHT)}"></span>'
            for kind, value in (("gross", gross[hour]), ("net", net[hour]))
            if value is not None
        )
        mmgd = gross[hour] - net[hour] if net[hour] is not None and gross[hour] is not None else None
        rows = "".join(
            '<div class="load-chart__tooltip-row">'
            f'<span class="load-chart__swatch load-chart__swatch--{kind}"></span>'
            f'<p>{label}</p><p class="load-chart__tooltip-value">{escape(_format_tooltip_gw(value))}</p>'
            "</div>"
            for kind, label, value in (
                ("net", "Carga líquida", net[hour]),
                ("gross", "Carga bruta", gross[hour]),
                ("mmgd", "MMGD", mmgd),
            )
        )
        # Até o meio do dia o card abre à direita da linha; depois, à esquerda, para não sair do gráfico.
        side = "right" if hour < _HOURS // 2 else "left"
        zones.append(
            f'<div class="load-chart__hover" style="left: {_percent(start / _HOURS)}; '
            f'width: {_percent((end - start) / _HOURS)}">'
            f'<span class="load-chart__guide" style="left: {guide}"></span>'
            f"{dots}"
            f'<div class="load-chart__tooltip load-chart__tooltip--{side}" style="left: {guide}">'
            f'<p class="load-chart__tooltip-hour">{hour}h</p>{rows}'
            "</div>"
            "</div>"
        )
    return "".join(zones)


def _annotation(text: str, hour: float, *, align: Literal["center", "start"]) -> str:
    """Texto acima do gráfico, na hora `hour`: centralizado nela ou começando nela."""
    return (
        f'<p class="load-chart__annotation load-chart__annotation--{align}" '
        f'style="left: {_percent(hour / _HOURS)}">{escape(text)}</p>'
    )


def _valley(net: Sequence[float | None], solar_window: tuple[int, int]) -> int | None:
    start, end = solar_window
    hours = [hour for hour in range(start, min(end, _HOURS - 1) + 1) if net[hour] is not None]
    return min(hours, key=lambda hour: net[hour]) if hours else None


def _runs(values):
    """Trechos de horas seguidas com valor, como listas de (hora, valor): uma hora vazia quebra a linha."""
    runs, current = [], []
    for hour, value in enumerate(values):
        if value is None:
            if current:
                runs.append(current)
            current = []
        else:
            current.append((hour, value))
    if current:
        runs.append(current)
    return runs


def _points(run, y) -> str:
    return " ".join(f"{_x(hour)},{y(value):.2f}" for hour, value in run)


def _x(hour: float) -> float:
    return hour * _HOUR_WIDTH


def _percent(fraction: float) -> str:
    return f"{fraction * 100:.4g}%"


def _y_scale(minimum: float, maximum: float) -> tuple[float, float]:
    """Base e passo do eixo Y: o menor passo redondo em que as curvas cabem abaixo da faixa das anotações."""
    exponent = math.floor(math.log10(max(abs(maximum), 1e-9))) - 3
    while True:
        for nice in _NICE_STEPS:
            step = nice * 10**exponent
            low = math.floor(minimum / step) * step
            if low + step * (_Y_TICKS - 1) * (1 - _HEADROOM) >= maximum:
                return low, step
        exponent += 1


def _format_gw(value: float) -> str:
    text = f"{value:.3f}".rstrip("0").rstrip(".")
    return f"{text.replace('.', ',')}GW"


def _format_tooltip_gw(value: float | None) -> str:
    if value is None:
        return f"{_MISSING} GW"
    return f"{value:.2f}".replace(".", ",") + " GW"


def _to_gw(value: float | None) -> float | None:
    if value is None or math.isnan(value):
        return None
    return value / 1000
