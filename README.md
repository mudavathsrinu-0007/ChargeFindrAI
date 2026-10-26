# ChargeFindr AI: Intelligent EV Charging Station Recommendation and Demand Prediction System

**Final Year Engineering Project**  
*Implementation Review Date: 26 October 2026*

---

## 1. Project Overview & Architecture

ChargeFindr AI is a full-stack decision-support system designed to optimize electric vehicle (EV) charging station selection and forecast session charging demand. It prevents long waiting queues, balances charging load, and provides human-interpretable station recommendations.

### Architecture Data Flow:
```text
[ Browser (HTML/CSS/JS) ]
         │
         ▼  (REST API / JSON)
  [ Flask Backend (Port 5000) ]
     ├── station_routes.py        ──> [ MySQL DB: charging_stations ]
     ├── recommendation_service.py ──> Multi-Criteria Utility Ranking
     ├── demand_service.py        ──> [ Random Forest Model (joblib) ]
     └── auth_routes.py           ──> [ MySQL DB: users ] (RBAC & Sessions)
```

---

## 2. Project Modules Implemented

1. **User Input & Preference Selection**: Allows drivers to filter by Hyderabad localities (Madhapur, Hitech City, Kondapur, Gachibowli, Kukatpally), charger type (Fast DC vs AC Type 2), and optimization priority.
2. **AI Station Recommendation Engine**: Evaluates available ports, estimated wait queues, proximity/area matching, charging power, and congestion levels with explainable rationale bullet points.
3. **Charging Demand Prediction (Machine Learning)**:
   - Trained on 72,856 sessions from the Figshare EV Charging Transactions dataset (`ml/ChargingRecords.csv`).
   - Strict **80/20 Chronological Split** (58,284 train / 14,572 test) to prevent future temporal data leakage.
   - Algorithm: `RandomForestRegressor` with 10 extracted features (hour, day of week, month, weekend flag, charger type code, and 5 one-hot location categories).
   - Validated Metrics: **MAE = 10.29 kWh**, **RMSE = 13.44 kWh**, and **R² = 0.0667**.
   - **Academic & Diagnostic Note**: Predictive performance is currently weak ($R^2 \approx 6.67\%$). Results are experimental. Individual transaction energy demand is largely governed by unobserved physical vehicle attributes (such as battery pack capacity and incoming State-of-Charge) that are absent from public transaction logs.
   - **Dataset Source & License Notice**: While labeled as the Figshare EV Charging Transactions dataset, the exact publication DOI/URL and licensing terms are not recorded in the project files and still require formal verification.
4. **Interactive 24-Hour Forecast Curve**: Displays hourly expected charging demand (kWh) across the day for diurnal profile evaluation.
5. **Smart Alerts & Congestion Notification**: Real-time backend alerts querying MySQL to detect full stations (0 ports available or wait > 20 mins) and recommend alternative low-wait stations.
6. **Authentication & Role-Based Access Control (RBAC)**: Secure user registration and login with `scrypt` password hashing, signed Flask session cookies (`HttpOnly`, `SameSite=Lax`), timing-safe CSRF tokens (`X-CSRF-Token`), and administrator-protected telemetry (`@admin_required`).
7. **Live Database Integration**: Station status and user accounts managed via local MySQL database `chargefindr_ai`.

---

## 3. Technology Stack

- **Backend**: Python 3.14, Flask, REST APIs, Werkzeug Security (`scrypt`)
- **Database**: MySQL (`mysql-connector-python`)
- **Machine Learning & Data**: Scikit-Learn (`RandomForestRegressor`), Pandas, NumPy, Joblib
- **Frontend**: HTML5, Modern CSS3 (responsive grid, status badges, dark mode styling), JavaScript (Fetch API, Google Maps JS API integration)
- **Version Control**: Git

---

## 4. Setup and Execution Instructions

### Prerequisites
- Python 3.10+ (tested and verified on Python 3.14)
- MySQL Server (v8.0+ or compatible) running on port `3306`

### Step 1: Clone & Set Up Python Environment
Navigate to the `ChargeFindrAI` project directory:
```powershell
cd ChargeFindrAI

# Create virtual environment
python -m venv .venv

# Activate virtual environment (Windows PowerShell)
.\.venv\Scripts\Activate.ps1

# (On Linux / macOS: source .venv/bin/activate)

# Install required dependencies
pip install -r requirements.txt
```

