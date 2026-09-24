"""Extrai a carga bruta prevista pelo modelo para a mesma janela de data/last_month_predictions.csv.

O last_month_predictions.csv só traz a carga líquida; a bruta vem das previsões de teste do modelo.
Uso: uv run python scripts/extract_last_month_components.py
"""

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "hackathon_proenergia" / "artifacts" / "reports" / "test_predictions.csv.gz"
PREDICTIONS = ROOT / "data" / "last_month_predictions.csv"
OUTPUT = ROOT / "data" / "last_month_components.csv"

KEYS = ["target_time", "submercado", "horizon"]


def main() -> None:
    window = pd.read_csv(PREDICTIONS, usecols=KEYS).drop_duplicates()
    components = pd.read_csv(SOURCE, usecols=[*KEYS, "pred_gross"])
    # Mesmas linhas (hora, submercado, horizonte) do last_month_predictions.csv.
    extracted = window.merge(components, on=KEYS, how="left", validate="one_to_one")
    missing = extracted["pred_gross"].isna().sum()
    if missing:
        raise SystemExit(f"{missing} linhas de {PREDICTIONS.name} sem carga bruta em {SOURCE.name}.")
    extracted.to_csv(OUTPUT, index=False)
    print(f"{len(extracted)} linhas gravadas em {OUTPUT.relative_to(ROOT)}.")


if __name__ == "__main__":
    main()
