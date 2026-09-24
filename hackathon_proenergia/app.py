from __future__ import annotations

import json
import os
from pathlib import Path

import joblib
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from sin_forecast.inference import predict_scenario

st.set_page_config(page_title="SIN — previsão e cenários", page_icon="⚡", layout="wide")
ARTIFACTS = Path(os.environ.get("SIN_ARTIFACTS", str(Path(__file__).parent / "artifacts")))


@st.cache_resource
def load_bundle(path, modified):
    return joblib.load(path)


@st.cache_data
def load_table(path, modified):
    return pd.read_parquet(path)


def main():
    st.title("⚡ Previsão de carga do SIN")
    st.caption("Carga líquida, carga bruta e MMGD • D+1 / D+7 • simulação interativa")
    model_path = ARTIFACTS / "models" / "forecast_bundle.joblib"
    prediction_path = ARTIFACTS / "reports" / "test_predictions.parquet"
    if not model_path.exists() or not prediction_path.exists():
        st.info("Execute `python run.py train` para preparar os modelos e os resultados.")
        return
    bundle = load_bundle(str(model_path), model_path.stat().st_mtime_ns)
    test = load_table(str(prediction_path), prediction_path.stat().st_mtime_ns)
    with st.sidebar:
        st.header("Cenário")
        horizon = st.selectbox("Horizonte", sorted(test.horizon.unique()), format_func=lambda h: f"D+{h}")
        sub = st.selectbox("Submercado", ["SECO", "S", "NE", "N"])
        subset = test[test.horizon.eq(horizon) & test.submercado.eq(sub)].copy()
        subset["target_date"] = subset.target_time.dt.strftime("%Y-%m-%d")
        complete = subset.groupby("target_date").size()
        dates = sorted(complete[complete.eq(24)].index)
        target_date = st.selectbox("Dia previsto (replay do teste)", dates, index=len(dates) - 1)
        with st.form("scenario_controls"):
            temperature_delta = st.slider("Alteração da temperatura (°C)", -10.0, 10.0, 0.0, .5)
            radiation_multiplier = st.slider("Multiplicador de irradiância", 0.0, 2.0, 1.0, .05)
            change_cloud = st.checkbox("Alterar nebulosidade")
            cloud = st.slider("Nebulosidade (%)", 0, 100, 50)
            change_humidity = st.checkbox("Alterar umidade")
            humidity = st.slider("Umidade relativa (%)", 0, 100, 60)
            holiday = st.selectbox("Calendário do dia", ["Original", "Simular feriado", "Simular dia sem feriado"])
            st.form_submit_button("Calcular cenário", type="primary")
    rows = subset[subset.target_date.eq(target_date)].drop(columns="target_date")
    rows = rows.drop(columns=[c for c in rows if c.startswith(("pred_", "error_", "absolute_error_", "ape_"))])
    overrides = {"temperature_delta": temperature_delta, "radiation_multiplier": radiation_multiplier,
                 "cloud_override": float(cloud) if change_cloud else None,
                 "humidity_override": float(humidity) if change_humidity else None,
                 "holiday_override": {"Original": None, "Simular feriado": 1, "Simular dia sem feriado": 0}[holiday]}
    predicted = predict_scenario(bundle, rows, overrides)
    origin = predicted.origin_time.iloc[0]
    st.markdown(f"**{sub} · D+{horizon} · dia-alvo {target_date}**  \nOrigem simulada: `{origin}` · modelo treinado até `{bundle.trained_through}`")
    st.caption("Replay de previsão histórica com alterações hipotéticas. A curva real é referência do cenário original; não é o resultado observado do cenário alterado.")
    a, b, c, d = st.columns(4)
    a.metric("Carga líquida média", f"{predicted.pred_final.mean():,.0f} MW", f"{predicted.scenario_delta_mw.mean():+,.0f} MW")
    b.metric("Energia prevista no dia", f"{predicted.pred_final.sum():,.0f} MWh", f"{predicted.scenario_delta_mw.sum():+,.0f} MWh")
    c.metric("Pico previsto", f"{predicted.pred_final.max():,.0f} MW")
    d.metric("MMGD média — rota decomposta", f"{predicted.pred_mmgd.mean():,.0f} MW")
    if predicted.outside_training_range.any():
        st.info("Este cenário contém valores meteorológicos fora da faixa do treino; a resposta envolve extrapolação.")
    fig = go.Figure()
    for column, label, color in [("pred_original_scenario", "Previsão original", "#64748b"),
                                 ("pred_final", "Cenário simulado", "#10b981"),
                                 ("pred_baseline", "Baseline semanal", "#f59e0b"),
                                 ("net", "Real — referência original", "#2563eb")]:
        fig.add_scatter(x=predicted.target_time, y=predicted[column], name=label, line={"color": color})
    fig.add_scatter(x=predicted.target_time, y=predicted.pred_upper, mode="lines", line={"width": 0}, showlegend=False)
    fig.add_scatter(x=predicted.target_time, y=predicted.pred_lower, fill="tonexty", mode="lines", line={"width": 0},
                    name="Faixa empírica 90% — erro histórico", fillcolor="rgba(16,185,129,0.12)")
    fig.update_layout(yaxis_title="MW médios", xaxis_title="Hora de Brasília", template="plotly_white", height=440)
    st.plotly_chart(fig, use_container_width=True)
    st.caption("A faixa usa erros históricos anteriores ao teste; não foi recalibrada para alterações hipotéticas.")
    left, right = st.columns(2)
    with left:
        component = go.Figure()
        for column, label in [("pred_gross", "Bruta prevista"), ("pred_mmgd", "MMGD prevista"), ("pred_decomposed", "Líquida decomposta")]:
            component.add_scatter(x=predicted.target_time, y=predicted[column], name=label)
        component.update_layout(title="Componentes do cenário", yaxis_title="MW médios", height=350)
        st.plotly_chart(component, use_container_width=True)
    with right:
        st.subheader("Desempenho no teste original")
        metrics = pd.read_csv(ARTIFACTS / "reports" / "metrics.csv")
        show = metrics[metrics.horizon.eq(horizon) & metrics.submercado.eq(sub) & metrics.band.isin(["all", "solar_08_16"])]
        st.dataframe(show[["band", "route", "mape_pct", "mae_mw", "improvement_vs_baseline_pct"]], hide_index=True, use_container_width=True)
    with st.expander("Previsões horárias e entradas alteradas"):
        st.dataframe(predicted[["target_time", "temperature", "radiation", "cloud", "humidity", "pred_final", "pred_gross",
                                "pred_mmgd", "pred_direct", "pred_decomposed", "decomposition_weight", "scenario_delta_mw"]], hide_index=True)
    with st.expander("Modelos, decisões e rastreabilidade"):
        st.json({"run_id": bundle.run_id, "selected": bundle.selected, "weights": bundle.blend_weights,
                 "trained_through": bundle.trained_through, "overrides": overrides})
    st.download_button("Baixar todas as informações do cenário (CSV)", predicted.to_csv(index=False).encode("utf-8"),
                       file_name=f"cenario_{sub}_d{horizon}_{target_date}.csv", mime="text/csv")
    st.download_button("Baixar parâmetros do cenário (JSON)", json.dumps({"origin_time": str(origin), "horizon": int(horizon),
        "submercado": sub, "overrides": overrides, "run_id": bundle.run_id}, indent=2, ensure_ascii=False),
        file_name="cenario.json", mime="application/json")


if __name__ == "__main__":
    main()
