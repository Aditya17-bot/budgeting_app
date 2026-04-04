"""
api/main.py
-----------
FastAPI application for the SMS Budget Tracker.

Endpoints:
    POST   /upload-sms
    GET    /transactions
    GET    /transactions/stats
    GET    /budget/status
    GET    /budget/limits
    POST   /budget/limits
    GET    /categories
    DELETE /data
"""

from __future__ import annotations

import io
from datetime import datetime
from typing import List, Optional

import pandas as pd
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from api.webhook import router as webhook_router
from core.parser import load_sms_xml, process_sms_dataframe
from db.session import DataPersistence
from services.budgeting import current_period_status   # fixed: was `from budget import ...`

# ---------------------------------------------------------------------------
# Pydantic models (moved inline — db.models does not exist in file tree)
# ---------------------------------------------------------------------------


class BudgetLimit(BaseModel):
    period:       str    # "daily" | "weekly" | "monthly"
    limit_amount: float


class BudgetStatus(BaseModel):
    daily_spent:      float
    daily_remaining:  Optional[float]
    weekly_spent:     float
    weekly_remaining: Optional[float]
    monthly_spent:    float
    monthly_remaining: Optional[float]


class TransactionResponse(BaseModel):
    id:               Optional[int]   = None
    date:             Optional[str]   = None
    amount:           float
    transaction_type: str
    category:         str
    merchant:         Optional[str]   = None
    original_message: Optional[str]   = None


# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

app = FastAPI(title="SMS Budget Tracker API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(webhook_router)

db = DataPersistence()

# ---------------------------------------------------------------------------
# Column detection helper (mirrors Streamlit logic)
# ---------------------------------------------------------------------------

_MESSAGE_CANDIDATES = ["body", "content", "message", "sms", "text"]
_DATE_CANDIDATES    = ["date", "readable_date", "datetime", "timestamp", "time"]
_SENDER_CANDIDATES  = ["address", "sender", "from", "contact_name"]


def _first_match(columns: list[str], candidates: list[str]) -> Optional[str]:
    lowered = {c.lower(): c for c in columns}
    for key in candidates:
        if key in lowered:
            return lowered[key]
    return None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/")
async def root():
    return {"message": "SMS Budget Tracker API", "version": "1.0.0", "status": "ok"}


@app.post("/upload-sms")
async def upload_sms(file: UploadFile = File(...)):
    """
    Accept a CSV or XML SMS export, parse transactions, persist to DB.
    Returns a summary and the first five parsed transactions.
    """
    try:
        content  = await file.read()
        file_io  = io.BytesIO(content)
        filename = (file.filename or "").lower()

        df = load_sms_xml(file_io) if filename.endswith(".xml") else pd.read_csv(file_io)

        cols        = list(df.columns)
        message_col = _first_match(cols, _MESSAGE_CANDIDATES)
        date_col    = _first_match(cols, _DATE_CANDIDATES)
        sender_col  = _first_match(cols, _SENDER_CANDIDATES)

        if not message_col or not date_col:
            raise HTTPException(
                status_code=400,
                detail="Could not detect required columns (message body / date).",
            )

        processed = process_sms_dataframe(df, message_col, date_col, sender_col)
        if processed.empty:
            return {"message": "No financial transactions found", "count": 0}

        saved_count = db.save_transactions(processed)

        # Serialize sample safely
        sample = processed.head(5).copy()
        if "date" in sample.columns:
            sample["date"] = sample["date"].astype(str)
        sample_records = sample.to_dict("records")

        return {
            "message":             f"Successfully processed {len(processed)} transactions",
            "count":               len(processed),
            "total_in_db":         saved_count,
            "sample_transactions": sample_records,
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error processing file: {exc}") from exc


@app.get("/transactions", response_model=List[TransactionResponse])
async def get_transactions(
    limit:            Optional[int] = 100,
    category:         Optional[str] = None,
    transaction_type: Optional[str] = None,
):
    """Return paginated transactions, optionally filtered by category or type."""
    try:
        df = db.get_transactions(category=category, transaction_type=transaction_type)
        if limit:
            df = df.head(limit)
        if "date" in df.columns:
            df["date"] = df["date"].astype(str)
        return df.to_dict("records")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error fetching transactions: {exc}") from exc


@app.get("/transactions/stats")
async def get_transaction_stats():
    """Return aggregate statistics across all stored transactions."""
    try:
        df = db.get_spending_summary()
        return df
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error fetching stats: {exc}") from exc


@app.get("/budget/status", response_model=BudgetStatus)
async def get_budget_status():
    """Return current-period spending vs budget limits."""
    try:
        budgets = db.get_budgets()
        df      = db.get_transactions()

        if df.empty:
            return BudgetStatus(
                daily_spent=0.0,      daily_remaining=budgets.get("daily"),
                weekly_spent=0.0,     weekly_remaining=budgets.get("weekly"),
                monthly_spent=0.0,    monthly_remaining=budgets.get("monthly"),
            )

        status = current_period_status(
            df,
            budgets.get("daily",   0.0),
            budgets.get("weekly",  0.0),
            budgets.get("monthly", 0.0),
        )
        return BudgetStatus(
            daily_spent=float(status["day_total"]),
            daily_remaining=status["day_remaining"],
            weekly_spent=float(status["week_total"]),
            weekly_remaining=status["week_remaining"],
            monthly_spent=float(status["month_total"]),
            monthly_remaining=status["month_remaining"],
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error fetching budget status: {exc}") from exc


@app.get("/budget/limits")
async def get_budget_limits():
    """Return the configured budget limits for the default user."""
    try:
        return db.get_budgets()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error fetching budget limits: {exc}") from exc


@app.post("/budget/limits")
async def set_budget_limits(budgets: List[BudgetLimit]):
    """Upsert one or more budget limits."""
    try:
        for budget in budgets:
            db.save_budget("default", budget.period, budget.limit_amount)
        return {"message": "Budget limits updated successfully"}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error setting budget limits: {exc}") from exc


@app.get("/categories")
async def get_categories():
    """Return total spending per category."""
    try:
        df = db.get_transactions()
        if df.empty:
            return {}
        category_totals = df.groupby("category")["amount"].sum()
        return {k: float(v) for k, v in category_totals.items()}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error fetching categories: {exc}") from exc


@app.delete("/data")
async def clear_all_data():
    """Permanently delete all data for the default user."""
    try:
        db.delete_user_data("default")
        return {"message": "All data cleared successfully"}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error clearing data: {exc}") from exc


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)