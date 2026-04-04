"""
frontend/streamlit_app.py
--------------------------
Main Streamlit application for the SMS Budget Tracker.
"""

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime

from core.parser import process_sms_dataframe, load_sms_xml
from services.budgeting import daily_totals, weekly_totals, monthly_totals, current_period_status
from db.session import DataPersistence
from frontend.mobile_utils import add_pwa_meta, mobile_friendly_layout
from services.analytics import (
    average_daily_spend,
    calculate_financial_health_score,
    build_budget_overrun_forecasts,
    detect_anomalies,
    predict_next_7_days_spend,
    daily_spending_series,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_PLOTLY_BASE = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(family="'IBM Plex Mono', monospace", color="#c9b99a"),
    xaxis=dict(gridcolor="#242424", zerolinecolor="#242424"),
    yaxis=dict(gridcolor="#242424", zerolinecolor="#242424"),
)

_ACCENT  = "#c9963c"
_GREEN   = "#6db38a"
_RED     = "#c95f5f"
_BLUE    = "#5f8ec9"
_PURPLE  = "#9b7dc9"

_CAT_COLORS = [
    _ACCENT, _GREEN, _BLUE, _PURPLE, "#c97d5f",
    "#5fc9c1", "#c9c25f", "#c95f9b", "#7dc9a0", "#8ec95f",
]

_COLUMN_CANDIDATES = {
    "message": ["content", "body", "message", "sms", "text"],
    "date":    ["date", "datetime", "timestamp", "time", "sent", "received", "readable_date"],
    "sender":  ["name/number sender", "sender", "from", "address", "name", "contact_name"],
}

# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------

db = DataPersistence()

st.set_page_config(
    page_title="Rupee Radar",
    page_icon="◈",
    layout="wide",
    initial_sidebar_state="expanded",
)

add_pwa_meta()
mobile_friendly_layout()

# ---------------------------------------------------------------------------
# Design system
# ---------------------------------------------------------------------------

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Playfair+Display:wght@700;900&family=IBM+Plex+Mono:wght@300;400;500&display=swap');

:root {
    --bg-base:     #0d0d0d;
    --bg-surface:  #141414;
    --bg-raised:   #1a1a1a;
    --bg-border:   #242424;
    --accent:      #c9963c;
    --accent-soft: #c9b99a;
    --accent-dim:  rgba(201,150,60,0.12);
    --green:       #6db38a;
    --red:         #c95f5f;
    --text-pri:    #e8ddd0;
    --text-muted:  #6b6158;
    --mono:        'IBM Plex Mono', monospace;
    --display:     'Playfair Display', serif;
}

html, body, [data-testid="stAppViewContainer"] {
    background-color: var(--bg-base) !important; color: var(--text-pri) !important;
}
[data-testid="stSidebar"] {
    background-color: var(--bg-surface) !important;
    border-right: 1px solid var(--bg-border) !important;
}
[data-testid="stHeader"] { background: transparent !important; }
section.main > div { padding-top: 1.5rem !important; }

h1,h2,h3,h4 { font-family: var(--display) !important; color: var(--text-pri) !important; letter-spacing: -0.02em !important; }
p,li,label,.stMarkdown,[data-testid="stText"],.stSelectbox label,.stCheckbox label,.stNumberInput label {
    font-family: var(--mono) !important; font-size: 0.78rem !important; color: var(--accent-soft) !important;
}

.rr-masthead { display:flex; align-items:baseline; gap:1.2rem; padding:2.4rem 0 1rem; border-bottom:1px solid var(--bg-border); margin-bottom:2rem; }
.rr-wordmark { font-family:var(--display); font-size:3.6rem; font-weight:900; color:var(--text-pri); letter-spacing:-0.04em; line-height:1; }
.rr-wordmark span { color:var(--accent); }
.rr-tagline { font-family:var(--mono); font-size:0.68rem; color:var(--text-muted); letter-spacing:0.18em; text-transform:uppercase; padding-bottom:0.2rem; }

.stat-grid { display:grid; grid-template-columns:repeat(4,1fr); gap:1px; background:var(--bg-border); border:1px solid var(--bg-border); border-radius:4px; overflow:hidden; margin-bottom:1.6rem; }
.stat-card { background:var(--bg-surface); padding:1.2rem 1.4rem; display:flex; flex-direction:column; gap:0.3rem; transition:background 0.15s; }
.stat-card:hover { background:var(--bg-raised); }
.stat-label { font-family:var(--mono); font-size:0.62rem; letter-spacing:0.2em; text-transform:uppercase; color:var(--text-muted); }
.stat-value { font-family:var(--mono); font-size:1.55rem; font-weight:500; color:var(--text-pri); letter-spacing:-0.02em; }
.stat-value.pos { color:var(--green); }
.stat-value.neg { color:var(--red); }
.stat-value.acc { color:var(--accent); }
.stat-delta { font-family:var(--mono); font-size:0.62rem; color:var(--text-muted); }

