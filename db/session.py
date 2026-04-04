"""
db/session.py
-------------
SQLite persistence layer for transactions, budgets, and custom categories.

Public surface:
    DataPersistence(db_path?)
        .save_transactions(df, user_id?)   -> int
        .get_transactions(user_id?, ...)   -> pd.DataFrame
        .save_budget(user_id, period, amount)
        .get_budgets(user_id?)             -> dict
        .get_spending_summary(...)         -> dict
        .export_to_csv(...)                -> str
        .delete_user_data(user_id)
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional

import pandas as pd


class DataPersistence:
    def __init__(self, db_path: str = "") -> None:
        self.db_path = self._resolve_db_path(db_path)
        self._init_database()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_db_path(db_path: str) -> str:
        if db_path:
            return db_path
        base_dir  = Path(__file__).resolve().parents[1]
        data_dir  = base_dir / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        preferred = data_dir / "budget_data.db"
        legacy    = base_dir / "budget_data.db"
        return str(preferred if preferred.exists() or not legacy.exists() else legacy)

    @contextmanager
    def _connect(self) -> Generator[sqlite3.Connection, None, None]:
        conn = sqlite3.connect(self.db_path, detect_types=sqlite3.PARSE_DECLTYPES)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_database(self) -> None:
        """Create tables and performance indexes. Safe to call on existing DBs."""
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS transactions (
                    id               INTEGER PRIMARY KEY AUTOINCREMENT,
                    date             TEXT    NOT NULL,
                    amount           REAL    NOT NULL,
                    transaction_type TEXT    NOT NULL,
                    category         TEXT    NOT NULL,
                    merchant         TEXT,
                    original_message TEXT,
                    created_at       TEXT    DEFAULT CURRENT_TIMESTAMP,
                    user_id          TEXT    DEFAULT 'default'
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS budgets (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id      TEXT DEFAULT 'default',
                    period       TEXT NOT NULL,
                    limit_amount REAL NOT NULL,
                    created_at   TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at   TEXT DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE (user_id, period)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS custom_categories (
                    id            INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id       TEXT DEFAULT 'default',
                    category_name TEXT NOT NULL,
                    keywords      TEXT,
                    created_at    TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            # Query-speed indexes only — no unique constraint on transactions.
            # Deduplication is handled in Python inside save_transactions().
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_transactions_user_date
                ON transactions (user_id, date)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_transactions_category
                ON transactions (user_id, category)
            """)

    # ------------------------------------------------------------------
    # Transactions
    # ------------------------------------------------------------------

    def save_transactions(self, df: pd.DataFrame, user_id: str = "default") -> int:
        """
        Persist new rows from *df*, skipping any that are already stored
        (matched on user_id + original_message + date + amount).

        Deduplication is done in Python so it works regardless of SQLite
        version and is immune to index state on existing databases.

        Returns the total row count for *user_id* after the insert.
        """
        if df.empty:
            return self._count_transactions(user_id)

        required  = ["date", "amount", "transaction_type", "category",
                     "merchant", "original_message"]
        available = [c for c in required if c in df.columns]

        insert_df = df[available].copy()
        insert_df["user_id"]    = user_id
        insert_df["created_at"] = datetime.now().isoformat()

        if "date" in insert_df.columns:
            insert_df["date"] = (
                pd.to_datetime(insert_df["date"], errors="coerce")
                .dt.strftime("%Y-%m-%d %H:%M:%S")
            )

        # ── Python-side deduplication ─────────────────────────────────
        # Fetch the fingerprints (message + date + amount) already in the DB
        # for this user, then drop any incoming rows that match.
        with self._connect() as conn:
            existing = pd.read_sql_query(
                """
                SELECT original_message, date, amount
                FROM   transactions
                WHERE  user_id = ? AND original_message IS NOT NULL
                """,
                conn,
                params=(user_id,),
            )

        if not existing.empty and "original_message" in insert_df.columns:
            existing["_key"] = (
                existing["original_message"].astype(str)
                + "|" + existing["date"].astype(str)
                + "|" + existing["amount"].astype(str)
            )
            existing_keys = set(existing["_key"])

            mask = ~(
                insert_df["original_message"].astype(str)
                + "|" + insert_df["date"].astype(str)
                + "|" + insert_df["amount"].astype(str)
            ).isin(existing_keys)
            insert_df = insert_df[mask]

        if insert_df.empty:
            return self._count_transactions(user_id)

        records      = insert_df.to_dict("records")
        col_names    = list(records[0].keys())
        placeholders = ", ".join("?" * len(col_names))
        col_list     = ", ".join(col_names)
        sql          = f"INSERT INTO transactions ({col_list}) VALUES ({placeholders})"

        with self._connect() as conn:
            conn.executemany(sql, [tuple(r[c] for c in col_names) for r in records])
            count = conn.execute(
                "SELECT COUNT(*) FROM transactions WHERE user_id = ?", (user_id,)
            ).fetchone()[0]

        return count

    def _count_transactions(self, user_id: str) -> int:
        with self._connect() as conn:
            return conn.execute(
                "SELECT COUNT(*) FROM transactions WHERE user_id = ?", (user_id,)
            ).fetchone()[0]

    def get_transactions(
        self,
        user_id: str = "default",
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        category: Optional[str] = None,
        transaction_type: Optional[str] = None,
    ) -> pd.DataFrame:
        """Return transactions for *user_id* as a DataFrame, newest first."""
        conditions: List[str] = ["user_id = ?"]
        params:     List[Any] = [user_id]

        if start_date:
            conditions.append("date >= ?")
            params.append(start_date)
        if end_date:
            conditions.append("date <= ?")
            params.append(end_date)
        if category:
            conditions.append("category = ?")
            params.append(category)
        if transaction_type:
            conditions.append("transaction_type = ?")
            params.append(transaction_type)

        sql = (
            f"SELECT * FROM transactions "
            f"WHERE {' AND '.join(conditions)} "
            f"ORDER BY date DESC"
        )

        with self._connect() as conn:
            df = pd.read_sql_query(sql, conn, params=params)

        if not df.empty and "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"], errors="coerce")

        return df

    # ------------------------------------------------------------------
    # Budgets
    # ------------------------------------------------------------------

    def save_budget(self, user_id: str, period: str, limit_amount: float) -> None:
        """Upsert a budget limit for *period* (daily / weekly / monthly)."""
        sql = """
            INSERT INTO budgets (user_id, period, limit_amount, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT (user_id, period)
            DO UPDATE SET limit_amount = excluded.limit_amount,
                          updated_at   = excluded.updated_at
        """
        with self._connect() as conn:
            conn.execute(sql, (user_id, period, limit_amount, datetime.now().isoformat()))

    def get_budgets(self, user_id: str = "default") -> Dict[str, float]:
        """Return {period: limit_amount} for *user_id*."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT period, limit_amount FROM budgets WHERE user_id = ?",
                (user_id,),
            ).fetchall()
        return {row["period"]: row["limit_amount"] for row in rows}

    # ------------------------------------------------------------------
    # Summary & export
    # ------------------------------------------------------------------

    def get_spending_summary(
        self,
        user_id: str = "default",
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Return high-level spending statistics for *user_id*."""
        df = self.get_transactions(user_id, start_date, end_date)

        if df.empty:
            return {
                "total_transactions": 0,
                "total_expenses":     0.0,
                "total_income":       0.0,
                "avg_transaction":    0.0,
                "categories":         [],
                "date_range":         None,
            }

        expenses = float(df[df["transaction_type"] == "Expense"]["amount"].sum())
        income   = float(df[df["transaction_type"] == "Income"]["amount"].sum())

        return {
            "total_transactions": len(df),
            "total_expenses":     expenses,
            "total_income":       income,
            "avg_transaction":    float(df["amount"].mean()),
            "categories":         sorted(df["category"].dropna().unique().tolist()),
            "date_range": {
                "start": df["date"].min().strftime("%Y-%m-%d"),
                "end":   df["date"].max().strftime("%Y-%m-%d"),
            },
        }

    def export_to_csv(
        self,
        user_id: str = "default",
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> str:
        """Return transactions as a CSV string."""
        return self.get_transactions(user_id, start_date, end_date).to_csv(index=False)

    # ------------------------------------------------------------------
    # Deletion
    # ------------------------------------------------------------------

    def delete_user_data(self, user_id: str) -> None:
        """Permanently remove all data for *user_id* across all tables."""
        with self._connect() as conn:
            conn.execute("DELETE FROM transactions      WHERE user_id = ?", (user_id,))
            conn.execute("DELETE FROM budgets           WHERE user_id = ?", (user_id,))
            conn.execute("DELETE FROM custom_categories WHERE user_id = ?", (user_id,))