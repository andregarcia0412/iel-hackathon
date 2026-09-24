from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
ARTIFACTS = ROOT / "hackathon_proenergia" / "artifacts"
SOURCE = ARTIFACTS / "reports" / "test_predictions.csv.gz"
CAPACITY_SOURCE = ARTIFACTS / "prepared" / "capacity_auxiliary.parquet"
PREDICTIONS = ROOT / "data" / "last_month_predictions.csv"
OUTPUT = ROOT / "data" / "last_month_components.csv"
CAPACITY_OUTPUT = ROOT / "data" / "mmgd_capacity.csv"

KEYS = ["target_time", "submercado", "horizon"]
COLUMNS = [
    "pred_gross",
    "pld_brl_mwh",
    "temperature",
    "radiation",
    "weekday",
    "feriado_nacional",
    "carnaval",
    "corpus_christi",
    "emenda",
    "vespera_feriado",
    "pos_feriado",
    "frac_pop_feriado_estadual",
]
CAPACITY_COLUMNS = ["submercado", "mes", "mw_acumulado"]


def main() -> None:
    window = pd.read_csv(PREDICTIONS, usecols=KEYS).drop_duplicates()
    components = pd.read_csv(SOURCE, usecols=[*KEYS, *COLUMNS])
    extracted = window.merge(components, on=KEYS, how="left", validate="one_to_one")
    missing = extracted[COLUMNS].isna().sum()
    if missing.any():
        raise SystemExit(f"Valores ausentes em {SOURCE.name} para {PREDICTIONS.name}: {missing[missing > 0].to_dict()}.")
    extracted[[*KEYS, *COLUMNS]].to_csv(OUTPUT, index=False)
    print(f"{len(extracted)} linhas gravadas em {OUTPUT.relative_to(ROOT)}.")

    capacity = pd.read_parquet(CAPACITY_SOURCE, columns=CAPACITY_COLUMNS)
    capacity.to_csv(CAPACITY_OUTPUT, index=False)
    print(f"{len(capacity)} linhas gravadas em {CAPACITY_OUTPUT.relative_to(ROOT)}.")


if __name__ == "__main__":
    main()
