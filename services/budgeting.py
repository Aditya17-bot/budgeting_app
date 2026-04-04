"""
services/budgeting.py
---------------------
Aggregates expense data into daily / weekly / monthly totals and computes
the current-period spend vs configured budget limits.

Public surface:
    daily_totals(df)                                    -> pd.DataFrame
    weekly_totals(df)                                   -> pd.DataFrame
    monthly_totals(df)                                  -> pd.DataFrame
    current_period_status(df, daily, weekly, monthly)   -> dict
"""

from __future__ import annotations

from typing import Optional

import pandas as pd


# ---------------------------------------------------------------------------
# Internal helper
# ---------------------------------------------------------------------------


def _expenses(df: pd.DataFrame) -> pd.DataFrame:
    """Return a clean expense-only copy of *df* with a parsed date column."""
    out = df.copy()
    if "date" in out.columns:
        out["date"] = pd.to_datetime(out["date"], errors="coerce")
    if "transaction_type" in out.columns:
        out = out[out["transaction_type"] == "Expense"]
    return out.dropna(subset=["date"])


# ---------------------------------------------------------------------------
# Aggregations
# ---------------------------------------------------------------------------


def daily_totals(df: pd.DataFrame) -> pd.DataFrame:
    """Return a DataFrame with columns [date, amount] — one row per calendar day."""
    exp = _expenses(df)
    if exp.empty:
        return pd.DataFrame(columns=["date", "amount"])
    return (
        exp.assign(date=exp["date"].dt.normalize())
        .groupby("date", as_index=False)["amount"]
        .sum()
        .sort_values("date")
        .reset_index(drop=True)
    )


def weekly_totals(df: pd.DataFrame) -> pd.DataFrame:
    """Return a DataFrame with columns [week_start, amount] — one row per ISO week."""
    exp = _expenses(df)
    if exp.empty:
        return pd.DataFrame(columns=["week_start", "amount"])
    exp = exp.copy()
    exp["week_start"] = (
        exp["date"].dt.to_period("W-MON").apply(lambda p: p.start_time.date())
    )
    return (
        exp.groupby("week_start", as_index=False)["amount"]
        .sum()
        .sort_values("week_start")
        .reset_index(drop=True)
    )


def monthly_totals(df: pd.DataFrame) -> pd.DataFrame:
    """Return a DataFrame with columns [month_start, amount] — one row per month."""
    exp = _expenses(df)
    if exp.empty:
        return pd.DataFrame(columns=["month_start", "amount"])
    exp = exp.copy()
    exp["month_start"] = (
        exp["date"].dt.to_period("M").apply(lambda p: p.start_time.date())
    )
    return (
        exp.groupby("month_start", as_index=False)["amount"]
        .sum()
        .sort_values("month_start")
        .reset_index(drop=True)
    )


# ---------------------------------------------------------------------------
# Current-period status
# ---------------------------------------------------------------------------


def current_period_status(
    df: pd.DataFrame,
    daily_limit: float,
    weekly_limit: float,
    monthly_limit: float,
) -> dict:
    """
    Return spending totals and budget headroom for today, this week, and
    this month.

    Week boundary: Monday (ISO week convention).
    Month boundary: 1st of the current calendar month.

    All ``*_remaining`` values are ``None`` when the corresponding limit is 0
    (i.e. unset), so callers can distinguish "no limit" from "₹0 left".
    """
    exp = _expenses(df)

    today       = pd.Timestamp.today().normalize()
    week_start  = (today - pd.Timedelta(days=today.weekday())).date()
    month_start = today.replace(day=1).date()

    day_total   = float(exp[exp["date"].dt.date == today.date()]["amount"].sum())
    week_total  = float(exp[exp["date"].dt.date >= week_start]["amount"].sum())
    month_total = float(exp[exp["date"].dt.date >= month_start]["amount"].sum())

    def _remaining(limit: float, total: float) -> Optional[float]:
        return (limit - total) if limit > 0 else None

    return {
        "day_total":       day_total,
        "week_total":      week_total,
        "month_total":     month_total,
        "day_remaining":   _remaining(daily_limit,   day_total),
        "week_remaining":  _remaining(weekly_limit,  week_total),
        "month_remaining": _remaining(monthly_limit, month_total),
    }