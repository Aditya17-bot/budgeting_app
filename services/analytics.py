"""
services/analytics.py
----------------------
Analytics, forecasting, anomaly detection, and financial health scoring.

Public surface:
    daily_spending_series(df)                       -> pd.DataFrame
    predict_next_7_days_spend(df)                   -> pd.DataFrame
    average_daily_spend(df, window)                 -> float
    detect_anomalies(df)                            -> pd.DataFrame
    calculate_financial_health_score(df, ...)       -> dict
    budget_overrun_forecast(...)                    -> dict
    build_budget_overrun_forecasts(...)             -> list[dict]
"""

from __future__ import annotations

import math
from datetime import timedelta
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _expense_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Return a clean expenses-only copy of *df*."""
    if df.empty:
        return df.copy()

    out = df.copy()
    if "transaction_type" in out.columns:
        out = out[out["transaction_type"] == "Expense"]
    if "date" in out.columns:
        out["date"] = pd.to_datetime(out["date"], errors="coerce")
        out = out.dropna(subset=["date"])
    if "amount" in out.columns:
        out["amount"] = pd.to_numeric(out["amount"], errors="coerce")
        out = out.dropna(subset=["amount"])
    return out.copy()


def _fill_date_gaps(daily: pd.DataFrame) -> pd.DataFrame:
    """Reindex *daily* to a continuous date range, filling missing days with 0."""
    if daily.empty:
        return daily
    full_range = pd.date_range(daily["date"].min(), daily["date"].max(), freq="D")
    return (
        daily
        .set_index("date")
        .reindex(full_range, fill_value=0.0)
        .rename_axis("date")
        .reset_index()
    )


def _iqr_bounds(series: pd.Series) -> Tuple[float, float]:
    """Return (lower, upper) IQR fences for outlier detection."""
    q1, q3 = series.quantile(0.25), series.quantile(0.75)
    iqr = q3 - q1
    return q1 - 1.5 * iqr, q3 + 1.5 * iqr


def _z_score(series: pd.Series, value: float) -> float:
    std = series.std(ddof=0)
    if std == 0:
        return 0.0
    return (value - series.mean()) / std


# ---------------------------------------------------------------------------
# Spending series
# ---------------------------------------------------------------------------


def daily_spending_series(df: pd.DataFrame) -> pd.DataFrame:
    """
    Return a DataFrame with columns [date, amount] — one row per calendar day,
    summing all expenses. Days with no spending are NOT filled here (use
    _fill_date_gaps when continuity is needed).
    """
    expenses = _expense_frame(df)
    if expenses.empty:
        return pd.DataFrame(columns=["date", "amount"])

    return (
        expenses
        .assign(date=expenses["date"].dt.normalize())
        .groupby("date", as_index=False)["amount"]
        .sum()
        .sort_values("date")
        .reset_index(drop=True)
    )


# ---------------------------------------------------------------------------
# Forecasting
# ---------------------------------------------------------------------------


def predict_next_7_days_spend(df: pd.DataFrame, window: int = 14) -> pd.DataFrame:
    """
    Forecast daily spend for the next 7 days using a linear trend fitted on
    the most recent *window* days of history, blended with a weighted moving
    average (recent days count more).

    Falls back to a simple weighted average when fewer than 3 data points
    exist, and returns an empty DataFrame when there is no history at all.
    """
    daily = daily_spending_series(df)
    if daily.empty:
        return pd.DataFrame(columns=["date", "predicted_amount"])

    history = _fill_date_gaps(daily)
    lookback = history.tail(max(3, min(window, len(history)))).copy().reset_index(drop=True)
    last_date = history["date"].max()

    amounts = lookback["amount"].values
    n = len(amounts)

    # Weighted moving average — weights increase linearly toward the most recent day
    weights = np.arange(1, n + 1, dtype=float)
    weights /= weights.sum()
    wma = float(np.dot(weights, amounts))

    # Linear trend via least-squares
    slope = 0.0
    if n >= 3:
        x = np.arange(n, dtype=float)
        x -= x.mean()
        y = amounts - amounts.mean()
        denom = float(np.dot(x, x))
        if denom > 0:
            slope = float(np.dot(x, y) / denom)

    # Blend: 70 % WMA base + 30 % trend extrapolation, clamped to ≥ 0
    rows = []
    for offset in range(1, 8):
        trend_component = slope * offset
        predicted = max(0.0, wma + 0.3 * trend_component)
        rows.append({
            "date": last_date + timedelta(days=offset),
            "predicted_amount": round(predicted, 2),
        })

    return pd.DataFrame(rows)


def average_daily_spend(df: pd.DataFrame, window: int = 14) -> float:
    """Return weighted average daily spend over the last *window* days."""
    daily = daily_spending_series(df)
    if daily.empty:
        return 0.0

    history = _fill_date_gaps(daily)
    lookback = history.tail(max(1, min(window, len(history))))
    amounts = lookback["amount"].values
    weights = np.arange(1, len(amounts) + 1, dtype=float)
    weights /= weights.sum()
    return float(np.dot(weights, amounts))


# ---------------------------------------------------------------------------
# Anomaly detection
# ---------------------------------------------------------------------------


def detect_anomalies(df: pd.DataFrame) -> pd.DataFrame:
    """
    Detect anomalous expense transactions using a two-stage approach:

    1.  **IQR fence** (per category) — flags transactions above the upper
        Tukey fence within their category, so a ₹5,000 dinner is compared
        to other dinners, not to a ₹300 coffee.

    2.  **Z-score guard** (global) — any transaction with z > 2.5 across
        *all* expenses is flagged regardless of category, catching
        rare high-value one-offs in thin categories.

    A transaction must breach at least one of these to be reported.
    The result is deduplicated and sorted by amount descending.
    """
    expenses = _expense_frame(df)
    if expenses.empty:
        return pd.DataFrame(columns=list(df.columns) + ["z_score", "threshold", "flag_reason"])

    amounts = expenses["amount"]
    global_mean = float(amounts.mean())
    global_std  = float(amounts.std(ddof=0)) if len(amounts) > 1 else 0.0

    flagged_indices: set = set()
    flag_reasons: Dict[int, str] = {}
    thresholds:   Dict[int, float] = {}

    # Stage 1 — per-category IQR
    if "category" in expenses.columns:
        for cat, group in expenses.groupby("category"):
            if len(group) < 4:
                # Too few samples for a reliable IQR fence — skip category filter,
                # let the global z-score handle these.
                continue
            _, upper = _iqr_bounds(group["amount"])
            over = group[group["amount"] > max(upper, 0)]
            for idx in over.index:
                flagged_indices.add(idx)
                flag_reasons[idx] = f"Above IQR fence for {cat}"
                thresholds[idx]   = round(upper, 2)

    # Stage 2 — global z-score
    if global_std > 0:
        for idx, row in expenses.iterrows():
            z = (row["amount"] - global_mean) / global_std
            if z > 2.5:
                flagged_indices.add(idx)
                if idx not in flag_reasons:
                    flag_reasons[idx] = "Unusually high (z-score)"
                    thresholds[idx]   = round(global_mean + 2.5 * global_std, 2)

    if not flagged_indices:
        return pd.DataFrame(columns=list(df.columns) + ["z_score", "threshold", "flag_reason"])

    result = expenses.loc[list(flagged_indices)].copy()
    result["z_score"]     = result["amount"].apply(
        lambda a: round(_z_score(amounts, a), 2)
    )
    result["threshold"]   = result.index.map(thresholds)
    result["flag_reason"] = result.index.map(flag_reasons)
    result["global_mean"] = round(global_mean, 2)

    return result.sort_values("amount", ascending=False).reset_index(drop=True)


# ---------------------------------------------------------------------------
# Financial health score
# ---------------------------------------------------------------------------


def calculate_financial_health_score(
    df: pd.DataFrame,
    budget_limits: Dict[str, float],
    current_status: Dict[str, float],
) -> Dict[str, object]:
    """
    Compute a 0–100 financial health score from three components:

    - **Savings ratio** (40 %) — (income − expenses) / income.
    - **Budget adherence** (35 %) — how far under limits the current periods are.
    - **Spending consistency** (25 %) — inverse of the coefficient of variation
      in daily spend; lower volatility → higher score.
    """
    working = df.copy()
    if "amount" in working.columns:
        working["amount"] = pd.to_numeric(working["amount"], errors="coerce")
        working = working.dropna(subset=["amount"])

    expenses = _expense_frame(working)
    income   = (
        working[working["transaction_type"] == "Income"].copy()
        if "transaction_type" in working.columns
        else pd.DataFrame()
    )

    total_expenses = float(expenses["amount"].sum()) if not expenses.empty else 0.0
    total_income   = float(income["amount"].sum())   if not income.empty   else 0.0

    # Savings ratio score
    savings_ratio = (
        max(0.0, (total_income - total_expenses) / total_income)
        if total_income > 0
        else 0.0
    )
    savings_score = min(100.0, savings_ratio * 100)

    # Budget adherence score
    adherence_parts: list[float] = []
    for limit_key, status_key in [
        ("daily", "day_total"),
        ("weekly", "week_total"),
        ("monthly", "month_total"),
    ]:
        limit = float(budget_limits.get(limit_key) or 0.0)
        spent = float(current_status.get(status_key) or 0.0)
        if limit > 0:
            adherence_parts.append(max(0.0, min(100.0, (limit - spent) / limit * 100)))

    budget_adherence_score = (
        sum(adherence_parts) / len(adherence_parts) if adherence_parts else 50.0
    )

    # Spending consistency score (lower CV → higher score, capped)
    daily = daily_spending_series(working)
    if not daily.empty and len(daily) > 1:
        history = _fill_date_gaps(daily)
        mean = float(history["amount"].mean())
        if mean > 0:
            cv = float(history["amount"].std(ddof=0) / mean)
            spending_consistency_score = max(0.0, min(100.0, 100.0 - cv * 35.0))
        else:
            spending_consistency_score = 100.0
    else:
        spending_consistency_score = 50.0

    overall = (
        savings_score              * 0.40
        + budget_adherence_score   * 0.35
        + spending_consistency_score * 0.25
    )

    label = (
        "Excellent"       if overall >= 80 else
        "Good"            if overall >= 65 else
        "Fair"            if overall >= 50 else
        "Needs Attention"
    )

    return {
        "score":         round(overall, 1),
        "label":         label,
        "savings_ratio": round(savings_ratio * 100, 1),
        "components": {
            "savings_ratio_score":        round(savings_score, 1),
            "budget_adherence_score":     round(budget_adherence_score, 1),
            "spending_consistency_score": round(spending_consistency_score, 1),
        },
        "totals": {
            "income":   round(total_income, 2),
            "expenses": round(total_expenses, 2),
        },
    }


# ---------------------------------------------------------------------------
# Budget overrun forecasting
# ---------------------------------------------------------------------------


def budget_overrun_forecast(
    current_spend: float,
    budget_limit: float,
    avg_daily_spend: float,
    budget_name: str,
) -> Dict[str, object]:
    """
    Estimate when (if ever) *current_spend* will exceed *budget_limit*
    given *avg_daily_spend*.
    """
    if budget_limit <= 0:
        return {
            "budget_name": budget_name,
            "will_exceed": False,
            "days_to_exceed": None,
            "message": f"No {budget_name.lower()} budget configured.",
        }

    remaining = budget_limit - current_spend
    if remaining <= 0:
        return {
            "budget_name": budget_name,
            "will_exceed": True,
            "days_to_exceed": 0,
            "message": f"You have already exceeded your {budget_name.lower()} budget.",
        }

    if avg_daily_spend <= 0:
        return {
            "budget_name": budget_name,
            "will_exceed": False,
            "days_to_exceed": None,
            "message": f"Spend rate too low to forecast a {budget_name.lower()} overrun.",
        }

    days = math.ceil(remaining / avg_daily_spend)
    return {
        "budget_name": budget_name,
        "will_exceed": True,
        "days_to_exceed": days,
        "message": f"At your current rate you will exceed your {budget_name.lower()} budget in {days} day(s).",
    }


def build_budget_overrun_forecasts(
    current_status: Dict[str, float],
    budget_limits: Dict[str, float],
    avg_daily_spend_value: float,
) -> List[Dict[str, object]]:
    """Return overrun forecasts for daily, weekly, and monthly budgets."""
    periods = [
        ("Daily",   "day_total",   "daily"),
        ("Weekly",  "week_total",  "weekly"),
        ("Monthly", "month_total", "monthly"),
    ]
    return [
        budget_overrun_forecast(
            current_status.get(status_key, 0.0),
            budget_limits.get(limit_key, 0.0),
            avg_daily_spend_value,
            name,
        )
        for name, status_key, limit_key in periods
    ]