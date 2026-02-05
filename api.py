from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import List, Optional
import pandas as pd
import io
from datetime import datetime

from database import DataPersistence
from sms_parser import process_sms_dataframe, load_sms_xml
from budget import current_period_status

app = FastAPI(title="SMS Budget Tracker API", version="1.0.0")

# Enable CORS for mobile app
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize database
db = DataPersistence()

# Pydantic models
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
    period: str  # daily, weekly, monthly
    limit_amount: float

# API Endpoints

@app.get("/")
async def root():
    return {"message": "SMS Budget Tracker API", "version": "1.0.0"}

@app.post("/upload-sms")
async def upload_sms(file: UploadFile = File(...)):
    """Upload and process SMS file"""
    try:
        # Read file content
        content = await file.read()
        file_io = io.BytesIO(content)
        
        # Determine file type and process
        filename = file.filename.lower()
        if filename.endswith('.xml'):
            df = load_sms_xml(file_io)
        else:
            df = pd.read_csv(file_io)
        
        # Auto-detect columns (simplified for API)
        message_col = "body" if "body" in df.columns else "content" if "content" in df.columns else "message"
        date_col = "date" if "date" in df.columns else "readable_date" if "readable_date" in df.columns else "datetime"
        sender_col = "address" if "address" in df.columns else "sender" if "sender" in df.columns else None
        
        if not message_col or not date_col:
            raise HTTPException(status_code=400, detail="Could not detect required columns")
        
        # Process transactions
        processed = process_sms_dataframe(df, message_col, date_col, sender_col)
        
        if processed.empty:
            return {"message": "No financial transactions found", "count": 0}
        
        # Save to database
        saved_count = db.save_transactions(processed)
        
        return {
            "message": f"Successfully processed {len(processed)} transactions",
            "count": len(processed),
            "total_in_db": saved_count,
            "sample_transactions": processed.head(5).to_dict('records')
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing file: {str(e)}")

@app.get("/transactions", response_model=List[TransactionResponse])
async def get_transactions(
    limit: Optional[int] = 100,
    category: Optional[str] = None,
    transaction_type: Optional[str] = None
):
    """Get transactions with optional filters"""
    try:
        df = db.get_transactions()
        
        # Apply filters
        if category:
            df = df[df['category'] == category]
        if transaction_type:
            df = df[df['transaction_type'] == transaction_type]
        
        # Limit results
        if limit:
            df = df.head(limit)
        
        return df.to_dict('records')
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching transactions: {str(e)}")

@app.get("/transactions/stats")
async def get_transaction_stats():
    """Get transaction statistics"""
    try:
        df = db.get_transactions()
        
        if df.empty:
            return {
                "total_transactions": 0,
                "total_expenses": 0.0,
                "total_income": 0.0,
                "avg_transaction": 0.0,
                "categories": []
            }
        
        expenses = df[df['transaction_type'] == 'Expense']['amount'].sum()
        income = df[df['transaction_type'] == 'Income']['amount'].sum()
        
        return {
            "total_transactions": len(df),
            "total_expenses": float(expenses),
            "total_income": float(income),
            "avg_transaction": float(df['amount'].mean()),
            "categories": list(df['category'].unique()),
            "date_range": {
                "start": df['date'].min().strftime('%Y-%m-%d'),
                "end": df['date'].max().strftime('%Y-%m-%d')
            }
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching stats: {str(e)}")

@app.get("/budget/status", response_model=BudgetStatus)
async def get_budget_status():
    """Get current budget status"""
    try:
        budgets = db.get_budgets()
        df = db.get_transactions()
        
        if df.empty:
            return {
                "daily_spent": 0.0,
                "daily_remaining": budgets.get('daily', 0.0),
                "weekly_spent": 0.0,
                "weekly_remaining": budgets.get('weekly', 0.0),
                "monthly_spent": 0.0,
                "monthly_remaining": budgets.get('monthly', 0.0)
            }
        
        status = current_period_status(
            df, 
            budgets.get('daily', 0.0),
            budgets.get('weekly', 0.0), 
            budgets.get('monthly', 0.0)
        )
        
        return {
            "daily_spent": float(status['day_total']),
            "daily_remaining": status['day_remaining'],
            "weekly_spent": float(status['week_total']),
            "weekly_remaining": status['week_remaining'],
            "monthly_spent": float(status['month_total']),
            "monthly_remaining": status['month_remaining']
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching budget status: {str(e)}")

@app.get("/budget/limits")
async def get_budget_limits():
    """Get current budget limits"""
    try:
        return db.get_budgets()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching budget limits: {str(e)}")

@app.post("/budget/limits")
async def set_budget_limits(budgets: List[BudgetLimit]):
    """Set budget limits"""
    try:
        for budget in budgets:
            db.save_budget('default', budget.period, budget.limit_amount)
        return {"message": "Budget limits updated successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error setting budget limits: {str(e)}")

@app.get("/categories")
async def get_categories():
    """Get all categories and their totals"""
    try:
        df = db.get_transactions()
        
        if df.empty:
            return {}
        
        category_totals = df.groupby('category')['amount'].sum().to_dict()
        
        # Convert to float for JSON serialization
        return {k: float(v) for k, v in category_totals.items()}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching categories: {str(e)}")

@app.delete("/data")
async def clear_all_data():
    """Clear all transaction data"""
    try:
        db.delete_user_data('default')
        return {"message": "All data cleared successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error clearing data: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
