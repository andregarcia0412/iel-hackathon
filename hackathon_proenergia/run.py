from __future__ import annotations

import argparse
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="Previsão SIN: dados, AutoML temporal e inferência")
    parser.add_argument("command", choices=["prepare", "train", "predict"])
    parser.add_argument("--config", type=Path, default=Path("config.json"))
    parser.add_argument("--output", type=Path, default=Path("artifacts"))
    parser.add_argument("--reuse-prepared", action="store_true")
    parser.add_argument("--request", type=Path)
    parser.add_argument("--predictions", type=Path, default=Path("artifacts/live_predictions.csv"))
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    if args.command == "predict":
        from sin_forecast.inference import predict_request
        if not args.request:
            parser.error("predict requer --request arquivo.json")
        request = json.loads(args.request.read_text(encoding="utf-8"))
        result = predict_request(request, args.output.resolve())
        args.predictions.parent.mkdir(parents=True, exist_ok=True)
        result.to_csv(args.predictions, index=False)
        print(f"{len(result)} previsões salvas em {args.predictions}")
        return
    from sin_forecast.experiment import prepare_features, run_experiment
    config = json.loads(args.config.read_text(encoding="utf-8"))
    if args.command == "prepare":
        prepare_features(root, args.output.resolve(), config)
    else:
        run_experiment(root, args.output.resolve(), config, reuse=args.reuse_prepared)


if __name__ == "__main__":
    main()
