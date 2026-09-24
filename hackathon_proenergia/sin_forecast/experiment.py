from __future__ import annotations

import gc
import itertools
import json
import platform
import time
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from .common import LIMITATIONS, SUBMARKETS, TARGETS, file_hash, save_json, versions
from .data import prepare
from .features import add_splits, assert_temporal_contract, feature_columns, make_features
from .metrics import evaluate, macro_mape
from .models import ForecastBundle, fit_model, load_scales, predict_component


def prepare_features(root, output, config):
    hourly, calendar, weather = prepare(root, output)
    tables = []
    for horizon in config["horizons"]:
        print(f"Features causais D+{horizon}...", flush=True)
        f = add_splits(make_features(hourly, calendar, weather, horizon), config)
        assert_temporal_contract(f, horizon)
        f.to_parquet(output / "prepared" / f"features_d{horizon}.parquet", index=False)
        tables.append(f)
    all_features = pd.concat(tables, ignore_index=True)
    coverage = all_features.groupby(["horizon", "split"], observed=True).agg(
        total=("target_time", "size"), eligible=("evaluation_eligible", "sum"),
        first_target=("target_time", "min"), last_target=("target_time", "max"),
        first_origin=("origin_time", "min"), last_origin=("origin_time", "max"),
    ).reset_index()
    coverage.to_csv(output / "prepared" / "split_coverage.csv", index=False)
    excluded = all_features.loc[~all_features.evaluation_eligible & all_features.split.ne("unused"),
                                ["horizon", "split", "submercado", "origin_time", "target_time", "exclusion_reason"]]
    excluded.to_csv(output / "prepared" / "excluded_rows.csv", index=False)
    save_json(output / "prepared" / "preparation_config.json", config)
    return all_features


def get_features(root, output, config, reuse):
    if reuse:
        saved = json.loads((output / "prepared" / "preparation_config.json").read_text())
        if saved != config:
            raise ValueError("Configuração difere da preparação salva. Execute sem --reuse-prepared.")
        quality = json.loads((output / "prepared" / "data_quality.json").read_text())
        for name, info in quality["input_files"].items():
            if file_hash(root / "Datasets" / name) != info["sha256"]:
                raise ValueError(f"Fonte mudou desde a preparação: {name}")
        return pd.concat([pd.read_parquet(output / "prepared" / f"features_d{h}.parquet") for h in config["horizons"]], ignore_index=True)
    return prepare_features(root, output, config)


def search_models(features, output, config, run_id):
    search_dir = output / "search"
    search_dir.mkdir(parents=True, exist_ok=True)
    trials, combinations, selected, all_scales, models = [], [], {}, {}, {}
    for horizon in config["horizons"]:
        eligible = features[features.horizon.eq(horizon) & features.evaluation_eligible]
        train, tune = [eligible[eligible.split.eq(split)].copy() for split in ("train", "tune")]
        if train.empty or tune.empty:
            raise ValueError("Treino/validação vazios.")
        scales = load_scales(train)
        all_scales[str(horizon)] = scales
        predictions = {}
        validation_predictions = tune[["origin_time", "target_time", "submercado", "horizon", *TARGETS]].copy()
        for target in TARGETS:
            for name in config["candidates"]:
                started = time.monotonic()
                key = f"{target}:{name}"
                print(f"AutoML D+{horizon} | {target} | {name}", flush=True)
                model = fit_model(train, target, horizon, name, config, scales)
                prediction = predict_component(model, tune, target, horizon, scales, config["n_jobs"])
                predictions[key] = prediction
                validation_predictions[key] = prediction
                row = {"horizon": horizon, "target": target, "candidate": name, "status": "success",
                       "train_n": len(train), "validation_n": len(tune), "elapsed_seconds": time.monotonic() - started,
                       "component_mae_mw": float(np.abs(tune[target].to_numpy() - prediction).mean()),
                       "net_macro_mape_pct": macro_mape(tune, prediction) if target == "net" else None,
                       "params": json.dumps(model.named_steps["regressor"].get_params(), sort_keys=True)}
                trials.append(row)
                joblib.dump(model, search_dir / f"d{horizon}_{target}_{name}.joblib", compress=3)
                pd.DataFrame(trials).to_csv(search_dir / "trials.csv", index=False)
                del model
                gc.collect()
        best_direct = min(config["candidates"], key=lambda name: macro_mape(tune, predictions[f"net:{name}"]))
        best_pair, best_score = None, float("inf")
        for gross_name, mmgd_name in itertools.product(config["candidates"], repeat=2):
            net = np.maximum(1, predictions[f"gross:{gross_name}"] - predictions[f"mmgd:{mmgd_name}"])
            score = macro_mape(tune, net)
            combinations.append({"horizon": horizon, "gross_candidate": gross_name, "mmgd_candidate": mmgd_name,
                                 "net_macro_mape_pct": score})
            if score < best_score:
                best_pair, best_score = (gross_name, mmgd_name), score
        for target, name in zip(TARGETS, [best_direct, *best_pair]):
            selected[f"{horizon}:{target}"] = name
            models[f"{horizon}:{target}"] = joblib.load(search_dir / f"d{horizon}_{target}_{name}.joblib")
        validation_predictions.to_parquet(search_dir / f"tuning_predictions_d{horizon}.parquet", index=False)
        print(f"Selecionados D+{horizon}: direta={best_direct}; decomposição={best_pair}, MAPE={best_score:.3f}%", flush=True)
    pd.DataFrame(combinations).to_csv(search_dir / "decomposition_combinations.csv", index=False)
    save_json(search_dir / "selected_models.json", selected)
    return ForecastBundle(models, all_scales, selected, config, run_id, config["train_end"])


