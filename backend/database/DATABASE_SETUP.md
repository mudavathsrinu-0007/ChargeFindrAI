# ChargeFindr AI — Database Setup & Architecture Guide

This document provides complete instructions for provisioning, configuring, and maintaining the MySQL database for the **ChargeFindr AI** intelligent EV charging station platform.

---

## 1. Database Architecture Overview

The application utilizes MySQL (InnoDB storage engine, `utf8mb4` encoding) with strict relational schemas, foreign key constraints, and row-level locking for concurrency control.

```text
                        ┌──────────────────┐
                        │      users       │
                        └────────┬─────────┘
                                 │ 1:N
           ┌─────────────────────┼─────────────────────┐
           │ 1:N                 │ 1:N                 │
           ▼                     ▼                     ▼
┌──────────────────┐   ┌──────────────────┐   ┌──────────────────┐
│ charging_stations│   │ station_bookings │   │   walkin_queue   │
└────────┬─────────┘   └────────┬─────────┘   └──────────────────┘
         │ 1:N                  │
         ▼                      │
┌──────────────────┐            │
│ station_chargers ◄────────────┘
└──────────────────┘ (Bay Assignment)
```

---

## 2. Table Schemas & Specifications

### A. `charging_stations`
Stores the geographic, power, and real-time status attributes of each monitored EV charging hub.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `station_id` | `INT` | `AUTO_INCREMENT PRIMARY KEY` | Unique station identifier |
| `station_name` | `VARCHAR(100)` | `NOT NULL` | Hub name (e.g. GreenCharge Hub) |
| `location` | `VARCHAR(150)` | `NOT NULL` | Locality area in Hyderabad |
| `distance_km` | `DECIMAL(6,2)` | `NOT NULL` | Baseline benchmark distance |
| `charger_type` | `VARCHAR(50)` | `NOT NULL` | Fast DC / AC Type 2 / DC CCS |
| `capacity_kw` | `DECIMAL(6,2)` | `NOT NULL` | Maximum power output in kilowatts |
| `available_ports` | `INT` | `DEFAULT 0` | Available bays |
| `total_ports` | `INT` | `NOT NULL` | Total installed physical bays |
| `estimated_wait_minutes` | `INT` | `DEFAULT 0` | Current queue wait time |
| `demand_level` | `VARCHAR(20)` | `DEFAULT 'Medium'` | Demand category (Low, Medium, High) |
| `latitude` | `DECIMAL(9,6)` | `NULLABLE` | Verified GPS latitude coordinate |
| `longitude` | `DECIMAL(9,6)` | `NULLABLE` | Verified GPS longitude coordinate |

---

### B. `users`
Stores authenticated user and administrator accounts with cryptographic password hashes.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `user_id` | `INT` | `AUTO_INCREMENT PRIMARY KEY` | Unique user identity |
| `full_name` | `VARCHAR(100)` | `NOT NULL` | Driver's display name |
| `email` | `VARCHAR(150)` | `NOT NULL UNIQUE` | Unique login email address |
| `password_hash` | `VARCHAR(255)` | `NOT NULL` | `scrypt` hash with unique salt |
| `role` | `VARCHAR(20)` | `DEFAULT 'user'` | Role: `'user'` or `'admin'` |
| `created_at` | `TIMESTAMP` | `DEFAULT CURRENT_TIMESTAMP` | Account creation timestamp |
| `updated_at` | `TIMESTAMP` | `DEFAULT CURRENT_TIMESTAMP ON UPDATE` | Last modification |

---

### C. `station_chargers`
Models each physical port/bay per station, enforcing capacity partition between advance bookings and rapid walk-ins.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `charger_id` | `INT` | `AUTO_INCREMENT PRIMARY KEY` | Unique physical bay identifier |
| `station_id` | `INT` | `NOT NULL, FK -> charging_stations` | Station reference |
| `port_number` | `INT` | `NOT NULL` | Physical bay index (1, 2, 3...) |
| `charger_type` | `VARCHAR(50)` | `NOT NULL` | Port connector type |
| `capacity_kw` | `DECIMAL(6,2)` | `NOT NULL` | Individual bay power capacity |
| `allocation_type` | `ENUM('RESERVED','WALKIN')` | `DEFAULT 'RESERVED'` | Dedicated allocation partition |
| `status` | `ENUM('AVAILABLE','OCCUPIED','MAINTENANCE')` | `DEFAULT 'AVAILABLE'` | Hardware state |
| `created_at` | `TIMESTAMP` | `DEFAULT CURRENT_TIMESTAMP` | Port record creation |

*Unique Key*: `(station_id, port_number)` ensures no duplicate port indices per station.

---