.budget-row { background:var(--bg-surface); border:1px solid var(--bg-border); border-radius:4px; padding:1.4rem 1.6rem; margin-bottom:1px; }
.budget-row-header { display:flex; justify-content:space-between; align-items:baseline; margin-bottom:0.7rem; }
.budget-period { font-family:var(--display); font-size:1rem; color:var(--text-pri); }
.budget-figures { font-family:var(--mono); font-size:0.72rem; color:var(--text-muted); }
.budget-track { height:3px; background:var(--bg-border); border-radius:2px; overflow:hidden; margin-bottom:0.5rem; }
.budget-fill { height:100%; border-radius:2px; transition:width 0.6s ease; }
.budget-meta { font-family:var(--mono); font-size:0.62rem; color:var(--text-muted); letter-spacing:0.1em; }

.anomaly-card { background:var(--bg-surface); border:1px solid var(--bg-border); border-left:3px solid var(--red); border-radius:4px; padding:1rem 1.2rem; margin-bottom:6px; display:grid; grid-template-columns:1fr auto; gap:0.4rem 1.2rem; align-items:start; }
.anomaly-card.z-flag { border-left-color:var(--accent); }
.anomaly-amount { font-family:var(--mono); font-size:1.2rem; font-weight:500; color:var(--red); justify-self:end; align-self:center; }
.anomaly-merchant { font-family:var(--display); font-size:0.95rem; color:var(--text-pri); }
.anomaly-meta { font-family:var(--mono); font-size:0.62rem; color:var(--text-muted); }
.anomaly-badge { font-family:var(--mono); font-size:0.58rem; letter-spacing:0.15em; text-transform:uppercase; padding:0.15rem 0.5rem; border-radius:2px; background:rgba(201,95,95,0.15); color:var(--red); display:inline-block; margin-top:0.3rem; }
.anomaly-badge.z { background:rgba(201,150,60,0.15); color:var(--accent); }

.section-label { font-family:var(--mono); font-size:0.62rem; letter-spacing:0.25em; text-transform:uppercase; color:var(--text-muted); border-bottom:1px solid var(--bg-border); padding-bottom:0.5rem; margin:1.6rem 0 1rem; }

[data-testid="stFileUploader"] { background:var(--bg-surface) !important; border:1px dashed var(--bg-border) !important; border-radius:4px !important; }
[data-testid="stFileUploader"]:hover { border-color:var(--accent) !important; }

[data-testid="stNumberInput"] input,[data-testid="stTextInput"] input,.stSelectbox>div>div {
    background:var(--bg-raised) !important; border:1px solid var(--bg-border) !important;
    border-radius:3px !important; color:var(--text-pri) !important;
    font-family:var(--mono) !important; font-size:0.8rem !important;
}