def select_blend_and_calibrate(bundle, features, output):
    selection = features[features.split.eq("selection") & features.evaluation_eligible]
    predictions = bundle.predict(selection)
    grid = []
    for (horizon, solar), rows in predictions.groupby(["horizon", "is_solar"]):
        scores = []
        for weight in bundle.config["blend_grid"]:
            score = macro_mape(rows, weight * rows.pred_decomposed + (1 - weight) * rows.pred_direct)
            scores.append((score, weight))
            grid.append({"horizon": int(horizon), "is_solar": int(solar), "weight": weight, "macro_mape_pct": score})
        bundle.blend_weights[f"{horizon}:{solar}"] = min(scores)[1]
    pd.DataFrame(grid).to_csv(output / "search" / "blend_search.csv", index=False)
    predictions = bundle.predict(selection)
    predictions.to_parquet(output / "search" / "selection_predictions.parquet", index=False)
    calibration = features[features.split.eq("calibration") & features.evaluation_eligible]
    cp = bundle.predict(calibration)
    cp["absolute_error"] = (cp.net - cp.pred_final).abs()
    for (h, sub, solar), rows in cp.groupby(["horizon", "submercado", "is_solar"]):
        coverage = min(1, np.ceil((len(rows) + 1) * bundle.config["interval_coverage"]) / len(rows))
        bundle.interval_quantiles[f"{h}:{sub}:{solar}"] = float(rows.absolute_error.quantile(coverage, interpolation="higher"))
    bundle.predict(calibration).to_parquet(output / "search" / "calibration_predictions.parquet", index=False)
    save_json(output / "search" / "frozen_decisions.json", {
        "selected": bundle.selected, "blend_weights": bundle.blend_weights,
        "interval_quantiles": bundle.interval_quantiles,
        "calibration_note": "Quantis empíricos com modelo pré-reajuste; medir cobertura após reajuste no teste.",
    })
    return bundle


def refit(bundle, features, output):
    for horizon in bundle.config["horizons"]:
        train = features[features.horizon.eq(horizon) & features.refit_eligible]
        scales = load_scales(train)
        bundle.scales[str(horizon)] = scales
        for col in feature_columns(horizon):
            values = train[col].dropna()
            bundle.feature_ranges[f"{horizon}:{col}"] = [float(values.min()), float(values.max())] if len(values) else [0.0, 0.0]
        for target in TARGETS:
            key = f"{horizon}:{target}"
            print(f"Reajuste final D+{horizon} | {target} | {bundle.selected[key]}", flush=True)
            bundle.models[key] = fit_model(train, target, horizon, bundle.selected[key], bundle.config, scales)
    bundle.trained_through = bundle.config["refit_end"]
    models_dir = output / "models"
    models_dir.mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle, models_dir / "forecast_bundle.joblib", compress=3)
    loaded = joblib.load(models_dir / "forecast_bundle.joblib")
    sample = features[features.split.eq("test") & features.evaluation_eligible].groupby("horizon").head(24)
    np.testing.assert_allclose(bundle.predict(sample).pred_final, loaded.predict(sample).pred_final, rtol=0, atol=1e-9)
    return loaded


