# ChargeFindr AI: Intelligent EV Charging Station Recommendation, Demand Prediction, Slot Booking, and Rapid Queue System

**Final Year Engineering Project**  
*Implementation & Release Review: October 2026*

---

## 1. Project Overview & Architecture

**ChargeFindr AI** is an enterprise-grade, full-stack decision-support and operations platform designed to optimize electric vehicle (EV) charging station selection, forecast session charging demand, manage reserved slot bookings, and coordinate rapid walk-in charging queues. The platform prevents long waiting queues, balances charging load across urban centers, and provides human-interpretable station recommendations alongside robust role-based access control.

### Architecture Data Flow:
```text
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                        Browser Client (HTML5 / Modern CSS / JavaScript)                 │
│  • Full-Screen EV Auth Landing Page  • Interactive Hyderabad Google Maps & Directions  │
│  • 24-Hour Diurnal Demand Forecast   • Slot Booking & Rapid Walk-in Queue Modals       │
└───────────────────────────────────────────┬────────────────────────────────────────────┘
                                            │ REST API / JSON (Session + CSRF Protection)
                                            ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                               Flask Application Backend (Port 5000)                    │
│                                                                                        │
│  ├── auth_routes.py & auth_service.py         ──> Authentication, Sessions, CSRF, RBAC │
│  ├── station_routes.py                        ──> Station Catalog & Admin Station CRUD │
│  ├── recommendation_routes.py & service       ──> Multi-Criteria Utility Ranking       │
│  ├── demand_routes.py & demand_service.py     ──> ML Random Forest Regressor (joblib)  │
│  ├── booking_routes.py & booking_service.py   ──> Reserved Slot Booking (Concurrency)  │
│  └── queue_routes.py & queue_service.py       ──> Rapid Walk-in Queue (FIFO Tokens)    │
└───────────────────────────────────────────┬────────────────────────────────────────────┘
                                            │
                                            ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                              MySQL Relational Database (chargefindr_ai)                │
│  ├── users              ──> User Credentials (scrypt), Full Names, Roles (USER/ADMIN)  │
│  ├── charging_stations  ──> Station Locations, Total/Available Ports, Pricing, Status  │
│  ├── station_chargers   ──> Physical Chargers & Connectors (CCS2, Type 2, CHAdeMO)     │
│  ├── station_bookings   ──> Scheduled Slot Reservations, Timestamps, Booking Status    │
│  └── walkin_queue       ──> Live Walk-in Queue Tokens, Priority Sequence, Wait Times   │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Project Modules Implemented

1. **User Input & Preference Selection (Module 1)**: Allows drivers to filter by Hyderabad localities (Madhapur, Hitech City, Kondapur, Gachibowli, Kukatpally), charger type (Fast DC vs AC Type 2), and optimization priorities (Fastest Charging, Minimal Wait, Highest Reliability).
2. **AI Station Recommendation Engine (Module 2)**: Evaluates available ports, estimated wait queues, proximity/area matching, charging power, and congestion levels with explainable rationale bullet points.
3. **Charging Demand Prediction — Machine Learning (Module 3)**:
   - Trained on 72,856 sessions from the Figshare EV Charging Transactions dataset (`ml/ChargingRecords.csv`).
   - Strict **80/20 Chronological Split** (58,284 train / 14,572 test) to prevent future temporal data leakage.
   - Algorithm: `RandomForestRegressor` with 10 extracted features (hour, day of week, month, weekend flag, charger type code, and 5 one-hot location categories).
   - Validated Metrics: **MAE = 10.29 kWh**, **RMSE = 13.44 kWh**, and **R² = 0.0667**.
   - **Academic & Diagnostic Note**: Predictive performance reflects real-world transaction data ($R^2 \approx 6.67\%$). Results are experimental. Individual transaction energy demand is largely governed by unobserved physical vehicle attributes (such as battery pack capacity and incoming State-of-Charge) that are absent from public transaction logs.
4. **Interactive 24-Hour Forecast Curve (Module 4)**: Displays hourly expected charging demand (kWh) across the day for diurnal profile evaluation and station load planning.
5. **Smart Alerts & Congestion Notification (Module 5)**: Real-time backend alerts querying MySQL to detect full stations (0 ports available or wait > 20 mins) and recommend alternative low-wait stations using Haversine distance.
6. **Authentication & Role-Based Access Control — RBAC (Module 6)**: Secure user registration and login with `scrypt` password hashing, signed Flask session cookies (`HttpOnly`, `SameSite=Lax`), timing-safe CSRF tokens (`X-CSRF-Token`), and administrator-protected telemetry (`@admin_required`).
7. **Live Database Integration & Admin Management (Module 7)**: Station status, charger hardware, user accounts, bookings, and queues managed via local MySQL database `chargefindr_ai`. Includes full Admin Station CRUD (Add, Edit, Delete stations).
8. **Reserved Slot Booking System (Module 8)**:
   - Dedicated booking interface with real-time slot availability lookup.
   - Strict input validation: Full Name, Vehicle Model, Registration Number, Date, Start Time, and Duration.
   - Concurrency protection preventing overlapping confirmed bookings on physical chargers using MySQL row-level locking (`FOR UPDATE`).
   - Booking lifecycle management: `CONFIRMED`, `COMPLETED`, `CANCELLED`, `MISSED`.
   - Cancellation policy with automatic port release and alternative slot recommendation upon missed or conflicting reservations.
9. **Rapid Walk-in Charging Queue (Module 9)**:
   - FIFO walk-in token issuance (`Q-001`, `Q-002`, etc.) for drivers arriving directly at stations without prior reservation.
   - Dynamic real-time estimated wait time calculation based on active queue position.
   - Token lifecycle: `WAITING`, `CHARGING`, `COMPLETED`, `CANCELLED`.
   - In-app queue status tracking and user self-cancellation.
10. **Premium UI Redesign & Dedicated Landing Experience (Module 10)**:
    - Dedicated, responsive full-screen landing page with high-resolution EV charging station background image and authentication panel.
    - Clean, modern light aesthetic with bright white surfaces (`#ffffff`), soft neutral canvas (`#f8fafc`), subtle borders (`#e2e8f0`), and vibrant emerald green accents (`#059669`).
    - Interactive modals for Reserved Slot Booking, Rapid Walk-in Queue, Admin Management, and System Telemetry.
    - Dynamic Google Maps integration with station markers and turn-by-turn driving directions.

