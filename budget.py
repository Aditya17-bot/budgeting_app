import pandas as pd


def _ensure_datetime(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    if "date" in out.columns:
        out["date"] = pd.to_datetime(out["date"], errors="coerce")
    return out


def daily_totals(df: pd.DataFrame) -> pd.DataFrame:
    expenses = _ensure_datetime(df)
    expenses = expenses[expenses["transaction_type"] == "Expense"].copy()
    expenses = expenses.dropna(subset=["date"])
    expenses["date_only"] = expenses["date"].dt.date
    totals = (
        expenses.groupby("date_only")["amount"].sum().reset_index().rename(columns={"date_only": "date"})
    )
    return totals


def weekly_totals(df: pd.DataFrame) -> pd.DataFrame:
    expenses = _ensure_datetime(df)
    expenses = expenses[expenses["transaction_type"] == "Expense"].copy()
    expenses = expenses.dropna(subset=["date"])
    expenses["week_start"] = expenses["date"].dt.to_period("W-MON").apply(lambda p: p.start_time.date())
    totals = expenses.groupby("week_start")["amount"].sum().reset_index()
    return totals


def monthly_totals(df: pd.DataFrame) -> pd.DataFrame:
    expenses = _ensure_datetime(df)
    expenses = expenses[expenses["transaction_type"] == "Expense"].copy()
    expenses = expenses.dropna(subset=["date"])
    expenses["month_start"] = expenses["date"].dt.to_period("M").apply(lambda p: p.start_time.date())
    totals = expenses.groupby("month_start")["amount"].sum().reset_index()
    return totals


def current_period_status(
    df: pd.DataFrame,
    daily_limit: float,
    weekly_limit: float,
    monthly_limit: float,
) -> dict:
    expenses = _ensure_datetime(df)
    expenses = expenses[expenses["transaction_type"] == "Expense"].copy()
    expenses = expenses.dropna(subset=["date"])

    today = pd.Timestamp.today().normalize()
    week_start = (today - pd.Timedelta(days=today.weekday())).date()
    month_start = today.replace(day=1).date()

    day_total = expenses[expenses["date"].dt.date == today.date()]["amount"].sum()
    week_total = expenses[expenses["date"].dt.date >= week_start]["amount"].sum()
    month_total = expenses[expenses["date"].dt.date >= month_start]["amount"].sum()

    def remaining(limit, total):
        if not limit:
            return None
        return limit - total

    return {
        "day_total": day_total,
        "week_total": week_total,
        "month_total": month_total,
        "day_remaining": remaining(daily_limit, day_total),
        "week_remaining": remaining(weekly_limit, week_total),
        "month_remaining": remaining(monthly_limit, month_total),
    }