def export_results(bundle, features, output):
    report_dir = output / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    test = features[features.split.eq("test") & features.evaluation_eligible].copy()
    print(f"Avaliando teste congelado: {len(test):,} previsões...", flush=True)
    predictions = bundle.predict(test)
    pld = pd.read_parquet(output / "prepared" / "pld.parquet")
    predictions = predictions.merge(pld, on=["submercado", "target_time"], how="left", validate="many_to_one")
    for route in ["baseline", "direct", "decomposed", "final"]:
        predictions[f"error_{route}_mw"] = predictions[f"pred_{route}"] - predictions.net
        predictions[f"absolute_error_{route}_mw"] = predictions[f"error_{route}_mw"].abs()
        predictions[f"ape_{route}_pct"] = 100 * predictions[f"absolute_error_{route}_mw"] / predictions.net
    for target in ["gross", "mmgd"]:
        predictions[f"error_{target}_mw"] = predictions[f"pred_{target}"] - predictions[target]
    predictions["interval_contains_actual"] = predictions.net.between(predictions.pred_lower, predictions.pred_upper)
    predictions["evaluation_generated_at"] = datetime.now(timezone.utc).isoformat()
    predictions.to_parquet(report_dir / "test_predictions.parquet", index=False)
    predictions.to_csv(report_dir / "test_predictions.csv.gz", index=False, compression="gzip")
    metrics = evaluate(predictions)
    metrics.to_csv(report_dir / "metrics.csv", index=False)
    macro = metrics[metrics.band.isin(["all", "solar_08_16", "other_hours"])].groupby(["horizon", "band", "route"])["mape_pct"].mean().reset_index()
    macro.to_csv(report_dir / "macro_metrics.csv", index=False)
    component_metrics = predictions.groupby(["horizon", "submercado"]).agg(
        gross_mae_mw=("error_gross_mw", lambda s: s.abs().mean()), mmgd_mae_mw=("error_mmgd_mw", lambda s: s.abs().mean()),
        decomposition_clipped=("decomposition_clipped", "sum"), interval_coverage=("interval_contains_actual", "mean"),
    ).reset_index()
    component_metrics.to_csv(report_dir / "component_metrics.csv", index=False)
    daily = predictions.groupby(["horizon", "submercado", "origin_time"]).agg(
        hours=("target_time", "size"), mape_baseline=("ape_baseline_pct", "mean"), mape_final=("ape_final_pct", "mean"),
    ).reset_index()
    daily.to_csv(report_dir / "daily_metrics.csv", index=False)
    predictions.nlargest(100, "ape_final_pct").to_csv(report_dir / "worst_100_predictions.csv", index=False)
    create_card(bundle, macro, metrics, component_metrics, report_dir)
    create_plots(predictions, metrics, report_dir)
    return predictions, metrics


