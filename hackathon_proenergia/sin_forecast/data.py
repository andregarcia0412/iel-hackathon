from __future__ import annotations

import subprocess
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

from .common import SUBMARKETS, TARGETS, TZ, file_hash, save_json

POPULATION = {
    "Sao Paulo": 11.45, "Rio de Janeiro": 6.21, "Brasilia": 2.82,
    "Belo Horizonte": 2.32, "Goiania": 1.44, "Campo Grande": .90,
    "Cuiaba": .65, "Porto Velho": .46, "Rio Branco": .36, "Vitoria": .32,
    "Curitiba": 1.77, "Porto Alegre": 1.33, "Florianopolis": .54,
    "Fortaleza": 2.43, "Salvador": 2.42, "Recife": 1.49, "Maceio": .96,
    "Teresina": .87, "Joao Pessoa": .83, "Natal": .75, "Aracaju": .60,
    "Manaus": 2.06, "Belem": 1.30, "Sao Luis": 1.04, "Macapa": .44,
    "Boa Vista": .41, "Palmas": .30,
}
CALENDAR_COLUMNS = [
    "feriado_nacional", "carnaval", "corpus_christi", "quarta_cinzas",
    "frac_pop_feriado_estadual", "intensidade_feriado", "emenda", "vespera_feriado", "pos_feriado",
]


def hourly_load(raw: pd.DataFrame):
    d = raw.loc[raw.cod_areacarga.isin(SUBMARKETS)].copy()
    d = d.rename(columns={"cod_areacarga": "submercado", "val_cargaglobalsmmgd": "net",
                          "val_cargaglobal": "gross", "val_cargammgd": "mmgd"})
    d["interval_end"] = pd.to_datetime(d.din_referenciautc, utc=True).dt.tz_convert(TZ)
    d["target_time"] = (d.interval_end - pd.Timedelta(minutes=30)).dt.floor("h")
    if d.duplicated(["submercado", "interval_end"]).any():
        raise ValueError("Carga duplicada: resolver versões explicitamente antes da agregação.")
    identity = (d.gross - d.mmgd - d.net).abs()
    finite = np.isfinite(d[list(TARGETS)]).all(axis=1)
    d["valid_halfhour"] = finite & d.net.gt(0) & d.gross.gt(0) & d.mmgd.ge(0) & identity.le(.01)
    anomalies = d.loc[~d.valid_halfhour, ["submercado", "interval_end", *TARGETS]].copy()
    group = d.groupby(["submercado", "target_time"], observed=True)
    h = group[list(TARGETS)].mean()
    h["halfhour_count"] = group.size()
    h["valid_halfhours"] = group.valid_halfhour.sum()
    if "din_atualizacao" in d:
        h["source_updated_at"] = group.din_atualizacao.max()
    h["quality_ok"] = h.halfhour_count.eq(2) & h.valid_halfhours.eq(2)
    for target in TARGETS:
        h[f"{target}_raw"] = h[target]
        h.loc[~h.quality_ok, target] = np.nan
    h = h.reset_index()
    grid = pd.MultiIndex.from_product([
        SUBMARKETS, pd.date_range(h.target_time.min(), h.target_time.max(), freq="h")
    ], names=["submercado", "target_time"])
    h = h.set_index(["submercado", "target_time"]).reindex(grid).reset_index()
    h["quality_ok"] = h.quality_ok.eq(True)
    report = {
        "selected_halfhours": len(d), "hourly_rows": len(h),
        "invalid_halfhours": len(anomalies), "invalid_hours": int((~h.quality_ok).sum()),
        "max_component_identity_error_mw": float(identity.max()),
        "start": h.target_time.min(), "end": h.target_time.max(),
        "timezone": TZ, "hour_label": "interval_start", "aggregation": "mean_of_two_halfhours",
    }
    return h, anomalies, report


def load_calendar(z: zipfile.ZipFile):
    with z.open("novos/calendario_submercado.csv") as stream:
        c = pd.read_csv(stream)
    c["date"] = pd.to_datetime(c.data).dt.tz_localize(TZ)
    if c.duplicated(["submercado", "date"]).any():
        raise ValueError("Calendário duplicado por data/submercado.")
    if not c.dia_semana.eq(c.date.dt.dayofweek).all():
        raise ValueError("Dia da semana inconsistente no calendário.")
    if c[CALENDAR_COLUMNS].isna().any().any():
        raise ValueError("Calendário incompleto.")
    return c[["submercado", "date", *CALENDAR_COLUMNS]]


