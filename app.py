import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt

from parser import process_sms_dataframe
from budget import daily_totals, weekly_totals, check_budget_limits

st.set_page_config(page_title="SMS Budgeting", layout="wide")

st.title("SMS Expense Tracking and Budgeting")

uploaded_file = st.file_uploader("Upload SMS CSV", type=["csv"])

if uploaded_file:
    df = pd.read_csv(uploaded_file)
    st.subheader("CSV Preview")
    st.dataframe(df.head(20))

    columns = list(df.columns)

    def guess_column(candidates):
        lowered = {c.lower(): c for c in columns}
        for key in candidates:
            if key in lowered:
                return lowered[key]
        return ""

    message_default = guess_column(["content", "body", "message", "sms", "text"])
    date_default = guess_column(["date", "datetime", "timestamp", "time", "sent", "received"])
    sender_default = guess_column(["name/number sender", "sender", "from", "address", "name"])

    if not columns:
        st.error("No columns detected in CSV.")
        st.stop()

    message_index = columns.index(message_default) if message_default in columns else 0
    date_index = columns.index(date_default) if date_default in columns else 0

    message_col = st.selectbox("Message Column", options=columns, index=message_index)
    date_col = st.selectbox("Date Column", options=columns, index=date_index)

    sender_options = ["(None)"] + columns
    sender_index = sender_options.index(sender_default) if sender_default in sender_options else 0
    sender_selection = st.selectbox("Sender Column (optional)", options=sender_options, index=sender_index)
    sender_col = None if sender_selection == "(None)" else sender_selection

    st.sidebar.header("Budgets")
    daily_limit = st.sidebar.number_input("Daily Budget Limit", min_value=0.0, value=0.0, step=100.0)
    weekly_limit = st.sidebar.number_input("Weekly Budget Limit", min_value=0.0, value=0.0, step=500.0)

    if st.button("Process SMS"):
        processed = process_sms_dataframe(df, message_col, date_col, sender_col)
        if processed.empty:
            st.warning("No valid transaction SMS messages found.")
        else:
            st.subheader("Processed Transactions")
            st.dataframe(processed)

            st.download_button(
                "Download Processed CSV",
                data=processed.to_csv(index=False).encode("utf-8"),
                file_name="processed_transactions.csv",
                mime="text/csv",
            )

            daily = daily_totals(processed)
            weekly = weekly_totals(processed)

            st.subheader("Daily Totals")
            st.dataframe(daily)

            st.subheader("Weekly Totals")
            st.dataframe(weekly)

            st.subheader("Category Breakdown")
            category_totals = processed.groupby("category")["amount"].sum()
            fig, ax = plt.subplots()
            ax.pie(category_totals, labels=category_totals.index, autopct="%1.1f%%")
            ax.axis("equal")
            st.pyplot(fig)

            daily_exceeded, weekly_exceeded = check_budget_limits(daily, weekly, daily_limit, weekly_limit)

            if daily_exceeded:
                st.error(f"Daily budget exceeded. Highest day: {daily_exceeded:.2f}")
            if weekly_exceeded:
                st.error(f"Weekly budget exceeded. Highest week: {weekly_exceeded:.2f}")
