# React Native SMS Budget Tracker

## Overview
Convert your Streamlit SMS Budget Tracker into a native mobile app using React Native.

## Architecture

### Backend (Keep Existing Python)
- Your current `app.py` becomes the API backend
- Add REST API endpoints using FastAPI or Flask
- SQLite database remains the same
- SMS parsing logic stays in Python

### Frontend (New React Native App)
- React Native for cross-platform mobile app
- React Navigation for mobile navigation
- Async Storage for local caching
- React Query for API data management

## Step 1: Convert Backend to API

```python
# api.py - New file
from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from database import DataPersistence
from sms_parser import process_sms_dataframe, load_sms_xml
import pandas as pd

app = FastAPI()

# Enable CORS for mobile app
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

db = DataPersistence()

@app.post("/upload-sms")
async def upload_sms(file: UploadFile = File(...)):
    # Process SMS file
    # Save to database
    # Return processed data
    pass

@app.get("/transactions")
async def get_transactions():
    # Return all transactions
    pass

@app.get("/budget-status")
async def get_budget_status():
    # Return current budget status
    pass
```

## Step 2: Create React Native App

```bash
npx react-native init SMSBudgetTracker
cd SMSBudgetTracker
npm install @react-navigation/native @react-navigation/stack
npm install react-native-screens react-native-safe-area-context
npm install @react-native-async-storage/async-storage
npm install react-query
npm install react-native-chart-kit
```

## Step 3: Key Mobile Components

### Navigation Structure
```
- Dashboard (Home)
- Transactions List
- Budget Status
- Analytics/Charts
- Settings
- Upload SMS
```

### Key Features for Mobile
- **Offline Mode**: Cache transactions locally
- **Push Notifications**: Budget alerts
- **Biometric Auth**: Secure access
- **Dark Mode**: Mobile-friendly theme
- **Export Options**: Share reports

## Step 4: Development Plan

### Phase 1: Core Features (2-3 weeks)
1. Set up React Navigation
2. Create API integration
3. Build transaction list
4. Implement basic charts

### Phase 2: Advanced Features (2-3 weeks)
1. Offline data sync
2. Push notifications
3. Biometric authentication
4. Advanced analytics

### Phase 3: Polish & Deploy (1-2 weeks)
1. UI/UX improvements
2. Testing & bug fixes
3. App store submission
4. Documentation

## Required Libraries

### React Native Core
```json
{
  "dependencies": {
    "react": "18.2.0",
    "react-native": "0.72.0",
    "@react-navigation/native": "^6.1.0",
    "@react-navigation/stack": "^6.3.0",
    "react-native-screens": "^3.22.0",
    "react-native-safe-area-context": "^4.7.0"
  }
}
```

### Data & Charts
```json
{
  "dependencies": {
    "@tanstack/react-query": "^4.29.0",
    "react-native-chart-kit": "^6.12.0",
    "react-native-svg": "^13.9.0",
    "@react-native-async-storage/async-storage": "^1.19.0"
  }
}
```

### UI & UX
```json
{
  "dependencies": {
    "react-native-paper": "^5.8.0",
    "react-native-vector-icons": "^10.0.0",
    "react-native-reanimated": "^3.3.0",
    "react-native-gesture-handler": "^2.12.0"
  }
}
```

## File Structure
```
SMSBudgetTracker/
├── src/
│   ├── components/
│   │   ├── TransactionCard.js
│   │   ├── BudgetProgress.js
│   │   └── ChartComponent.js
│   ├── screens/
│   │   ├── Dashboard.js
│   │   ├── Transactions.js
│   │   ├── Budget.js
│   │   └── Settings.js
│   ├── services/
│   │   ├── api.js
│   │   └── storage.js
│   ├── navigation/
│   │   └── AppNavigator.js
│   └── utils/
│       └── helpers.js
├── android/
├── ios/
└── package.json
```

## API Integration Example

```javascript
// services/api.js
import axios from 'axios';

const API_BASE_URL = 'http://localhost:8000';

export const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 10000,
});

export const uploadSMS = async (file) => {
  const formData = new FormData();
  formData.append('file', file);
  
  const response = await api.post('/upload-sms', formData, {
    headers: { 'Content-Type': 'multipart/form-data' }
  });
  
  return response.data;
};

export const getTransactions = async () => {
  const response = await api.get('/transactions');
  return response.data;
};
```

## Next Steps

1. **Start with PWA** (Easiest - 1-2 days)
2. **React Native** (Medium - 4-6 weeks)
3. **Flutter** (Alternative - 4-6 weeks)

## Cost & Time Estimates

### PWA Conversion
- **Time**: 1-2 days
- **Cost**: Minimal
- **Features**: Mobile web app, installable

### React Native App
- **Time**: 6-8 weeks
- **Cost**: Development time + app store fees
- **Features**: Full native app, offline mode, notifications

### Flutter App
- **Time**: 6-8 weeks  
- **Cost**: Development time + app store fees
- **Features**: Cross-platform native app

## Recommendation

**Start with PWA** to get mobile-friendly quickly, then **progress to React Native** if you need full native features like offline mode and push notifications.