.stButton>button { background:transparent !important; border:1px solid var(--bg-border) !important; color:var(--accent-soft) !important; font-family:var(--mono) !important; font-size:0.72rem !important; letter-spacing:0.12em !important; text-transform:uppercase !important; border-radius:3px !important; transition:all 0.15s !important; }
.stButton>button:hover { border-color:var(--accent) !important; color:var(--accent) !important; background:var(--accent-dim) !important; }
.stButton>button[kind="primary"] { background:var(--accent) !important; border-color:var(--accent) !important; color:#0d0d0d !important; font-weight:500 !important; }

[data-testid="stTabs"] [role="tablist"] { background:transparent !important; border-bottom:1px solid var(--bg-border) !important; }
[data-testid="stTabs"] button[role="tab"] { font-family:var(--mono) !important; font-size:0.68rem !important; letter-spacing:0.18em !important; text-transform:uppercase !important; color:var(--text-muted) !important; background:transparent !important; border:none !important; border-bottom:2px solid transparent !important; border-radius:0 !important; }
[data-testid="stTabs"] button[role="tab"][aria-selected="true"] { color:var(--accent) !important; border-bottom-color:var(--accent) !important; }

[data-testid="stDataFrame"] { border:1px solid var(--bg-border) !important; border-radius:4px !important; font-family:var(--mono) !important; font-size:0.74rem !important; }
[data-testid="stDataFrame"] th { background:var(--bg-raised) !important; color:var(--text-muted) !important; font-size:0.62rem !important; letter-spacing:0.15em !important; text-transform:uppercase !important; }
[data-testid="stDataFrame"] td { color:var(--text-pri) !important; border-bottom:1px solid var(--bg-border) !important; }

[data-testid="stMetric"] { background:var(--bg-surface) !important; border:1px solid var(--bg-border) !important; border-radius:4px !important; padding:1rem !important; }
[data-testid="stMetricLabel"] { font-family:var(--mono) !important; font-size:0.62rem !important; letter-spacing:0.18em !important; text-transform:uppercase !important; color:var(--text-muted) !important; }
[data-testid="stMetricValue"] { font-family:var(--mono) !important; font-size:1.35rem !important; color:var(--text-pri) !important; }

[data-testid="stAlert"] { border-radius:3px !important; font-family:var(--mono) !important; font-size:0.74rem !important; }
[data-testid="stExpander"] { border:1px solid var(--bg-border) !important; border-radius:4px !important; background:var(--bg-surface) !important; }
[data-testid="stExpander"] summary { font-family:var(--mono) !important; font-size:0.72rem !important; color:var(--accent-soft) !important; }

[data-testid="stSidebar"] .stMarkdown h2,[data-testid="stSidebar"] .stMarkdown h3 {
    font-family:var(--mono) !important; font-size:0.62rem !important; letter-spacing:0.25em !important;
    text-transform:uppercase !important; color:var(--text-muted) !important;
    border-bottom:1px solid var(--bg-border) !important; padding-bottom:0.4rem !important; margin-top:1.6rem !important;
}

[data-testid="stDownloadButton"]>button { background:transparent !important; border:1px solid var(--accent) !important; color:var(--accent) !important; font-family:var(--mono) !important; font-size:0.72rem !important; letter-spacing:0.12em !important; text-transform:uppercase !important; border-radius:3px !important; }
[data-testid="stDownloadButton"]>button:hover { background:var(--accent-dim) !important; }

[data-testid="stCheckbox"] label { font-family:var(--mono) !important; font-size:0.74rem !important; color:var(--accent-soft) !important; }

::-webkit-scrollbar { width:4px; height:4px; }
::-webkit-scrollbar-track { background:var(--bg-base); }
::-webkit-scrollbar-thumb { background:var(--bg-border); border-radius:2px; }
::-webkit-scrollbar-thumb:hover { background:var(--accent); }
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------


def _theme(fig: go.Figure, title: str = "") -> go.Figure:
    fig.update_layout(
        **_PLOTLY_BASE,
        title=dict(text=title, font=dict(family="'Playfair Display', serif", size=14, color="#e8ddd0")),
        margin=dict(l=0, r=0, t=40 if title else 10, b=0),
        legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(family="'IBM Plex Mono', monospace", size=10, color="#6b6158")),
    )
    return fig


def _guess_column(columns: list, key: str) -> str:
    lowered = {c.lower(): c for c in columns}
    for c in _COLUMN_CANDIDATES.get(key, []):
        if c in lowered:
            return lowered[c]
    return ""


def _detect_columns(df: pd.DataFrame, is_xml: bool) -> tuple:
    cols = list(df.columns)
    if is_xml:
        msg    = "body" if "body" in cols else _guess_column(cols, "message")
        date   = next((c for c in ["readable_date", "date"] if c in cols), "")
        sender = "address" if "address" in cols else _guess_column(cols, "sender")
    else:
        msg    = _guess_column(cols, "message")
        date   = _guess_column(cols, "date")
        sender = _guess_column(cols, "sender")
    return msg, date, sender


def _date_range_str(df: pd.DataFrame) -> str:
    for col in ["date", "readable_date"]:
        if col not in df.columns:
            continue
        series = df[col].dropna()
        if series.empty:
            continue
        try:
            parsed = pd.to_datetime(series, errors="coerce")
            if parsed.notna().any():
                return f"{parsed.min():%b %Y} – {parsed.max():%b %Y}"
        except Exception:
            pass
        raw = str(series.iloc[0]).strip()
        if raw:
            return raw[:7]
    return "—"


def _rupee(v: float) -> str:
    return f"₹{v:,.2f}"


def _stat_card(label: str, value: str, delta: str = "", variant: str = "") -> str:
    cls = f"stat-value {variant}".strip()
    delta_html = f'<div class="stat-delta">{delta}</div>' if delta else ""
    return f'<div class="stat-card"><div class="stat-label">{label}</div><div class="{cls}">{value}</div>{delta_html}</div>'


def _budget_bar(label: str, spent: float, limit: float, remaining: float) -> str:
    if limit <= 0:
        return f'<div class="budget-row"><div class="budget-row-header"><span class="budget-period">{label}</span><span class="budget-figures">No limit set</span></div></div>'
    pct    = min(spent / limit * 100, 100)
    color  = _RED if pct >= 100 else _ACCENT if pct >= 80 else _GREEN
    status = "OVER LIMIT" if pct >= 100 else f"{100 - pct:.0f}% remaining"
    return f"""<div class="budget-row">
    <div class="budget-row-header"><span class="budget-period">{label}</span><span class="budget-figures">{_rupee(spent)} / {_rupee(limit)}</span></div>
    <div class="budget-track"><div class="budget-fill" style="width:{pct:.1f}%;background:{color};"></div></div>
    <div class="budget-meta">{status} · {_rupee(remaining)} left</div>
</div>"""


