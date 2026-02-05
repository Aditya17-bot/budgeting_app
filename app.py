import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import numpy as np
from datetime import datetime, timedelta
import os

from sms_parser import process_sms_dataframe, load_sms_xml
from budget import daily_totals, weekly_totals, monthly_totals, current_period_status
from database import DataPersistence
from mobile_utils import add_pwa_meta, mobile_friendly_layout

# Initialize database
db = DataPersistence()

# Streamlit page configuration
st.set_page_config(
    page_title="SMS Budget Tracker",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for better styling
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        text-align: center;
        background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 2rem;
    }
    .metric-card {
        background: white;
        padding: 1rem;
        border-radius: 10px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        border-left: 4px solid #667eea;
    }
    .success-box {
        background: #d4edda;
        border: 1px solid #c3e6cb;
        border-radius: 5px;
        padding: 1rem;
        margin: 0.5rem 0;
    }
    .warning-box {
        background: #fff3cd;
        border: 1px solid #ffeaa7;
        border-radius: 5px;
        padding: 1rem;
        margin: 0.5rem 0;
    }
    .error-box {
        background: #f8d7da;
        border: 1px solid #f5c6cb;
        border-radius: 5px;
        padding: 1rem;
        margin: 0.5rem 0;
    }
</style>
""", unsafe_allow_html=True)

st.markdown('<h1 class="main-header">💰 SMS Budget Tracker</h1>', unsafe_allow_html=True)

# Add PWA meta tags and mobile optimizations
add_pwa_meta()
mobile_friendly_layout()

# File Upload Section
st.subheader("📤 Upload SMS Data")
col1, col2, col3 = st.columns([2, 1, 1])
with col1:
    uploaded_file = st.file_uploader(
        "Choose SMS file", 
        type=['csv', 'xml'],
        help="Upload your SMS export file (CSV or XML format)"
    )
with col2:
    file_type = st.selectbox(
        "File Type",
        ["CSV", "XML"],
        help="Select your file format"
    )
with col3:
    if st.button("🔄 Clear", help="Clear all data"):
        st.session_state.clear()
        st.rerun()

if uploaded_file:
    filename = (uploaded_file.name or "").lower()
    is_xml = filename.endswith(".xml")

    # Data loading
    if is_xml:
        df = load_sms_xml(uploaded_file)
    else:
        df = pd.read_csv(uploaded_file)

    # Data preview with tabs
    tab1, tab2 = st.tabs(["📊 Data Preview", "⚙️ Column Mapping"])
    
    with tab1:
        st.subheader("📋 Raw Data Preview")
        if is_xml:
            st.info("📱 XML SMS data detected")
        else:
            st.info("📄 CSV SMS data detected")
        
        # Compact preview with expand option
        with st.expander("👁️ Preview Raw Data (First 10 rows)", expanded=False):
            st.dataframe(df.head(10), use_container_width=True, height=300)
        
        # Compact stats row
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("📨 Messages", f"{len(df):,}")
        with col2:
            st.metric("📊 Columns", len(df.columns))
        with col3:
            if 'date' in df.columns or 'readable_date' in df.columns:
                date_col = 'date' if 'date' in df.columns else 'readable_date'
                st.metric("📅 Range", f"{df[date_col].min()[:7]}")
            else:
                st.metric("📅 Range", "N/A")
        with col4:
            st.metric("💾 Size", f"{len(df.to_csv()) / 1024:.0f}KB")
    
    with tab2:

        st.subheader("🔧 Column Configuration")
        columns = list(df.columns)
        
        col1, col2 = st.columns(2)
        with col1:
            st.write("**Available Columns:**")
            for col in columns:
                st.write(f"• {col}")
        
        with col2:
            st.write("**Auto-detected Mapping:**")
            def guess_column(candidates):
                lowered = {c.lower(): c for c in columns}
                for key in candidates:
                    if key in lowered:
                        return lowered[key]
                return ""

            if is_xml:
                message_col = "body" if "body" in columns else guess_column(["body", "content", "message", "sms", "text"])
                date_col = "readable_date" if "readable_date" in columns else "date" if "date" in columns else ""
                sender_col = "address" if "address" in columns else guess_column(["address", "contact_name", "sender", "from"])
            else:
                message_col = guess_column(["content", "body", "message", "sms", "text"])
                date_col = guess_column(["date", "datetime", "timestamp", "time", "sent", "received"])
                sender_col = guess_column(["name/number sender", "sender", "from", "address", "name", "contact_name"])
            
            st.write(f"• **Message Column:** {message_col or 'Not found'}")
            st.write(f"• **Date Column:** {date_col or 'Not found'}")
            st.write(f"• **Sender Column:** {sender_col or 'Not found'}")

    if not message_col or not date_col:
        st.error("❌ Could not auto-detect message/date columns. Please ensure your file has message text and date fields.")
        st.info("💡 Required columns: message content and date/timestamp")
        st.stop()

    # Enhanced sidebar with budget configuration
    st.sidebar.markdown("## ⚙️ Budget Configuration")
    
    # Load saved budgets if available
    saved_budgets = db.get_budgets()
    
    with st.sidebar.expander("💳 Budget Limits", expanded=True):
        daily_limit = st.number_input(
            "Daily Budget Limit", 
            min_value=0.0, 
            value=saved_budgets.get('daily', 500.0), 
            step=50.0,
            help="Set your daily spending limit"
        )
        weekly_limit = st.number_input(
            "Weekly Budget Limit", 
            min_value=0.0, 
            value=saved_budgets.get('weekly', 3500.0), 
            step=200.0,
            help="Set your weekly spending limit"
        )
        monthly_limit = st.number_input(
            "Monthly Budget Limit", 
            min_value=0.0, 
            value=saved_budgets.get('monthly', 15000.0), 
            step=500.0,
            help="Set your monthly spending limit"
        )
        
        # Save budgets button
        if st.sidebar.button("💾 Save Budget Limits"):
            db.save_budget('default', 'daily', daily_limit)
            db.save_budget('default', 'weekly', weekly_limit)
            db.save_budget('default', 'monthly', monthly_limit)
            st.sidebar.success("Budget limits saved!")
    
    with st.sidebar.expander("📊 Analysis Options"):
        min_amount = st.number_input(
            "Minimum Transaction Amount", 
            min_value=0.0, 
            value=0.0, 
            step=10.0,
            help="Filter out transactions below this amount"
        )
        show_income = st.checkbox(
            "Include Income in Analysis", 
            value=True,  # Changed default to True
            help="Show income transactions alongside expenses"
        )
        debug_mode = st.checkbox(
            "🔍 Debug Mode", 
            value=False,
            help="Show classification details for debugging"
        )
        date_range = st.date_input(
            "Date Range",
            value=[datetime(2025, 1, 1).date(), datetime.now().date()],
            help="Select date range for analysis"
        )

    # Main processing button with better styling
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        if st.button("🚀 Process SMS Data", use_container_width=True, type="primary"):
            with st.spinner("🔄 Processing SMS data..."):
                processed = process_sms_dataframe(df, message_col, date_col, sender_col or None)
                if processed.empty:
                    st.warning("⚠️ No valid transaction SMS messages found.")
                    st.stop()

                # Apply filters
                processed = processed.dropna(subset=["date"])
                processed = processed[processed["date"] >= pd.Timestamp(date_range[0])]
                processed = processed[processed["date"] <= pd.Timestamp(date_range[1])]
                processed = processed[processed["amount"] >= min_amount]

                if not show_income:
                    processed = processed[processed["transaction_type"] == "Expense"]

                if processed.empty:
                    st.warning("⚠️ No transactions found after applying filters.")
                    st.stop()

                st.success(f"✅ Successfully processed {len(processed)} transactions!")
                
                # Debug mode - show classification details
                if debug_mode:
                    st.subheader("🔍 Debug Classification")
                    
                    # Show some sample messages and their classification
                    sample_messages = processed.head(10)[['original_message', 'transaction_type', 'category', 'amount']].copy()
                    
                    for idx, row in sample_messages.iterrows():
                        with st.expander(f"Message {idx+1}: ₹{row['amount']:,.2f} ({row['transaction_type']})"):
                            st.write(f"**Original Message:** {row['original_message']}")
                            st.write(f"**Classified as:** {row['transaction_type']}")
                            st.write(f"**Category:** {row['category']}")
                            st.write(f"**Amount:** ₹{row['amount']:,.2f}")
                
                # Save to database
                try:
                    saved_count = db.save_transactions(processed)
                    st.info(f"💾 Saved {len(processed)} transactions to database (Total: {saved_count})")
                except Exception as e:
                    st.error(f"Error saving to database: {e}")
                
                # Store in session state
                st.session_state.processed_data = processed
                st.session_state.budget_limits = {
                    'daily': daily_limit,
                    'weekly': weekly_limit,
                    'monthly': monthly_limit
                }

# Display results if data is processed
if 'processed_data' in st.session_state:
    processed = st.session_state.processed_data
    limits = st.session_state.budget_limits
    
    # Results tabs
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📊 Transactions", 
        "📈 Analytics", 
        "💰 Budget Status", 
        "📂 Categories",
        "💾 Export"
    ])
    
    with tab1:
        st.subheader("📋 Processed Transactions")
        
        # Summary metrics
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            total_expense = processed[processed['transaction_type'] == 'Expense']['amount'].sum()
            st.metric("💸 Expenses", f"₹{total_expense:,.2f}")
        with col2:
            total_income = processed[processed['transaction_type'] == 'Income']['amount'].sum()
            if total_income > 0:
                st.metric("💰 Income", f"₹{total_income:,.2f}")
            else:
                st.metric("💰 Income", "₹0.00")
        with col3:
            avg_transaction = processed['amount'].mean()
            st.metric("📊 Avg Transaction", f"₹{avg_transaction:,.2f}")
        with col4:
            st.metric("📝 Total Transactions", len(processed))
        
        # Transaction table with filtering
        st.subheader("Transaction Details")
        
        # Filters
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            category_filter = st.selectbox("Filter by Category", ['All'] + list(processed['category'].unique()))
        with col2:
            type_filter = st.selectbox("Filter by Type", ['All', 'Income', 'Expense', 'Income Only'])
        with col3:
            search_merchant = st.text_input("Search Merchant")
        with col4:
            show_income_only = st.checkbox("Show Income Only", value=False)
        
        # Apply filters
        filtered_data = processed.copy()
        if category_filter != 'All':
            filtered_data = filtered_data[filtered_data['category'] == category_filter]
        if type_filter == 'Income Only':
            filtered_data = filtered_data[filtered_data['transaction_type'] == 'Income']
        elif type_filter != 'All':
            filtered_data = filtered_data[filtered_data['transaction_type'] == type_filter]
        if search_merchant:
            filtered_data = filtered_data[filtered_data['merchant'].str.contains(search_merchant, case=False, na=False)]
        if show_income_only:
            filtered_data = filtered_data[filtered_data['transaction_type'] == 'Income']
        
        st.dataframe(filtered_data, use_container_width=True)
    
    with tab2:
        st.subheader("📈 Spending Analytics")
        
        # Time period analysis
        daily = daily_totals(processed)
        weekly = weekly_totals(processed)
        monthly = monthly_totals(processed)
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("📅 Daily Spending Trend")
            if not daily.empty:
                fig_daily = px.line(daily, x='date', y='amount', 
                                  title='Daily Expenses',
                                  labels={'date': 'Date', 'amount': 'Amount (₹)'})
                fig_daily.update_layout(showlegend=False)
                st.plotly_chart(fig_daily, use_container_width=True)
            else:
                st.info("No daily data available")
        
        with col2:
            st.subheader("📊 Weekly Spending")
            if not weekly.empty:
                fig_weekly = px.bar(weekly, x='week_start', y='amount',
                                   title='Weekly Expenses',
                                   labels={'week_start': 'Week Start', 'amount': 'Amount (₹)'})
                fig_weekly.update_xaxes(tickangle=45)
                st.plotly_chart(fig_weekly, use_container_width=True)
            else:
                st.info("No weekly data available")
        
        # Monthly overview
        st.subheader("📆 Monthly Overview")
        if not monthly.empty:
            fig_monthly = px.bar(monthly, x='month_start', y='amount',
                                title='Monthly Expenses',
                                labels={'month_start': 'Month', 'amount': 'Amount (₹)'})
            fig_monthly.update_xaxes(tickangle=45)
            st.plotly_chart(fig_monthly, use_container_width=True)
        else:
            st.info("No monthly data available")
    
    with tab3:
        st.subheader("💰 Budget Status")
        
        status = current_period_status(processed, limits['daily'], limits['weekly'], limits['monthly'])
        
        # Budget status cards
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.markdown("### 📅 Daily Budget")
            if limits['daily'] > 0:
                percentage = (status['day_total'] / limits['daily']) * 100
                st.metric("Spent", f"₹{status['day_total']:,.2f}")
                st.metric("Remaining", f"₹{status['day_remaining']:,.2f}")
                
                # Progress bar
                if percentage <= 100:
                    st.progress(min(percentage / 100, 1.0))
                    st.success(f"{percentage:.1f}% of daily budget used")
                else:
                    st.progress(1.0)
                    st.error(f"{percentage:.1f}% of daily budget used (OVER BUDGET)")
            else:
                st.info("No daily budget set")
        
        with col2:
            st.markdown("### 📆 Weekly Budget")
            if limits['weekly'] > 0:
                percentage = (status['week_total'] / limits['weekly']) * 100
                st.metric("Spent", f"₹{status['week_total']:,.2f}")
                st.metric("Remaining", f"₹{status['week_remaining']:,.2f}")
                
                if percentage <= 100:
                    st.progress(min(percentage / 100, 1.0))
                    st.success(f"{percentage:.1f}% of weekly budget used")
                else:
                    st.progress(1.0)
                    st.error(f"{percentage:.1f}% of weekly budget used (OVER BUDGET)")
            else:
                st.info("No weekly budget set")
        
        with col3:
            st.markdown("### 🗓️ Monthly Budget")
            if limits['monthly'] > 0:
                percentage = (status['month_total'] / limits['monthly']) * 100
                st.metric("Spent", f"₹{status['month_total']:,.2f}")
                st.metric("Remaining", f"₹{status['month_remaining']:,.2f}")
                
                if percentage <= 100:
                    st.progress(min(percentage / 100, 1.0))
                    st.success(f"{percentage:.1f}% of monthly budget used")
                else:
                    st.progress(1.0)
                    st.error(f"{percentage:.1f}% of monthly budget used (OVER BUDGET)")
            else:
                st.info("No monthly budget set")
    
    with tab4:
        st.subheader("📂 Category Analysis")
        
        # Category breakdown
        category_totals = processed.groupby('category')['amount'].sum().sort_values(ascending=False)
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("💸 Spending by Category")
            fig_pie = px.pie(
                values=category_totals.values,
                names=category_totals.index,
                title='Expense Distribution'
            )
            st.plotly_chart(fig_pie, use_container_width=True)
        
        with col2:
            st.subheader("📊 Category Totals")
            category_df = category_totals.reset_index()
            category_df.columns = ['Category', 'Total Amount']
            category_df['Total Amount'] = category_df['Total Amount'].apply(lambda x: f"₹{x:,.2f}")
            st.dataframe(category_df, use_container_width=True)
        
        # Monthly category trends
        st.subheader("📈 Monthly Category Trends")
        processed_copy = processed.copy()
        processed_copy['month'] = processed_copy['date'].dt.to_period('M').astype(str)
        
        monthly_category = processed_copy.groupby(['month', 'category'])['amount'].sum().reset_index()
        
        fig_trend = px.line(
            monthly_category,
            x='month',
            y='amount',
            color='category',
            title='Monthly Spending by Category',
            labels={'month': 'Month', 'amount': 'Amount (₹)', 'category': 'Category'}
        )
        st.plotly_chart(fig_trend, use_container_width=True)
    
    with tab5:
        st.subheader("💾 Export Data")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("#### 📄 Download Processed Data")
            csv_data = processed.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 Download CSV",
                data=csv_data,
                file_name=f"processed_transactions_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv"
            )
        
        with col2:
            st.markdown("#### 📊 Download Summary Report")
            # Create summary report
            summary_data = {
                'Metric': ['Total Transactions', 'Total Expenses', 'Total Income', 'Average Transaction'],
                'Value': [
                    len(processed),
                    processed[processed['transaction_type'] == 'Expense']['amount'].sum(),
                    processed[processed['transaction_type'] == 'Income']['amount'].sum(),
                    processed['amount'].mean()
                ]
            }
            summary_df = pd.DataFrame(summary_data)
            summary_csv = summary_df.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 Download Summary",
                data=summary_csv,
                file_name=f"budget_summary_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv"
            )
        
        st.markdown("#### 📋 Data Summary")
        st.json({
            "total_transactions": len(processed),
            "date_range": {
                "start": processed['date'].min().strftime('%Y-%m-%d'),
                "end": processed['date'].max().strftime('%Y-%m-%d')
            },
            "categories": list(processed['category'].unique()),
            "total_expenses": float(processed[processed['transaction_type'] == 'Expense']['amount'].sum()),
            "total_income": float(processed[processed['transaction_type'] == 'Income']['amount'].sum())
        })