### D. `station_bookings`
Persists advance reserved slot bookings with concurrency control.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `booking_id` | `INT` | `AUTO_INCREMENT PRIMARY KEY` | Internal ID |
| `booking_reference` | `VARCHAR(32)` | `NOT NULL UNIQUE` | Human reference (e.g. `BK-20261031-4F2A`) |
| `user_id` | `INT` | `NOT NULL, FK -> users` | Booking account owner |
| `station_id` | `INT` | `NOT NULL, FK -> charging_stations` | Target station |
| `charger_id` | `INT` | `NOT NULL, FK -> station_chargers` | Allocated physical bay |
| `port_number` | `INT` | `NOT NULL` | Bay number |
| `charger_type` | `VARCHAR(50)` | `NOT NULL` | Port type |
| `driver_name` | `VARCHAR(100)` | `NOT NULL` | Driver full name |
| `vehicle_model` | `VARCHAR(100)` | `NOT NULL` | Vehicle model (e.g. Tata Nexon EV) |
| `vehicle_reg_number` | `VARCHAR(30)` | `NOT NULL` | Vehicle registration plate |
| `booking_date` | `DATE` | `NOT NULL` | Reservation date |
| `start_time` | `TIME` | `NOT NULL` | Slot start time (08:00 - 22:00) |
| `end_time` | `TIME` | `NOT NULL` | Slot end time |
| `duration_minutes` | `INT` | `NOT NULL` | Duration: 30, 60, 90, 120 mins |
| `status` | `ENUM` | `DEFAULT 'CONFIRMED'` | `CONFIRMED`, `COMPLETED`, `CANCELLED`, `MISSED` |
| `grace_period_minutes` | `INT` | `DEFAULT 15` | Leniency window before marked missed |
| `cancellation_reason` | `VARCHAR(255)` | `NULLABLE` | Optional cancellation reason |

---

### E. `walkin_queue`
Manages real-time FIFO virtual queues for rapid walk-in charging.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `queue_id` | `INT` | `AUTO_INCREMENT PRIMARY KEY` | Internal queue record ID |
| `queue_ticket` | `VARCHAR(32)` | `NOT NULL UNIQUE` | Ticket code (e.g. `WQ-S1-A9B2`) |
| `user_id` | `INT` | `NOT NULL, FK -> users` | Driver account |
| `station_id` | `INT` | `NOT NULL, FK -> charging_stations` | Station queued for |
| `charger_type` | `VARCHAR(50)` | `NOT NULL` | Charger type requested |
| `driver_name` | `VARCHAR(100)` | `NOT NULL` | Driver name |
| `vehicle_model` | `VARCHAR(100)` | `NOT NULL` | Vehicle model |
| `vehicle_reg_number` | `VARCHAR(30)` | `NOT NULL` | Registration number |
| `status` | `ENUM` | `DEFAULT 'WAITING'` | `WAITING`, `READY`, `CHARGING`, `COMPLETED`, `CANCELLED` |
| `priority_score` | `INT` | `DEFAULT 0` | Priority weighting for FIFO order |
| `estimated_wait_minutes`| `INT` | `DEFAULT 0` | Dynamic wait calculation |
| `joined_at` | `TIMESTAMP` | `DEFAULT CURRENT_TIMESTAMP` | Queue entry timestamp |
| `called_at` | `TIMESTAMP` | `NULLABLE` | Port ready timestamp |
| `completed_at` | `TIMESTAMP` | `NULLABLE` | Session completed timestamp |

---

## 3. Step-by-Step Database Setup

### Step 1: Create Database
Connect to your local MySQL CLI or GUI client (e.g. MySQL Workbench, DBeaver) and run:
```sql
CREATE DATABASE IF NOT EXISTS chargefindr_ai 
CHARACTER SET utf8mb4 
COLLATE utf8mb4_unicode_ci;
```

### Step 2: Import Initial Station Snapshot
Use the verified freeze snapshot provided in the repository to populate the 5 demonstration stations:
```powershell
# From the ChargeFindrAI directory:
mysql -u root -p chargefindr_ai < backend/database/backup_charging_stations_freeze_20261025.sql
```

### Step 3: Automated Table Provisioning
The backend automatically creates the `users`, `station_chargers`, `station_bookings`, and `walkin_queue` tables on startup if they do not already exist, and automatically configures physical port records for all stations:
```powershell
# Verify connectivity and run schema provisioning:
python backend/database/db_config.py
```
Expected output:
```text
==================================================
 ChargeFindr AI - Database Connection Test
==================================================
[SUCCESS] Connected to MySQL database 'chargefindr_ai'.
[SUCCESS] 'charging_stations' table found with 5 records.
[SUCCESS] 'users' table found.
[SUCCESS] 'station_chargers' table initialized with 19 ports.
==================================================
```

### Step 4: Seed Default Administrator Account
To create or reset the standard system administrator account:
```powershell
python backend/scripts/seed_admin.py
```
Default Administrator Credentials:
- **Email**: `admin@chargefindr.local`
- **Password**: `AdminPass123!`
- **Role**: `admin`

---

## 4. Concurrency & Race-Condition Safeguards

1. **Row-Level Locking (`FOR UPDATE`)**:
   During slot reservation creation, the backend executes `SELECT ... FOR UPDATE` on `station_chargers` inside an active transaction. This prevents concurrent transactions from double-booking the same physical charging port.
2. **Duplicate Prevention**:
   - `station_bookings`: Enforces that a single driver cannot reserve conflicting overlapping slots across any station (`HTTP 409 Conflict`).
   - `walkin_queue`: Enforces that a single user cannot hold multiple active tickets (`WAITING` or `READY` or `CHARGING`) simultaneously (`HTTP 409 Conflict`).
3. **Capacity Isolation**:
   Physical bays partitioned as `WALKIN` are dedicated strictly to the rapid walk-in queue and can never be claimed by advance slot reservations.