def climate_from_raw(path: Path):
    variables = {"temperature": "temperature_2m", "radiation": "shortwave_radiation",
                 "cloud": "cloud_cover", "humidity": "relative_humidity_2m"}
    full_variables = [*variables.values(), "direct_radiation", "diffuse_radiation"]
    selected = ["timestamp", "submercado", "cidade"] + [f"{v}_previous_day{h}" for v in full_variables for h in (1, 7)]
    d = pd.read_csv(path, usecols=selected)
    d["target_time"] = pd.to_datetime(d.timestamp, utc=True).dt.tz_convert(TZ)
    if d.duplicated(["cidade", "target_time"]).any():
        raise ValueError("Clima duplicado por cidade/hora.")
    d["weight"] = d.cidade.map(POPULATION)
    if d.weight.isna().any():
        raise ValueError("Cidade meteorológica sem peso documentado.")
    totals = d[["submercado", "cidade", "weight"]].drop_duplicates().groupby("submercado").weight.sum()
    d["weight"] /= d.submercado.map(totals)
    result, report = [], {}
    for horizon in (1, 7):
        cols = [f"{v}_previous_day{horizon}" for v in full_variables]
        valid = d[cols].notna().all(axis=1)
        agg = pd.DataFrame({"submercado": d.submercado, "target_time": d.target_time})
        agg["missing_weight"] = (~valid) * d.weight
        for new, old in variables.items():
            agg[new] = d[f"{old}_previous_day{horizon}"] * d.weight
        a = agg.groupby(["submercado", "target_time"]).sum(min_count=1).reset_index()
        a["weather_valid"] = a.missing_weight.lt(1e-8)
        radiation = a[["submercado", "target_time", "radiation", "weather_valid"]].copy()
        radiation["target_time"] -= pd.Timedelta(hours=1)
        radiation = radiation.rename(columns={"weather_valid": "radiation_valid"})
        a = a.drop(columns="radiation").merge(radiation, on=["submercado", "target_time"], how="left", validate="one_to_one")
        a["weather_valid"] &= a.radiation_valid.eq(True)
        a["horizon"] = horizon
        a["weather_issued_at_max"] = a.target_time + pd.Timedelta(hours=1) - pd.Timedelta(days=horizon)
        a["weather_source"] = "Open-Meteo Previous Runs; offset nominal; radiação realinhada"
        a.loc[~a.weather_valid, list(variables)] = np.nan
        physical = a.temperature.between(-30, 55) & a.radiation.between(0, 1500) & a.cloud.between(0, 100) & a.humidity.between(0, 100)
        a["weather_valid"] &= physical
        a.loc[~a.weather_valid, list(variables)] = np.nan
        report[str(horizon)] = {"rows": len(a), "valid_rows": int(a.weather_valid.sum()),
                                "first_valid": a.loc[a.weather_valid, "target_time"].min()}
        result.append(a.drop(columns=["radiation_valid", "missing_weight"]))
    return pd.concat(result, ignore_index=True), report


def prepare(root: Path, output: Path):
    datasets, prepared = root / "Datasets", output / "prepared"
    prepared.mkdir(parents=True, exist_ok=True)
    cache = output / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    source = datasets / "dados_clima.7z"
    climate_path = cache / "dados_clima" / "clima_bruto_pontos.csv"
    cache_hash = cache / "climate_source.sha256"
    climate_hash = file_hash(source)
    if not climate_path.exists() or not cache_hash.exists() or cache_hash.read_text().strip() != climate_hash:
        subprocess.run(["7z", "x", str(source), f"-o{cache}", "-y", "-mmt=1",
                        "dados_clima/clima_bruto_pontos.csv", "dados_clima/README.txt"], check=True, timeout=90)
        cache_hash.write_text(climate_hash, encoding="utf-8")
    print("Preparando carga semi-horária...", flush=True)
    parts = [chunk[chunk.cod_areacarga.isin(SUBMARKETS)] for chunk in
             pd.read_csv(datasets / "carga_verificada.csv", chunksize=150_000)]
    hourly, anomalies, load_report = hourly_load(pd.concat(parts, ignore_index=True))
    print("Reconstruindo previsões meteorológicas sem proxies observados...", flush=True)
    weather, weather_report = climate_from_raw(climate_path)
    with zipfile.ZipFile(datasets / "novos.zip") as z:
        calendar = load_calendar(z)
        with z.open("novos/pld_horario_ccee_2023_2026.csv") as stream:
            pld = pd.read_csv(stream)
        with z.open("novos/potencia_mmgd_solar_submercado_mensal.csv") as stream:
            capacity = pd.read_csv(stream)
    pld["target_time"] = (pd.to_datetime(pld.MES_REFERENCIA.astype(str) + pld.DIA.astype(str).str.zfill(2), format="%Y%m%d")
                          + pd.to_timedelta(pld.HORA, unit="h")).dt.tz_localize(TZ)
    pld["submercado"] = pld.SUBMERCADO.map({"NORTE": "N", "NORDESTE": "NE", "SUL": "S", "SUDESTE": "SECO"})
    pld = pld[["submercado", "target_time", "PLD_HORA"]].rename(columns={"PLD_HORA": "pld_brl_mwh"})
    if pld.duplicated(["submercado", "target_time"]).any() or pld.submercado.isna().any():
        raise ValueError("Chaves inválidas no PLD.")
    for name, frame in {"hourly": hourly, "weather": weather, "calendar": calendar,
                        "pld": pld, "capacity_auxiliary": capacity}.items():
        frame.to_parquet(prepared / f"{name}.parquet", index=False)
    anomalies.to_csv(prepared / "load_anomalies.csv", index=False)
    report = {"load": load_report, "weather": weather_report,
              "capacity_policy": "Apenas auditada; não usada como feature sem publicação histórica rastreável.",
              "dessem_policy": "Excluído da comparação: emissão/rodada e alinhamento de alvo não identificados.",
              "population_weights": POPULATION,
              "input_files": {name: {"sha256": file_hash(datasets / name), "bytes": (datasets / name).stat().st_size}
                              for name in ["carga_verificada.csv", "dados_clima.7z", "novos.zip", "DicionarioDados_Carga_Verificada.json"]}}
    save_json(prepared / "data_quality.json", report)
    return hourly, calendar, weather