### Step 2: Configure Environment Variables (`.env`)
Create a file named `.env` in the root of the `ChargeFindrAI/` directory:
```env
# ============================================================================
# ChargeFindr AI — Local Environment Configuration
# NEVER commit this file or real credentials to GitHub.
# ============================================================================

# MySQL Database Configuration
DB_HOST=localhost
DB_USER=root
DB_PASSWORD=YOUR_MYSQL_PASSWORD
DB_NAME=chargefindr_ai
DB_PORT=3306

# Flask Session Security Secret Key
# MUST be a long, cryptographically random string.
# Generate one via: python -c "import secrets; print(secrets.token_hex(32))"
SECRET_KEY=YOUR_GENERATED_SECRET_KEY_HEX
```

> **IMPORTANT SECURITY NOTICE**:
> - `SECRET_KEY` is required for Flask session encryption, session fixation prevention, and CSRF security. If `SECRET_KEY` is missing, the backend will fail to start.
> - `SECRET_KEY` must be a long, random secret.
> - The `.env` file contains sensitive local credentials and must **never** be committed to GitHub. It is protected by `.gitignore`.

### Step 3: Database Initialization
1. Ensure your MySQL server is running.
2. Create the database:
   ```sql
   CREATE DATABASE IF NOT EXISTS chargefindr_ai;
   ```
3. Seed the demonstration charging stations using the provided SQL snapshot:
   ```powershell
   mysql -u root -p chargefindr_ai < backend/database/backup_charging_stations_freeze_20261025.sql
   ```
   *(The `users` table is automatically initialized by `ensure_users_table()` when the backend boots).*

### Step 4: Run the Backend Server
From the `ChargeFindrAI/` directory with the virtual environment activated:
```powershell
python backend/app.py
```
The server will start on `http://127.0.0.1:5000`.

### Step 5: Open the Application
Open your web browser and navigate to:
```text
http://127.0.0.1:5000
```
*(The dashboard and interactive map will load directly from the Flask static file provider).*

---

## 5. API Endpoints Reference

| Method | Endpoint | Access | Description |
| :--- | :--- | :---: | :--- |
| `GET` | `/api/health` | Public | Verifies Flask server and MySQL connectivity |
| `GET` | `/api/stations` | Public | Retrieves all 5 station records from MySQL |
| `GET` | `/api/stations/locations` | Public | Retrieves distinct database-driven locations for dropdown |
| `GET` | `/api/stations/alerts` | Public | Returns active congestion alerts and alternative suggestions |
| `POST` | `/api/recommend` | Public | Multi-criteria utility ranking based on location and charger preferences |
| `GET` | `/api/demand` | Public | ML demand prediction for specific hour/day & 24-hour curve |
| `GET` | `/api/demand/metadata` | Public | Returns dynamic ML evaluation metrics and split details |
| `GET` | `/api/auth/csrf` | Public | Generates and returns session CSRF token |
| `POST` | `/api/auth/register` | Public (CSRF) | Registers a new user account with `role='user'` |
| `POST` | `/api/auth/login` | Public (CSRF) | Authenticates credentials, rotates session, and sets HttpOnly cookie |
| `POST` | `/api/auth/logout` | User (CSRF) | Invalidates active session and purges identity cookies |
| `GET` | `/api/auth/me` | Public | Returns current authenticated session profile |
| `GET` | `/api/admin/overview` | Admin Only | System telemetry and database counts (`@admin_required`) |

---

## 6. Demonstration Notes & Project Limitations

1. **Demonstration Station Records**: The 5 stations located in Hyderabad (Madhapur, Kondapur, Hitech City, Gachibowli, Kukatpally) are **demonstration sample records stored in MySQL**, not live IoT sensor feeds or real-time verified hardware feeds. They serve to validate multi-criteria ranking, queue analysis, dynamic dropdowns, and congestion alert algorithms.
2. **Predictive Performance**: As noted, the Random Forest model achieves $MAE = 10.29\text{ kWh}$ and $R^2 = 0.0667$. Because individual transaction energy depends on vehicle battery capacity and incoming battery state-of-charge, the current model provides baseline heuristic predictions and is considered experimental.
3. **Dataset Verification**: The underlying training dataset is identified as the Figshare EV Charging Transactions dataset. The exact publication link, DOI, and license terms require independent verification.
4. **Google Maps Integration**: Google Maps JavaScript API integration operates with visual fallbacks if a custom API key is not supplied in `frontend/script.js`.
