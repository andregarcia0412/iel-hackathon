import numpy as np
import pandas as pd


def macro_mape(frame, prediction):
    p = np.asarray(prediction)
    if len(p) != len(frame) or not np.isfinite(p).all() or not frame.net.gt(0).all():
        raise ValueError("MAPE requer predições finitas e alvos positivos alinhados.")
    ape = pd.Series(100 * np.abs(frame.net.to_numpy() - p) / frame.net.to_numpy(), index=frame.index)
    return float(ape.groupby(frame.submercado).mean().mean())


def metric_row(group, column):
    actual, pred = group.net.to_numpy(), group[column].to_numpy()
    error = pred - actual
    abs_error = np.abs(error)
    result = {"n": len(group), "mape_pct": float(np.mean(abs_error / actual) * 100),
              "mae_mw": float(abs_error.mean()), "rmse_mw": float(np.sqrt(np.mean(error**2))),
              "bias_mw": float(error.mean()), "absolute_error_mwh": float(abs_error.sum()),
              "p95_absolute_error_mw": float(np.quantile(abs_error, .95))}
    if "pld_brl_mwh" in group:
        covered = group.pld_brl_mwh.notna()
        result["pld_coverage"] = float(covered.mean())
        result["exposure_proxy_brl"] = float((abs_error[covered] * group.loc[covered, "pld_brl_mwh"]).sum())
    return result


def evaluate(predictions):
    records = []
    for (horizon, sub), group in predictions.groupby(["horizon", "submercado"]):
        bands = {"all": group, "solar_08_16": group[group.is_solar.eq(1)], "other_hours": group[group.is_solar.eq(0)]}
        bands.update({f"hour_{hour:02d}": g for hour, g in group.groupby("hour")})
        for band, part in bands.items():
            if part.empty:
                continue
            baseline = metric_row(part, "pred_baseline")["mape_pct"]
            for route in ["baseline", "direct", "decomposed", "final"]:
                row = metric_row(part, f"pred_{route}")
                row.update(horizon=int(horizon), submercado=sub, band=band, route=route,
                           improvement_vs_baseline_pct=100 * (baseline - row["mape_pct"]) / baseline if baseline else 0)
                if route == "final":
                    row["interval_coverage"] = float(part.net.between(part.pred_lower, part.pred_upper).mean())
                    row["interval_mean_width_mw"] = float((part.pred_upper - part.pred_lower).mean())
                records.append(row)
    return pd.DataFrame(records)