def _anomaly_card(row: pd.Series) -> str:
    is_z      = "z-score" in str(row.get("flag_reason", "")).lower()
    card_cls  = "anomaly-card z-flag" if is_z else "anomaly-card"
    badge_cls = "anomaly-badge z"     if is_z else "anomaly-badge"
    badge_txt = "Z-SCORE"             if is_z else "IQR OUTLIER"
    merchant  = str(row.get("merchant") or row.get("category") or "Unknown")
    try:
        date_str = pd.to_datetime(row.get("date")).strftime("%d %b %Y")
    except Exception:
        date_str = "—"
    z         = row.get("z_score", "—")
    threshold = row.get("threshold")
    mean_val  = row.get("global_mean")
    reason    = row.get("flag_reason", "—")
    thr_str   = _rupee(threshold) if isinstance(threshold, (int, float)) else "—"
    avg_str   = _rupee(mean_val)  if isinstance(mean_val,  (int, float)) else "—"
    return f"""<div class="{card_cls}">
    <div>
        <div class="anomaly-merchant">{merchant}</div>
        <div class="anomaly-meta">{date_str} · {row.get("category", "—")}</div>
        <div class="anomaly-meta">z = {z} · threshold {thr_str} · avg {avg_str}</div>
        <span class="{badge_cls}">{badge_txt} — {reason}</span>
    </div>
    <div class="anomaly-amount">{_rupee(row["amount"])}</div>
</div>"""


# ---------------------------------------------------------------------------
# Masthead
# ---------------------------------------------------------------------------

