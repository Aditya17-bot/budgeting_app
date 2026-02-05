import sqlite3
import pandas as pd
from datetime import datetime
import os
from typing import Optional, List, Dict, Any

class DataPersistence:
    def __init__(self, db_path: str = "budget_data.db"):
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        """Initialize the database with required tables"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Create transactions table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                amount REAL NOT NULL,
                transaction_type TEXT NOT NULL,
                category TEXT NOT NULL,
                merchant TEXT,
                original_message TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                user_id TEXT DEFAULT 'default'
            )
        ''')
        
        # Create budgets table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS budgets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT DEFAULT 'default',
                period TEXT NOT NULL,  -- daily, weekly, monthly
                limit_amount REAL NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Create categories table for custom categories
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS custom_categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT DEFAULT 'default',
                category_name TEXT NOT NULL,
                keywords TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def save_transactions(self, df: pd.DataFrame, user_id: str = 'default') -> int:
        """Save transactions to database"""
        conn = sqlite3.connect(self.db_path)
        
        # Prepare data
        df_copy = df.copy()
        df_copy['user_id'] = user_id
        df_copy['created_at'] = datetime.now().isoformat()
        
        # Select only required columns
        required_columns = ['date', 'amount', 'transaction_type', 'category', 'merchant', 'original_message']
        available_columns = [col for col in required_columns if col in df_copy.columns]
        
        if 'user_id' not in df_copy.columns:
            df_copy['user_id'] = user_id
        if 'created_at' not in df_copy.columns:
            df_copy['created_at'] = datetime.now().isoformat()
        
        save_columns = available_columns + ['user_id', 'created_at']
        df_to_save = df_copy[save_columns]
        
        # Convert date to string format
        if 'date' in df_to_save.columns:
            df_to_save['date'] = pd.to_datetime(df_to_save['date']).dt.strftime('%Y-%m-%d %H:%M:%S')
        
        # Save to database
        df_to_save.to_sql('transactions', conn, if_exists='append', index=False)
        
        # Get count of inserted records
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM transactions WHERE user_id = ?", (user_id,))
        count = cursor.fetchone()[0]
        
        conn.close()
        return count
    
    def get_transactions(self, user_id: str = 'default', 
                         start_date: Optional[str] = None, 
                         end_date: Optional[str] = None,
                         category: Optional[str] = None,
                         transaction_type: Optional[str] = None) -> pd.DataFrame:
        """Retrieve transactions from database"""
        conn = sqlite3.connect(self.db_path)
        
        query = "SELECT * FROM transactions WHERE user_id = ?"
        params = [user_id]
        
        if start_date:
            query += " AND date >= ?"
            params.append(start_date)
        
        if end_date:
            query += " AND date <= ?"
            params.append(end_date)
        
        if category:
            query += " AND category = ?"
            params.append(category)
        
        if transaction_type:
            query += " AND transaction_type = ?"
            params.append(transaction_type)
        
        query += " ORDER BY date DESC"
        
        df = pd.read_sql_query(query, conn, params=params)
        conn.close()
        
        # Convert date back to datetime
        if not df.empty and 'date' in df.columns:
            df['date'] = pd.to_datetime(df['date'])
        
        return df
    
    def save_budget(self, user_id: str, period: str, limit_amount: float):
        """Save or update budget limits"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Check if budget exists
        cursor.execute(
            "SELECT id FROM budgets WHERE user_id = ? AND period = ?",
            (user_id, period)
        )
        existing = cursor.fetchone()
        
        if existing:
            # Update existing budget
            cursor.execute(
                "UPDATE budgets SET limit_amount = ?, updated_at = ? WHERE user_id = ? AND period = ?",
                (limit_amount, datetime.now().isoformat(), user_id, period)
            )
        else:
            # Insert new budget
            cursor.execute(
                "INSERT INTO budgets (user_id, period, limit_amount) VALUES (?, ?, ?)",
                (user_id, period, limit_amount)
            )
        
        conn.commit()
        conn.close()
    
    def get_budgets(self, user_id: str = 'default') -> Dict[str, float]:
        """Get budget limits for a user"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute(
            "SELECT period, limit_amount FROM budgets WHERE user_id = ?",
            (user_id,)
        )
        
        budgets = {}
        for row in cursor.fetchall():
            budgets[row[0]] = row[1]
        
        conn.close()
        return budgets
    
    def get_spending_summary(self, user_id: str = 'default', 
                           start_date: Optional[str] = None,
                           end_date: Optional[str] = None) -> Dict[str, Any]:
        """Get spending summary statistics"""
        df = self.get_transactions(user_id, start_date, end_date)
        
        if df.empty:
            return {
                'total_transactions': 0,
                'total_expenses': 0.0,
                'total_income': 0.0,
                'avg_transaction': 0.0,
                'categories': [],
                'date_range': None
            }
        
        expenses = df[df['transaction_type'] == 'Expense']['amount'].sum()
        income = df[df['transaction_type'] == 'Income']['amount'].sum()
        
        return {
            'total_transactions': len(df),
            'total_expenses': expenses,
            'total_income': income,
            'avg_transaction': df['amount'].mean(),
            'categories': list(df['category'].unique()),
            'date_range': {
                'start': df['date'].min().strftime('%Y-%m-%d'),
                'end': df['date'].max().strftime('%Y-%m-%d')
            }
        }
    
    def export_to_csv(self, user_id: str = 'default', 
                     start_date: Optional[str] = None,
                     end_date: Optional[str] = None) -> str:
        """Export transactions to CSV format"""
        df = self.get_transactions(user_id, start_date, end_date)
        return df.to_csv(index=False)
    
    def delete_user_data(self, user_id: str):
        """Delete all data for a user"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("DELETE FROM transactions WHERE user_id = ?", (user_id,))
        cursor.execute("DELETE FROM budgets WHERE user_id = ?", (user_id,))
        cursor.execute("DELETE FROM custom_categories WHERE user_id = ?", (user_id,))
        
        conn.commit()
        conn.close()
