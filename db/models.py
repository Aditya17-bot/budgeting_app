from typing import Optional

from pydantic import BaseModel


class TransactionResponse(BaseModel):
    id: int
    date: str
    amount: float
    transaction_type: str
    category: str
    merchant: Optional[str]
    original_message: Optional[str]


class BudgetStatus(BaseModel):
    daily_spent: float
    daily_remaining: Optional[float]
    weekly_spent: float
    weekly_remaining: Optional[float]
    monthly_spent: float
    monthly_remaining: Optional[float]


class BudgetLimit(BaseModel):
    period: str
    limit_amount: float
