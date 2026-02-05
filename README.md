# SMS Budget Tracker

A comprehensive SMS-based expense tracking and budgeting application built with Streamlit.

## Features

- 📱 **SMS Parsing**: Automatically extracts financial transactions from SMS data
- 💰 **Budget Tracking**: Set and monitor daily, weekly, and monthly budgets
- 📊 **Interactive Analytics**: Beautiful charts and visualizations with Plotly
- 🗄️ **Data Persistence**: SQLite database for storing transaction history
- 📂 **Category Analysis**: Automatic categorization of expenses
- 💾 **Export Options**: Download processed data and summary reports
- 🔍 **Advanced Filtering**: Filter transactions by category, type, and merchant
- 🎨 **Modern UI**: Beautiful, responsive interface with custom styling

## Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd budgeting_app
```

2. Create and activate a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

## Usage

### Running Locally

1. Start the Streamlit app:
```bash
streamlit run app.py
```

2. Open your browser and navigate to `http://localhost:8501`

3. Upload your SMS data (CSV or XML format) and start tracking!

### Data Formats

#### CSV Format
Your CSV should contain columns with:
- Message content (body, content, message, sms, text)
- Date/timestamp (date, datetime, timestamp, time, sent, received)
- Optional: Sender information (sender, from, address, contact_name)

#### XML Format
Standard Android SMS Backup & Restore XML format is supported with auto-detection of:
- `body` (message content)
- `date` or `readable_date` (timestamp)
- `address` / `contact_name` (sender information)
- MMS entries with text extraction

## Project Structure

```
budgeting_app/
├── app.py              # Main Streamlit application
├── sms_parser.py       # SMS parsing and transaction extraction
├── classifier.py       # Transaction categorization
├── budget.py           # Budget calculation functions
├── database.py         # Data persistence layer
├── requirements.txt    # Python dependencies
└── README.md          # This file
```

## Key Features

### Transaction Processing
- Automatic detection of financial SMS messages
- Amount extraction with support for INR/RS formats
- Merchant name extraction from transaction messages
- Income vs Expense classification
- Category assignment (Food, Travel, Shopping, Bills, Health, Other)

### Budget Management
- Set daily, weekly, and monthly budget limits
- Real-time budget tracking with progress indicators
- Over-budget warnings and alerts
- Persistent budget storage

### Analytics & Visualization
- Interactive charts using Plotly
- Daily, weekly, and monthly spending trends
- Category-wise expense breakdown
- Monthly category trends analysis
- Budget status dashboards

### Data Management
- SQLite database for persistent storage
- Historical data loading
- Export functionality for processed data
- Advanced filtering options

## Deployment

### Docker Deployment

1. Create a `Dockerfile`:
```dockerfile
FROM python:3.9-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
EXPOSE 8501

CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]
```

2. Build and run:
```bash
docker build -t sms-budget-tracker .
docker run -p 8501:8501 sms-budget-tracker
```

### Streamlit Cloud Deployment

1. Push your code to a GitHub repository
2. Connect your repository to [Streamlit Cloud](https://streamlit.io/cloud)
3. Deploy with one click

### Heroku Deployment

1. Create a `Procfile`:
```
web: streamlit run app.py --server.port=$PORT --server.address=0.0.0.0
```

2. Create a `runtime.txt`:
```
python-3.9.0
```

3. Deploy:
```bash
heroku create your-app-name
git push heroku main
```

## Privacy & Security

- All data processing happens locally in your browser
- No data is sent to external servers
- SMS content is only used for transaction extraction
- Database is stored locally on your machine
- Complete privacy for your financial data

## Configuration

The app automatically creates a SQLite database (`budget_data.db`) for data persistence. All settings and data are stored locally.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

## License

This project is licensed under the MIT License.

## Support

For issues and questions, please open an issue on the GitHub repository.
