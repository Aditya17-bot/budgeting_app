# SMS Budgeting App

A privacy-friendly SMS expense tracker that processes exported SMS backups (CSV or XML), extracts transactions, categorizes them, and visualizes spending with Streamlit.

## What You Get
- Rule-based SMS parsing (no cloud upload).
- Income vs Expense classification.
- Category tagging (food, travel, shopping, bills, health, other).
- Daily/weekly totals and budget warnings.
- CSV output of processed transactions.

## Requirements
- Python 3.9+
- Packages in `requirements.txt`

## Run
```bash
pip install -r requirements.txt
streamlit run app.py
```

## CSV Expectations
Your CSV must include at least:
- A message/text column (SMS body)
- A date or timestamp column

You can choose the columns in the Streamlit UI.

### Example Header
```
Type,Date,Name/Number Sender,Content
```

## XML Support
The app supports SMS Backup & Restore XML exports. It auto-loads the common fields:
- `body` (message)
- `date` or `readable_date`
- `address` / `contact_name` for sender

It also reads `mms` entries when present and extracts text from MMS parts.

## Output
The app generates a processed table and lets you download a CSV.