---

## 3. Technology Stack

- **Backend**: Python 3.14, Flask, REST APIs, Werkzeug Security (`scrypt`), Secrets module
- **Database**: MySQL Server (v8.0+), `mysql-connector-python`, row-level concurrency locking (`FOR UPDATE`)
- **Machine Learning & Data**: Scikit-Learn (`RandomForestRegressor`), Pandas, NumPy, Joblib
- **Frontend**: Vanilla HTML5, Modern CSS3 (CSS Custom Properties, Flexbox, CSS Grid, Glassmorphism, Responsive Breakpoints), Vanilla JavaScript ES6+ (Fetch API, DOM manipulation, Google Maps JavaScript API)
- **Security**: CSRF double-submit token validation, HttpOnly SameSite=Lax signed session cookies, password hashing with scrypt, role-based access decorators (`@login_required`, `@admin_required`)
- **Testing**: Python `unittest` framework with 58 automated integration and unit test cases

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
Copy the provided `.env.example` file to create your local `.env`:
```powershell
Copy-Item .env.example .env
```
Open `.env` and fill in your local MySQL credentials:
```env
# ============================================================================
# ChargeFindr AI — Local Environment Configuration
# NEVER commit this file or real credentials to GitHub.
# ============================================================================

# MySQL Database Configuration
DB_HOST=127.0.0.1
DB_USER=root
DB_PASSWORD=YOUR_MYSQL_PASSWORD
DB_NAME=chargefindr_ai
DB_PORT=3306

# Flask Session Security Secret Key
# MUST be a long, cryptographically random string.
# Generate one via: python -c "import secrets; print(secrets.token_hex(32))"
SECRET_KEY=YOUR_GENERATED_SECRET_KEY_HEX

# Session Security Settings
FLASK_ENV=development
SESSION_LIFETIME_HOURS=8
SESSION_COOKIE_SECURE=false
```

