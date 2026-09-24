from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from sklearn.ensemble import ExtraTreesRegressor, HistGradientBoostingRegressor, RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from threadpoolctl import threadpool_limits

from .common import TARGETS, timestamp
from .features import feature_columns


def candidate(name, config):
    seed, jobs = config["seed"], config["n_jobs"]
    algorithms = {
        "ridge": lambda: Ridge(alpha=30),
        "extra_trees": lambda: ExtraTreesRegressor(n_estimators=120, max_depth=20, min_samples_leaf=12,
                                                   max_features=.9, n_jobs=jobs, random_state=seed),
        "random_forest": lambda: RandomForestRegressor(n_estimators=80, max_depth=14, min_samples_leaf=20,
                                                        max_features=.8, n_jobs=jobs, random_state=seed),
        "hist_gradient_l1": lambda: HistGradientBoostingRegressor(loss="absolute_error", max_iter=180,
            learning_rate=.07, max_leaf_nodes=15, min_samples_leaf=60, l2_regularization=1,
            max_bins=127, early_stopping=False, random_state=seed),
        "hist_gradient_l2": lambda: HistGradientBoostingRegressor(loss="squared_error", max_iter=250,
            learning_rate=.055, max_leaf_nodes=31, min_samples_leaf=80, l2_regularization=3,
            max_bins=127, early_stopping=False, random_state=seed),
    }
    if name not in algorithms:
        raise ValueError(f"Candidato desconhecido: {name}")
    steps = [("imputer", SimpleImputer(strategy="median", keep_empty_features=True))]
    if name == "ridge":
        steps.append(("scaler", StandardScaler()))
    steps.append(("regressor", algorithms[name]()))
    return Pipeline(steps)


def load_scales(train):
    return train.groupby("submercado").net.median().to_dict()


def scales_for(frame, target, scales):
    return frame.mmgd_scale.to_numpy() if target == "mmgd" else frame.submercado.map(scales).to_numpy()


def fit_model(train, target, horizon, name, config, scales):
    scale = scales_for(train, target, scales)
    residual = (train[target].to_numpy() - train[f"{target}_lag168"].to_numpy()) / scale
    if not np.isfinite(residual).all():
        raise ValueError("Alvos residuais inválidos no treino.")
    estimator = candidate(name, config)
    with threadpool_limits(limits=config["n_jobs"]):
        estimator.fit(train[feature_columns(horizon)], residual)
    return estimator


def predict_component(model, frame, target, horizon, scales, n_jobs=4):
    with threadpool_limits(limits=n_jobs):
        residual = model.predict(frame[feature_columns(horizon)])
    raw = frame[f"{target}_lag168"].to_numpy() + scales_for(frame, target, scales) * residual
    return np.maximum(raw, 0 if target == "mmgd" else 1)


@dataclass
class ForecastBundle:
    models: dict
    scales: dict
    selected: dict
    config: dict
    run_id: str
    trained_through: str
    blend_weights: dict = field(default_factory=dict)
    interval_quantiles: dict = field(default_factory=dict)
    feature_ranges: dict = field(default_factory=dict)

    def predict(self, frame, require_after_training=True):
        if frame.empty:
            raise ValueError("Nenhuma linha para prever.")
        if not frame.feature_eligible.all():
            counts = frame.loc[~frame.feature_eligible, "exclusion_reason"].value_counts().to_dict()
            raise ValueError(f"Features inválidas ou indisponíveis: {counts}")
        if require_after_training and frame.origin_time.min() < timestamp(self.trained_through) + pd.Timedelta(days=1):
            raise ValueError("Origem anterior ao fechamento do treino deste modelo.")
        pieces = []
        for horizon, rows in frame.groupby("horizon", sort=False):
            horizon = int(horizon)
            out = rows.copy()
            for target, output in [("net", "pred_direct"), ("gross", "pred_gross"), ("mmgd", "pred_mmgd")]:
                key = f"{horizon}:{target}"
                out[output] = predict_component(self.models[key], rows, target, horizon, self.scales[str(horizon)], self.config["n_jobs"])
                out[f"model_{target}"] = self.selected[key]
            out["pred_baseline"] = out.net_lag168
            out["pred_decomposed_raw"] = out.pred_gross - out.pred_mmgd
            out["decomposition_clipped"] = out.pred_decomposed_raw.lt(1)
            out["pred_decomposed"] = out.pred_decomposed_raw.clip(lower=1)
            out["decomposition_weight"] = out.is_solar.map(lambda solar: self.blend_weights.get(f"{horizon}:{solar}", 0.0))
            out["pred_final"] = out.decomposition_weight * out.pred_decomposed + (1 - out.decomposition_weight) * out.pred_direct
            q = np.array([self.interval_quantiles.get(f"{horizon}:{sub}:{solar}", np.nan)
                          for sub, solar in zip(out.submercado, out.is_solar)])
            out["pred_lower"] = np.maximum(1, out.pred_final - q)
            out["pred_upper"] = out.pred_final + q
            out["nominal_interval_coverage"] = self.config["interval_coverage"]
            out["run_id"] = self.run_id
            out["model_trained_through"] = self.trained_through
            pieces.append(out)
        return pd.concat(pieces, ignore_index=True).sort_values(["horizon", "origin_time", "submercado", "target_time"]).reset_index(drop=True)