st.markdown("""
<div class="rr-masthead">
    <div class="rr-wordmark">Rupee<span>Radar</span></div>
    <div class="rr-tagline">SMS · Finance · Intelligence</div>
</div>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Upload
# ---------------------------------------------------------------------------

st.markdown('<div class="section-label">01 — Data Ingestion</div>', unsafe_allow_html=True)

up1, up2, up3 = st.columns([3, 1, 1])
with up1:
    uploaded_file = st.file_uploader("Drop SMS export here", type=["csv", "xml"], label_visibility="collapsed")
with up2:
    st.write(""); st.write("")
    if st.button("↺  Clear session", use_container_width=True):
        st.session_state.clear()
        st.rerun()
with up3:
    st.write(""); st.write("")
    st.caption("Supported: SMS Backup & Restore XML, generic CSV")

if uploaded_file:
    is_xml = (uploaded_file.name or "").lower().endswith(".xml")
    try:
        df = load_sms_xml(uploaded_file) if is_xml else pd.read_csv(uploaded_file)
    except Exception as exc:
        st.error(f"File could not be parsed — {exc}")
        st.stop()

    message_col, date_col, sender_col = _detect_columns(df, is_xml)

    st.markdown('<div class="section-label">02 — File Overview</div>', unsafe_allow_html=True)
    st.markdown(f"""<div class="stat-grid">
        {_stat_card("Messages",   f"{len(df):,}")}
        {_stat_card("Columns",    str(len(df.columns)))}
        {_stat_card("Date Range", _date_range_str(df))}
        {_stat_card("Format",     "XML" if is_xml else "CSV", variant="acc")}
    </div>""", unsafe_allow_html=True)

    st.markdown("  ·  ".join(f"`{k}` → **{v}**" for k, v in {
        "Message column": message_col or "not detected",
        "Date column":    date_col    or "not detected",
        "Sender column":  sender_col  or "not detected",
    }.items()))

    with st.expander("Preview raw data (first 10 rows)", expanded=False):
        st.dataframe(df.head(10), use_container_width=True, height=280)

    if not message_col or not date_col:
        st.error("Auto-detection failed for message or date columns.")
        st.stop()

    # ── Sidebar ─────────────────────────────────────────────────────────
    st.sidebar.markdown("## Configuration")
    saved_budgets = db.get_budgets()

    with st.sidebar.expander("Budget limits", expanded=True):
        daily_limit   = st.number_input("Daily",   min_value=0.0, value=saved_budgets.get("daily",   500.0),   step=50.0)
        weekly_limit  = st.number_input("Weekly",  min_value=0.0, value=saved_budgets.get("weekly",  3500.0),  step=200.0)
        monthly_limit = st.number_input("Monthly", min_value=0.0, value=saved_budgets.get("monthly", 15000.0), step=500.0)
        if st.button("Save limits", use_container_width=True):
            db.save_budget("default", "daily",   daily_limit)
            db.save_budget("default", "weekly",  weekly_limit)
            db.save_budget("default", "monthly", monthly_limit)
            st.success("Saved.")

    with st.sidebar.expander("Analysis options"):
        min_amount  = st.number_input("Min transaction (₹)", min_value=0.0, value=0.0, step=10.0)
        show_income = st.checkbox("Include income", value=True)
        debug_mode  = st.checkbox("Debug classification", value=False)
        date_range  = st.date_input("Date window", value=[datetime(2025, 1, 1).date(), datetime.now().date()])

    # ── Process ──────────────────────────────────────────────────────────
    st.markdown('<div class="section-label">03 — Processing</div>', unsafe_allow_html=True)
    _, btn_col, _ = st.columns([1, 2, 1])
    with btn_col:
        run = st.button("◈  Analyse SMS Data", use_container_width=True, type="primary")

    if run:
        with st.spinner("Parsing transactions…"):
            processed = process_sms_dataframe(df, message_col, date_col, sender_col or None)

        if processed.empty:
            st.warning("No financial SMS messages found.")
            st.stop()

        processed = (
            processed
            .dropna(subset=["date"])
            .loc[lambda d: d["date"] >= pd.Timestamp(date_range[0])]
            .loc[lambda d: d["date"] <= pd.Timestamp(date_range[1])]
            .loc[lambda d: d["amount"] >= min_amount]
        )
        if not show_income:
            processed = processed[processed["transaction_type"] == "Expense"]

        if processed.empty:
            st.warning("No transactions remain after applying filters.")
            st.stop()

        st.success(f"Extracted {len(processed):,} transactions.")

        if debug_mode:
            st.markdown('<div class="section-label">Debug — classification sample</div>', unsafe_allow_html=True)
            for _, row in processed.head(10).iterrows():
                with st.expander(f"{_rupee(row['amount'])}  ·  {row['transaction_type']}  ·  {row['category']}"):
                    st.text(row["original_message"])

        try:
            saved_count = db.save_transactions(processed)
            st.caption(f"Persisted {len(processed):,} transactions (total in DB: {saved_count:,})")
        except Exception as exc:
            st.warning(f"DB write failed — {exc}")

        st.session_state.processed_data = processed
        st.session_state.budget_limits  = {
            "daily": daily_limit, "weekly": weekly_limit, "monthly": monthly_limit,
        }

# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

if "processed_data" not in st.session_state:
    st.stop()

processed = st.session_state.processed_data
limits    = st.session_state.budget_limits

expenses_df   = processed[processed["transaction_type"] == "Expense"]
income_df     = processed[processed["transaction_type"] == "Income"]
total_expense = expenses_df["amount"].sum()
total_income  = income_df["amount"].sum()
avg_txn       = processed["amount"].mean()
net           = total_income - total_expense

status            = current_period_status(processed, limits["daily"], limits["weekly"], limits["monthly"])
avg_daily         = average_daily_spend(processed)
forecast_df       = predict_next_7_days_spend(processed)
anomalies_df      = detect_anomalies(processed)
health            = calculate_financial_health_score(processed, limits, status)
overrun_forecasts = build_budget_overrun_forecasts(status, limits, avg_daily)
daily_df          = daily_totals(processed)
weekly_df         = weekly_totals(processed)
monthly_df        = monthly_totals(processed)
full_daily        = daily_spending_series(processed)

st.markdown('<div class="section-label">04 — Dashboard</div>', unsafe_allow_html=True)

net_variant = "pos" if net >= 0 else "neg"
st.markdown(f"""<div class="stat-grid">
    {_stat_card("Total Expenses", _rupee(total_expense), variant="neg")}
    {_stat_card("Total Income",   _rupee(total_income),  variant="pos")}
    {_stat_card("Net Position",   _rupee(net),           variant=net_variant)}
    {_stat_card("Health Score",   f"{health['score']}/100", delta=health['label'], variant="acc")}
</div>""", unsafe_allow_html=True)

tab_txn, tab_analytics, tab_budget, tab_cat, tab_export = st.tabs([
    "Transactions", "Analytics", "Budget", "Categories", "Export",
])

# ============================================================ TRANSACTIONS
with tab_txn:
    st.markdown('<div class="section-label">Transaction ledger</div>', unsafe_allow_html=True)
    f1, f2, f3, f4 = st.columns(4)
    with f1:
        cat_filter = st.selectbox("Category", ["All"] + sorted(processed["category"].dropna().unique().tolist()))
    with f2:
        type_filter = st.selectbox("Type", ["All", "Expense", "Income"])
    with f3:
        merchant_q = st.text_input("Merchant search", placeholder="e.g. Swiggy")
    with f4:
        sort_by = st.selectbox("Sort by", ["date", "amount", "category"])

    view = processed.copy()
    if cat_filter != "All":
        view = view[view["category"] == cat_filter]
    if type_filter != "All":
        view = view[view["transaction_type"] == type_filter]
    if merchant_q:
        view = view[view["merchant"].str.contains(merchant_q, case=False, na=False)]
    view = view.sort_values(sort_by, ascending=False)

    f_exp = view[view["transaction_type"] == "Expense"]["amount"].sum()
    f_inc = view[view["transaction_type"] == "Income"]["amount"].sum()
    st.caption(f"Showing {len(view):,} of {len(processed):,}  ·  Filtered expenses {_rupee(f_exp)}  ·  income {_rupee(f_inc)}")
    st.dataframe(
        view[["date", "amount", "transaction_type", "category", "merchant", "original_message"]],
        use_container_width=True, height=460,
    )

# ============================================================ ANALYTICS
with tab_analytics:

    st.markdown('<div class="section-label">Financial health</div>', unsafe_allow_html=True)
    h1, h2, h3, h4 = st.columns(4)
    h1.metric("Overall Score",    f"{health['score']}/100")
    h2.metric("Rating",           health["label"])
    h3.metric("Savings Ratio",    f"{health['savings_ratio']:.1f}%")
    h4.metric("Budget Adherence", f"{health['components']['budget_adherence_score']:.0f}/100")

    comp_df = pd.DataFrame({
        "Component": ["Savings Ratio", "Budget Adherence", "Spending Consistency"],
        "Score":     [health["components"]["savings_ratio_score"],
                      health["components"]["budget_adherence_score"],
                      health["components"]["spending_consistency_score"]],
    })
    fig_h = go.Figure(go.Bar(
        x=comp_df["Component"], y=comp_df["Score"],
        marker_color=[_GREEN, _ACCENT, _BLUE], marker_line_width=0,
        text=[f"{s:.0f}" for s in comp_df["Score"]], textposition="outside",
        textfont=dict(family="'IBM Plex Mono', monospace", size=11, color="#c9b99a"),
    ))
    fig_h.update_layout(yaxis_range=[0, 115], **_PLOTLY_BASE,
                         title=dict(text="Health components", font=dict(family="'Playfair Display', serif", size=14, color="#e8ddd0")),
                         margin=dict(l=0, r=0, t=36, b=0))
    st.plotly_chart(fig_h, use_container_width=True)

    # ── Spending over time ───────────────────────────────────────────────
    st.markdown('<div class="section-label">Spending over time</div>', unsafe_allow_html=True)
    ts1, ts2 = st.columns(2)

    with ts1:
        if not daily_df.empty:
            dp = daily_df.copy()
            dp["date"] = pd.to_datetime(dp["date"])
            dp = dp.sort_values("date")
            dp["rolling_7d"] = dp["amount"].rolling(7, min_periods=1).mean()
            fig_d = go.Figure()
            fig_d.add_trace(go.Bar(
                x=dp["date"], y=dp["amount"], name="Daily spend",
                marker_color="rgba(201,150,60,0.35)", marker_line_width=0,
            ))
            fig_d.add_trace(go.Scatter(
                x=dp["date"], y=dp["rolling_7d"], name="7-day avg",
                mode="lines", line=dict(color=_ACCENT, width=2),
            ))
            _theme(fig_d, "Daily expenses + 7-day average")
            st.plotly_chart(fig_d, use_container_width=True)
        else:
            st.info("No daily data.")

    with ts2:
        if not weekly_df.empty:
            wp = weekly_df.copy()
            wp["week_start"] = pd.to_datetime(wp["week_start"])
            fig_w = go.Figure(go.Bar(x=wp["week_start"], y=wp["amount"], marker_color=_BLUE, marker_line_width=0))
            _theme(fig_w, "Weekly expenses")
            st.plotly_chart(fig_w, use_container_width=True)
        else:
            st.info("No weekly data.")

    if not monthly_df.empty:
        mp = monthly_df.copy()
        mp["month_start"] = pd.to_datetime(mp["month_start"])
        fig_m = go.Figure(go.Bar(x=mp["month_start"], y=mp["amount"], marker_color=_PURPLE, marker_line_width=0))
        _theme(fig_m, "Monthly expenses")
        st.plotly_chart(fig_m, use_container_width=True)

    # ── Forecast ─────────────────────────────────────────────────────────
    st.markdown('<div class="section-label">7-day forecast</div>', unsafe_allow_html=True)

    if not forecast_df.empty and not full_daily.empty:
        recent = full_daily.tail(30).copy()
        recent["date"] = pd.to_datetime(recent["date"])

        fc = forecast_df.copy()
        fc["date"]  = pd.to_datetime(fc["date"])
        fc["upper"] = fc["predicted_amount"] * 1.2
        fc["lower"] = fc["predicted_amount"] * 0.8

        fig_fc = go.Figure()

        # Historical bars
        fig_fc.add_trace(go.Bar(
            x=recent["date"], y=recent["amount"],
            name="Actual spend", marker_color="rgba(201,150,60,0.4)", marker_line_width=0,
        ))

        # Confidence band
        fig_fc.add_trace(go.Scatter(
            x=pd.concat([fc["date"], fc["date"].iloc[::-1]]),
            y=pd.concat([fc["upper"], fc["lower"].iloc[::-1]]),
            fill="toself", fillcolor="rgba(109,179,138,0.12)",
            line=dict(color="rgba(0,0,0,0)"), name="±20% band",
        ))

        # Forecast line
        fig_fc.add_trace(go.Scatter(
            x=fc["date"], y=fc["predicted_amount"],
            name="Forecast", mode="lines+markers",
            line=dict(color=_GREEN, width=2, dash="dot"),
            marker=dict(color=_GREEN, size=7, symbol="diamond"),
        ))

        # Today marker
        last_actual = recent["date"].max()
        fig_fc.add_vline(x=last_actual, line_dash="dash",
                          line_color="rgba(201,185,154,0.2)", line_width=1)
        fig_fc.add_annotation(x=last_actual, y=1, yref="paper", text="today",
                               showarrow=False, xanchor="left", xshift=6,
                               font=dict(family="'IBM Plex Mono', monospace", size=9, color="#6b6158"))

        _theme(fig_fc, "Spend history + 7-day forecast")
        st.plotly_chart(fig_fc, use_container_width=True)

        fc_disp = fc[["date", "predicted_amount", "lower", "upper"]].copy()
        fc_disp.columns = ["Date", "Predicted (₹)", "Low (₹)", "High (₹)"]
        fc_disp["Date"] = fc_disp["Date"].dt.strftime("%a %d %b")
        for col in ["Predicted (₹)", "Low (₹)", "High (₹)"]:
            fc_disp[col] = fc_disp[col].map(lambda x: f"₹{x:,.0f}")
        st.dataframe(fc_disp, use_container_width=True, hide_index=True)
        st.caption(
            "Weighted moving average (recent days weighted higher) blended with "
            "linear trend from last 14 days. Confidence band ±20%."
        )
    else:
        st.info("Not enough expense history for a forecast.")

    # ── Anomaly detection ────────────────────────────────────────────────
    st.markdown('<div class="section-label">Anomaly detection</div>', unsafe_allow_html=True)

    if not anomalies_df.empty:
        n_iqr = (~anomalies_df["flag_reason"].str.contains("z-score", case=False, na=False)).sum()
        n_z   = anomalies_df["flag_reason"].str.contains("z-score", case=False, na=False).sum()
        parts = []
        if n_iqr: parts.append(f"{n_iqr} above category IQR fence")
        if n_z:   parts.append(f"{n_z} high global z-score (>2.5σ)")
        st.warning(f"Found {len(anomalies_df)} unusual transactions — " + " · ".join(parts))

        # Scatter: all expenses with anomalies highlighted
        all_exp = expenses_df.copy()
        all_exp["date"] = pd.to_datetime(all_exp["date"])
        anomaly_keys = set(zip(
            anomalies_df["date"].astype(str).str[:10],
            anomalies_df["amount"].round(2),
        ))
        all_exp["_flag"] = [
            (str(r["date"])[:10], round(r["amount"], 2)) in anomaly_keys
            for _, r in all_exp.iterrows()
        ]
        normal_pts    = all_exp[~all_exp["_flag"]]
        anomalous_pts = all_exp[all_exp["_flag"]]

        fig_anom = go.Figure()
        fig_anom.add_trace(go.Scatter(
            x=normal_pts["date"], y=normal_pts["amount"],
            mode="markers", name="Normal",
            marker=dict(color="rgba(201,185,154,0.2)", size=5, line=dict(width=0)),
        ))
        fig_anom.add_trace(go.Scatter(
            x=anomalous_pts["date"], y=anomalous_pts["amount"],
            mode="markers", name="Anomaly",
            marker=dict(color=_RED, size=11, symbol="circle-open", line=dict(width=2, color=_RED)),
            text=anomalous_pts.get("merchant", pd.Series([""] * len(anomalous_pts))),
            hovertemplate="<b>%{text}</b><br>₹%{y:,.0f}<extra></extra>",
        ))
        _theme(fig_anom, "All expenses — anomalies highlighted")
        st.plotly_chart(fig_anom, use_container_width=True)

        for _, row in anomalies_df.iterrows():
            st.markdown(_anomaly_card(row), unsafe_allow_html=True)
    else:
        st.success("No anomalies detected — spending patterns look consistent.")
        st.caption(
            "Per-category IQR fences (Tukey) + global z-score > 2.5σ. "
            "Both rules compared before flagging."
        )

# ============================================================ BUDGET
with tab_budget:
    st.markdown('<div class="section-label">Period status</div>', unsafe_allow_html=True)
    st.markdown(
        _budget_bar("Today",      status["day_total"],   limits["daily"],   status["day_remaining"]   or 0)
        + _budget_bar("This week",  status["week_total"],  limits["weekly"],  status["week_remaining"]  or 0)
        + _budget_bar("This month", status["month_total"], limits["monthly"], status["month_remaining"] or 0),
        unsafe_allow_html=True,
    )
    st.markdown('<div class="section-label">Overrun forecasts</div>', unsafe_allow_html=True)
    for fc in overrun_forecasts:
        (st.warning if fc["will_exceed"] else st.info)(fc["message"])

# ============================================================ CATEGORIES
with tab_cat:
    st.markdown('<div class="section-label">Spending distribution</div>', unsafe_allow_html=True)
    cat_totals = processed.groupby("category")["amount"].sum().sort_values(ascending=False)

    pie_col, bar_col = st.columns(2)
    with pie_col:
        fig_pie = go.Figure(go.Pie(
            labels=cat_totals.index, values=cat_totals.values, hole=0.45,
            marker=dict(colors=_CAT_COLORS, line=dict(color="#0d0d0d", width=2)),
            textfont=dict(family="'IBM Plex Mono', monospace", size=10),
        ))
        _theme(fig_pie, "Category split")
        st.plotly_chart(fig_pie, use_container_width=True)

    with bar_col:
        fig_cat = go.Figure(go.Bar(
            x=cat_totals.values, y=cat_totals.index, orientation="h",
            marker_color=_CAT_COLORS[:len(cat_totals)], marker_line_width=0,
            text=[f"₹{v:,.0f}" for v in cat_totals.values], textposition="outside",
            textfont=dict(family="'IBM Plex Mono', monospace", size=10, color="#c9b99a"),
        ))
        _theme(fig_cat, "Total by category")
        fig_cat.update_layout(yaxis=dict(autorange="reversed"))
        st.plotly_chart(fig_cat, use_container_width=True)

    st.markdown('<div class="section-label">Monthly trends by category</div>', unsafe_allow_html=True)
    trend_df = processed.copy()
    trend_df["month"] = trend_df["date"].dt.to_period("M").astype(str)
    monthly_cat = trend_df.groupby(["month", "category"])["amount"].sum().reset_index()

    fig_trend = px.line(
        monthly_cat, x="month", y="amount", color="category",
        color_discrete_sequence=_CAT_COLORS, markers=True,
        labels={"month": "Month", "amount": "Amount (₹)", "category": "Category"},
    )
    _theme(fig_trend, "Category spend over time")
    fig_trend.update_traces(line=dict(width=1.5), marker=dict(size=5))
    st.plotly_chart(fig_trend, use_container_width=True)

# ============================================================ EXPORT
with tab_export:
    st.markdown('<div class="section-label">Download data</div>', unsafe_allow_html=True)
    today_str = datetime.now().strftime("%Y%m%d")
    ex1, ex2  = st.columns(2)

    with ex1:
        st.markdown("**Full transaction ledger**")
        st.caption("All parsed transactions including message text, category, and merchant.")
        st.download_button(
            "↓  Download transactions.csv",
            data=processed.to_csv(index=False).encode("utf-8"),
            file_name=f"transactions_{today_str}.csv", mime="text/csv", use_container_width=True,
        )
    with ex2:
        st.markdown("**Summary report**")
        st.caption("Aggregated KPIs — totals, averages, and health score.")
        summary_df = pd.DataFrame({
            "Metric": ["Total transactions", "Total expenses", "Total income", "Net position", "Avg transaction", "Health score"],
            "Value":  [len(processed), round(total_expense,2), round(total_income,2), round(net,2), round(avg_txn,2), health["score"]],
        })
        st.download_button(
            "↓  Download summary.csv",
            data=summary_df.to_csv(index=False).encode("utf-8"),
            file_name=f"summary_{today_str}.csv", mime="text/csv", use_container_width=True,
        )

    st.markdown('<div class="section-label">Snapshot</div>', unsafe_allow_html=True)
    st.json({
        "transactions":   len(processed),
        "date_range":     {"from": processed["date"].min().strftime("%Y-%m-%d"), "to": processed["date"].max().strftime("%Y-%m-%d")},
        "total_expenses": round(total_expense, 2),
        "total_income":   round(total_income,  2),
        "net":            round(net, 2),
        "health_score":   health["score"],
        "health_label":   health["label"],
        "categories":     sorted(processed["category"].dropna().unique().tolist()),
    })