> **SECURITY NOTICE**:
> - `SECRET_KEY` is required for Flask session encryption, session fixation prevention, and CSRF token security. If `SECRET_KEY` is missing, the backend will refuse to start.
> - The `.env` file contains sensitive local credentials and must **never** be committed to Git. It is excluded by `.gitignore`.

### Step 3: Database Initialization
For detailed schema documentation and database design, refer to [`backend/database/DATABASE_SETUP.md`](backend/database/DATABASE_SETUP.md).

1. Ensure your MySQL server is running on port `3306`.
2. Create the database:
   ```sql
   CREATE DATABASE IF NOT EXISTS chargefindr_ai;
   ```
3. Seed the demonstration charging stations using the provided snapshot:
   ```powershell
   mysql -u root -p chargefindr_ai < backend/database/backup_charging_stations_freeze_20261025.sql
   ```
4. *(The tables `users`, `station_chargers`, `station_bookings`, and `walkin_queue` are automatically created and verified by the backend on boot).*

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
- Unauthenticated visitors will see the full-screen EV Charging Station Landing Page with login and registration.
- After logging in, the full interactive ChargeFindr AI dashboard, Google Maps, slot booking, and queue management modules are displayed.

---

## 5. REST API Endpoints Catalog

The platform exposes 28 RESTful API endpoints secured by CSRF tokens and Role-Based Access Control (RBAC):

| # | Method | Endpoint | Access Level | Description |
| :---: | :--- | :--- | :---: | :--- |
| **System & Stations** | | | | |
| 1 | `GET` | `/api/health` | Public | Verifies Flask server and MySQL connectivity |
| 2 | `GET` | `/api/stations` | Public / User | Retrieves all charging station records from MySQL |
| 3 | `GET` | `/api/stations/locations` | Public | Retrieves distinct database-driven locations for dropdown |
| 4 | `GET` | `/api/stations/alerts` | Public | Returns active congestion alerts and alternative suggestions |
| 5 | `POST` | `/api/stations` | Admin Only (CSRF) | Adds a new charging station record to MySQL |
| 6 | `PUT` | `/api/stations/<id>` | Admin Only (CSRF) | Updates an existing station's details, ports, or pricing |
| 7 | `DELETE` | `/api/stations/<id>` | Admin Only (CSRF) | Deletes a charging station record from MySQL |
| **Recommendations** | | | | |
| 8 | `POST` | `/api/recommend` | User / Public | Multi-criteria utility ranking based on location and charger preferences |
| **Demand Analytics** | | | | |
| 9 | `GET` | `/api/demand` | User / Authenticated | ML demand prediction for specific hour/day & 24-hour curve |
| 10 | `GET` | `/api/demand/metadata` | Public | Returns dynamic ML evaluation metrics ($MAE$, $RMSE$, $R^2$) and split details |
| **Authentication & Session** | | | | |
| 11 | `GET` | `/api/auth/csrf` | Public | Generates and returns session-scoped CSRF token |
| 12 | `POST` | `/api/auth/register` | Public (CSRF) | Registers a new user account strictly with `role='user'` |
| 13 | `POST` | `/api/auth/login` | Public (CSRF) | Authenticates credentials, rotates session, and sets HttpOnly cookie |
| 14 | `POST` | `/api/auth/logout` | User (CSRF) | Invalidates active session and purges identity cookies |
| 15 | `GET` | `/api/auth/me` | Public / Authenticated | Returns current authenticated session profile |
| **Admin Operations** | | | | |
| 16 | `GET` | `/api/admin/overview` | Admin Only | System telemetry, station stats, and user counts (`@admin_required`) |
| 17 | `GET` | `/api/admin/users` | Admin Only | Lists registered users and role distribution |
| 18 | `GET` | `/api/admin/bookings` | Admin Only | Lists all scheduled bookings across all stations |
| 19 | `GET` | `/api/admin/queues` | Admin Only | Lists active and historical walk-in queues across all stations |
| **Reserved Slot Booking** | | | | |
| 20 | `GET` | `/api/bookings/available-slots` | Authenticated | Returns available 1-hour time slots for a given station and date |
| 21 | `POST` | `/api/bookings` | Authenticated (CSRF) | Creates a reserved slot booking with concurrency row-level lock |
| 22 | `GET` | `/api/bookings/my` | Authenticated | Returns all slot bookings created by the current user |
| 23 | `POST` | `/api/bookings/<id>/cancel` | Authenticated (CSRF) | Cancels a booking and releases the reserved charger slot |
| 24 | `GET` | `/api/bookings/<id>/alternatives` | Authenticated | Recommends alternative available slots if a booking is missed |
| **Rapid Walk-in Queue** | | | | |
| 25 | `GET` | `/api/queue/status/<id>` | Public / User | Returns current walk-in queue depth and wait time for a station |
| 26 | `POST` | `/api/queue/join` | Authenticated (CSRF) | Enqueues a driver and issues a unique FIFO queue token |
| 27 | `GET` | `/api/queue/my` | Authenticated | Returns the active queue ticket for the current user |
| 28 | `POST` | `/api/queue/<id>/cancel` | Authenticated (CSRF) | Cancels an active walk-in queue ticket and updates queue positions |

