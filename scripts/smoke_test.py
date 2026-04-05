from __future__ import annotations

import tempfile
from pathlib import Path

import pandas as pd

from core.parser import process_sms_dataframe
from db.session import DataPersistence
from services.analytics import (
    average_daily_spend,
    build_budget_overrun_forecasts,
    calculate_financial_health_score,
    daily_spending_series,
    detect_anomalies,
    predict_next_7_days_spend,
)
from services.budgeting import current_period_status, daily_totals, monthly_totals, weekly_totals


def main() -> None:
    project_root = Path(__file__).resolve().parents[1]
    sample_path = project_root / "sample_sms_upload.csv"
    raw_df = pd.read_csv(sample_path)

    processed = process_sms_dataframe(raw_df, "body", "date", "address")
    processed["date"] = pd.to_datetime(processed["date"], errors="coerce")
    processed["amount"] = pd.to_numeric(processed["amount"], errors="coerce")
    processed = processed.dropna(subset=["date", "amount"]).reset_index(drop=True)

    if processed.empty:
        raise RuntimeError("Smoke test failed: no transactions were parsed from sample data.")

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = str(Path(tmpdir) / "smoke_budget_data.db")
        db = DataPersistence(db_path=db_path)
        db.save_budget("default", "daily", 500.0)
        db.save_budget("default", "weekly", 3500.0)
        db.save_budget("default", "monthly", 15000.0)
        db.save_transactions(processed)

        reloaded = db.get_transactions()
        budgets = db.get_budgets()

    status = current_period_status(
        reloaded,
        budgets["daily"],
        budgets["weekly"],
        budgets["monthly"],
    )
    avg_daily = average_daily_spend(reloaded)
    forecast_df = predict_next_7_days_spend(reloaded)
    anomalies_df = detect_anomalies(reloaded)
    health = calculate_financial_health_score(reloaded, budgets, status)
    overrun = build_budget_overrun_forecasts(status, budgets, avg_daily)

    print("smoke_test: OK")
    print(f"transactions={len(reloaded)}")
    print(f"categories={sorted(reloaded['category'].dropna().unique().tolist())}")
    print(f"daily_rows={len(daily_totals(reloaded))}")
    print(f"weekly_rows={len(weekly_totals(reloaded))}")
    print(f"monthly_rows={len(monthly_totals(reloaded))}")
    print(f"daily_series_rows={len(daily_spending_series(reloaded))}")
    print(f"forecast_rows={len(forecast_df)}")
    print(f"anomalies_rows={len(anomalies_df)}")
    print(f"health_score={health['score']}")
    print(f"overrun_messages={len(overrun)}")


if __name__ == "__main__":
    main()