def create_card(bundle, macro, metrics, components, directory):
    lines = ["# Resultado — previsão de carga do SIN", "", f"Execução: `{bundle.run_id}`.",
             f"Teste: {bundle.config['test_start']} a {bundle.config['test_end']}. Treino final até {bundle.trained_through}.", "",
             "MAPE macro: média simples dos quatro submercados. Núcleo solar: 08h–16h de Brasília.", "",
             "| Horizonte | Faixa | Baseline | Direta | Decomposta | Final | Ganho relativo final |", "|---|---|---:|---:|---:|---:|---:|"]
    for (h, band), rows in macro.groupby(["horizon", "band"]):
        values = rows.set_index("route").mape_pct.to_dict()
        gain = 100 * (1 - values["final"] / values["baseline"])
        lines.append(f"| D+{h} | {band} | {values['baseline']:.3f}% | {values['direct']:.3f}% | {values['decomposed']:.3f}% | {values['final']:.3f}% | {gain:.2f}% |")
    lines += ["", "## Volume de erro e exposição teórica", ""]
    for h in bundle.config["horizons"]:
        rows = metrics[metrics.horizon.eq(h) & metrics.band.eq("all")]
        sums = rows.groupby("route")[["absolute_error_mwh", "exposure_proxy_brl"]].sum()
        reduction = sums.loc["baseline"] - sums.loc["final"]
        lines += [f"- D+{h}: redução de {reduction.absolute_error_mwh:,.0f} MWh no volume absoluto de erro; "
                  f"redução de R$ {reduction.exposure_proxy_brl:,.0f} na exposição teórica valorada ao PLD."]
    lines += ["", "Essas quantidades não representam energia economizada ou lucro realizado. Os horizontes não devem ser somados.",
              "", "## Onde falha / limitações", "", *[f"- {note}" for note in LIMITATIONS], "",
              "## Rastreabilidade", "", "- `search/trials.csv`: candidatos, parâmetros, tempo e métricas de validação.",
              "- `reports/test_predictions.parquet`: features, origens, alvos, componentes, erros e intervalos por hora.",
              "- `prepared/excluded_rows.csv`: observações excluídas e motivos.",
              "- `manifest.json`: fontes, versões, decisões e hashes."]
    (directory / "result_card.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def create_plots(predictions, metrics, directory):
    import plotly.express as px
    import plotly.graph_objects as go

    for h in sorted(predictions.horizon.unique()):
        selected = predictions[predictions.horizon.eq(h) & predictions.submercado.eq("S")]
        end = selected.target_time.min() + pd.Timedelta(days=7)
        selected = selected[selected.target_time.lt(end)]
        fig = go.Figure()
        for column, name in [("net", "Real"), ("pred_baseline", "Semana anterior"), ("pred_direct", "Direta"),
                             ("pred_decomposed", "Decomposta"), ("pred_final", "Final")]:
            fig.add_scatter(x=selected.target_time, y=selected[column], name=name)
        fig.update_layout(title=f"Sul — primeira semana do teste — D+{h}", yaxis_title="MW médios", template="plotly_white")
        fig.write_html(directory / f"week_d{h}.html", include_plotlyjs=True)
        rows = metrics[metrics.horizon.eq(h) & metrics.route.eq("final") & metrics.band.str.startswith("hour_")]
        pivot = rows.pivot(index="submercado", columns="band", values="improvement_vs_baseline_pct")
        heatmap = px.imshow(pivot, color_continuous_scale="RdYlGn", color_continuous_midpoint=0,
                            title=f"Ganho relativo sobre baseline por hora (%) — D+{h}", aspect="auto")
        heatmap.write_html(directory / f"hourly_gain_d{h}.html", include_plotlyjs=True)


def run_experiment(root: Path, output: Path, config, reuse=False):
    output.mkdir(parents=True, exist_ok=True)
    if (output / "manifest.json").exists():
        raise ValueError("Esta saída já contém um teste final. Use outro --output para uma nova execução identificada.")
    started = time.monotonic()
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    save_json(output / "run_config.json", config)
    features = get_features(root, output, config, reuse)
    bundle = search_models(features, output, config, run_id)
    bundle = select_blend_and_calibrate(bundle, features, output)
    bundle = refit(bundle, features, output)
    predictions, metrics = export_results(bundle, features, output)
    code_paths = [*sorted((root / "sin_forecast").glob("*.py")), root / "run.py", root / "app.py"]
    manifest = {"run_id": run_id, "config": config, "versions": versions(), "python": platform.python_version(),
                "elapsed_seconds": time.monotonic() - started, "limitations": LIMITATIONS,
                "selected": bundle.selected, "blend_weights": bundle.blend_weights,
                "feature_columns": {str(h): feature_columns(h) for h in config["horizons"]},
                "interval_quantiles": bundle.interval_quantiles, "test_rows": len(predictions),
                "sources": json.loads((output / "prepared" / "data_quality.json").read_text()),
                "code_sha256": {str(p.relative_to(root)): file_hash(p) for p in code_paths if p.exists()},
                "model_sha256": file_hash(output / "models" / "forecast_bundle.joblib")}
    save_json(output / "manifest.json", manifest)
    print(metrics[metrics.band.eq("all")][["horizon", "submercado", "route", "mape_pct"]].to_string(index=False), flush=True)
    print(f"Concluído em {manifest['elapsed_seconds']:.1f}s. Artefatos: {output}", flush=True)
    return bundle