---

## 6. Automated Test Suites & Verification

The project includes 58 automated unit and integration tests covering security, machine learning, data integrity, slot booking, walk-in queue, and UI contracts:

| Test File | Tests | Focus Area |
| :--- | :---: | :--- |
| `test_booking_and_queue.py` | 11 | Reserved slot booking, row locking, walk-in queue FIFO, and cancellations |
| `test_stage6_auth.py` | 10 | CSRF protection, scrypt hashing, role escalation prevention, and session rotation |
| `test_auth_rbac_stations.py` | 6 | Dashboard API protection, USER vs ADMIN RBAC, and admin station CRUD |
| `tests_module2_verification.py` | 5 | Multi-criteria recommendation engine and utility scoring |
| `tests_module3_verification.py` | 7 | Machine learning data pipeline, chronological split, and model persistence |
| `tests_module4_verification.py` | 5 | 24-hour diurnal demand curve, input validation, and boundary conditions |
| `tests_module6_verification.py` | 10 | Haversine distance, congestion alert routing, and alternative recommendations |
| `tests_module7_verification.py` | 4 | Dynamic R² metric display, chart interactivity, and admin telemetry contracts |

### Running the Full Test Suite:
```powershell
# Run all test suites sequentially
.\.venv\Scripts\python.exe test_booking_and_queue.py
.\.venv\Scripts\python.exe test_stage6_auth.py
.\.venv\Scripts\python.exe test_auth_rbac_stations.py
.\.venv\Scripts\python.exe tests_module2_verification.py
.\.venv\Scripts\python.exe tests_module3_verification.py
.\.venv\Scripts\python.exe tests_module4_verification.py
.\.venv\Scripts\python.exe tests_module6_verification.py
.\.venv\Scripts\python.exe tests_module7_verification.py
```
*All 58 test cases execute and pass with 0 failures and 0 errors.*

---

## 7. Demonstration Notes & Project Limitations

1. **Demonstration Station Records**: The 5 stations located in Hyderabad (Madhapur, Kondapur, Hitech City, Gachibowli, Kukatpally) are **demonstration sample records stored in MySQL**, not live IoT sensor feeds or real-time verified hardware feeds. They serve to validate multi-criteria ranking, queue analysis, dynamic dropdowns, slot reservations, and congestion alert algorithms.
2. **Predictive Performance**: As noted, the Random Forest model achieves $MAE = 10.29\text{ kWh}$ and $R^2 = 0.0667$. Because individual transaction energy depends on vehicle battery capacity and incoming battery state-of-charge, the current model provides baseline heuristic predictions and is considered experimental.
3. **Dataset Verification**: The underlying training dataset is identified as the Figshare EV Charging Transactions dataset (`ml/ChargingRecords.csv`). The exact publication link, DOI, and license terms require independent verification.
4. **Google Maps Integration**: Google Maps JavaScript API integration operates with visual fallbacks if a custom API key is not supplied in `frontend/script.js`.
