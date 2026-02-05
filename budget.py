import pandas as pd


def daily_totals(df: pd.DataFrame) -> pd.DataFrame:
    expenses = df[df["transaction_type"] == "Expense"].copy()
    expenses = expenses.dropna(subset=["date"])
    expenses["date_only"] = expenses["date"].dt.date
    totals = (
        expenses.groupby("date_only")["amount"].sum().reset_index().rename(columns={"date_only": "date"})
    )
    return totals


def weekly_totals(df: pd.DataFrame) -> pd.DataFrame:
    expenses = df[df["transaction_type"] == "Expense"].copy()
    expenses = expenses.dropna(subset=["date"])
    expenses["week_start"] = expenses["date"].dt.to_period("W-MON").apply(lambda p: p.start_time.date())
    totals = expenses.groupby("week_start")["amount"].sum().reset_index()
    return totals


def check_budget_limits(daily_df: pd.DataFrame, weekly_df: pd.DataFrame, daily_limit: float, weekly_limit: float):
    daily_exceeded = None
    weekly_exceeded = None

    if daily_limit and not daily_df.empty:
        max_daily = daily_df["amount"].max()
        if max_daily > daily_limit:
            daily_exceeded = max_daily

    if weekly_limit and not weekly_df.empty:
        max_weekly = weekly_df["amount"].max()
        if max_weekly > weekly_limit:
            weekly_exceeded = max_weekly

    return daily_exceeded, weekly_exceeded
