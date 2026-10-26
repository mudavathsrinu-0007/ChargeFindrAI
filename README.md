# ChargeFindr AI: Intelligent EV Charging Station Recommendation and Demand Prediction System

**Final Year Engineering Project**  
*Implementation Review Date: 26 October 2026*

---

## 1. Project Overview & Architecture

ChargeFindr AI is a full-stack decision-support system designed to optimize electric vehicle (EV) charging station selection and forecast grid charging demand. It prevents long waiting queues, balances charging load, and provides human-interpretable station recommendations.

### Architecture Data Flow:
```text
[ Browser (HTML/CSS/JS) ]
         │
         ▼  (REST API / JSON)
  [ Flask Backend (Port 5000) ]
     ├── station_routes.py        ──> [ MySQL DB: charging_stations ]
     ├── recommendation_service.py ──> Multi-Criteria Utility Ranking
     └── demand_service.py        ──> [ Random Forest Model (joblib) ]
```

---

## 2. Project Modules Implemented

1. **User Input & Preference Selection**: Allows drivers to filter by Hyderabad localities (Madhapur, Hitech City, Kondapur, Gachibowli, Kukatpally), charger type (Fast DC vs AC Type 2), and optimization priority.
2. **AI Station Recommendation Engine**: Evaluates available ports, estimated wait queues, proximity/area matching, charging power, and congestion levels with explainable rationale bullet points.
3. **Charging Demand Prediction (Machine Learning)**:
   - Trained on the Figshare EV Charging Transactions dataset (**72,856 sessions**).
   - Strict **80/20 Chronological Split** (58,284 train / 14,572 test) to avoid future temporal data leakage.
   - Algorithm: `RandomForestRegressor` with extracted time features (hour, day of week, month, weekend flag, charger type, location category).
   - Validated Metrics: **MAE = 10.29 kWh**, **RMSE = 13.44 kWh**, **R² = 0.0667**.
4. **Interactive 24-Hour Forecast Curve**: Displays hourly expected charging demand (kWh) across the day to identify off-peak charging hours.
5. **Smart Alerts & Congestion Notification**: Automatically alerts the user if a preferred station has 0 open ports and proposes the nearest low-queue alternative.
6. **Live Database Integration**: Real-time retrieval of station status from local MySQL database `chargefindr_ai`.

---

## 3. Technology Stack

- **Backend**: Python 3.14, Flask, REST APIs
- **Database**: MySQL (`mysql-connector-python`)
- **Machine Learning & Data**: Scikit-Learn (`RandomForestRegressor`), Pandas, NumPy, Joblib
- **Frontend**: HTML5, Modern CSS3 (responsive grid, custom chart bars), JavaScript (Async/Await `fetch`)
- **Version Control**: Git

---

## 4. Setup and Execution Instructions

### Prerequisites
- Python 3.10+ (tested and verified on Python 3.14.0)
- MySQL Server running locally on port `3306` with database `chargefindr_ai` and table `charging_stations`

### Step 1: Environment Variables
Create or verify `.env` in the `ChargeFindrAI/` directory:
```env
DB_HOST=localhost
DB_USER=root
DB_PASSWORD=YOUR_MYSQL_PASSWORD
DB_NAME=chargefindr_ai
DB_PORT=3306
```

### Step 2: Run Backend Server
From the `ChargeFindrAI` directory with virtual environment activated:
```powershell
python backend/app.py
```

### Step 3: Open the Dashboard
Open your web browser and navigate to:
```text
http://127.0.0.1:5000
```
*(Alternatively, you can also open `frontend/index.html` via VS Code Live Server or directly in your browser).*

---

## 5. API Endpoints Reference

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/api/health` | Verifies Flask server and MySQL connectivity |
| `GET` | `/api/stations` | Retrieves all 5 station records from MySQL |
| `POST` | `/api/recommend` | Accepts user location & charger preferences, returns ranked stations |
| `GET` | `/api/demand` | Returns demand prediction for a specific hour & 24-hour hourly curve |

---

## 6. Demonstration Notes & Limitations for Viva / Review

1. **Demonstration Records**: The 5 stations in Hyderabad are representative demonstration records to test multi-criteria ranking, queue analysis, and availability filtering.
2. **Explainability**: Each station card explicitly lists *why* it received its ranking score, fulfilling the project's explainable AI goal.
3. **No False Claims**: Distance calculations use the verified demo distance attributes; GPS haversine coordinates can be hooked in future extensions.

