import os
import mysql.connector
from mysql.connector import Error

def _load_env_file():
    """Load key-value pairs from .env file if present."""
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    env_file = os.path.join(base_dir, ".env")
    if os.path.exists(env_file):
        with open(env_file, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, val = line.split("=", 1)
                    os.environ.setdefault(key.strip(), val.strip())

# Load configuration on module import
_load_env_file()

def get_db_connection():
    """
    Establish and return a connection to the MySQL database.
    Configuration is read from environment variables (.env).
    """
    try:
        connection = mysql.connector.connect(
            host=os.getenv("DB_HOST", "localhost"),
            user=os.getenv("DB_USER", "root"),
            password=os.getenv("DB_PASSWORD", ""),
            database=os.getenv("DB_NAME", "chargefindr_ai"),
            port=int(os.getenv("DB_PORT", "3306"))
        )
        return connection
    except Error as e:
        print(f"[Database Error] Could not connect to MySQL: {e}")
        return None

def ensure_users_table(conn=None):
    """
    Ensure the users table exists in the database.
    Does not modify or delete any existing tables or records.
    """
    should_close = False
    if conn is None:
        conn = get_db_connection()
        should_close = True

    if not conn:
        print("[Database Error] Cannot ensure users table: database connection failed.")
        return False

    try:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INT AUTO_INCREMENT PRIMARY KEY,
                full_name VARCHAR(100) NOT NULL,
                email VARCHAR(150) NOT NULL,
                password_hash VARCHAR(255) NOT NULL,
                role VARCHAR(20) NOT NULL DEFAULT 'user',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                UNIQUE KEY uq_users_email (email),
                INDEX idx_users_role (role)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
        """)
        conn.commit()
        cursor.close()
        return True
    except Error as e:
        print(f"[Database Error] Could not ensure users table: {e}")
        return False
    finally:
        if should_close and conn and conn.is_connected():
            conn.close()

def ensure_booking_and_queue_tables(conn=None):
    """
    Ensure station_chargers, station_bookings, and walkin_queue tables exist.
    Populates physical station_chargers if not already present.
    Does not delete or alter any existing data in charging_stations or users.
    """
    should_close = False
    if conn is None:
        conn = get_db_connection()
        should_close = True

    if not conn:
        print("[Database Error] Cannot ensure booking & queue tables: database connection failed.")
        return False

    try:
        cursor = conn.cursor(dictionary=True)

        # 1. Physical chargers / ports table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS station_chargers (
                charger_id INT AUTO_INCREMENT PRIMARY KEY,
                station_id INT NOT NULL,
                port_number INT NOT NULL,
                charger_type VARCHAR(50) NOT NULL,
                capacity_kw DECIMAL(6,2) NOT NULL,
                allocation_type ENUM('RESERVED', 'WALKIN') NOT NULL DEFAULT 'RESERVED',
                status ENUM('AVAILABLE', 'OCCUPIED', 'MAINTENANCE') NOT NULL DEFAULT 'AVAILABLE',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE KEY uq_station_port (station_id, port_number),
                INDEX idx_chargers_lookup (station_id, allocation_type, status),
                FOREIGN KEY (station_id) REFERENCES charging_stations(station_id) ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
        """)

        # 2. Reserved slot bookings table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS station_bookings (
                booking_id INT AUTO_INCREMENT PRIMARY KEY,
                booking_reference VARCHAR(32) NOT NULL UNIQUE,
                user_id INT NOT NULL,
                station_id INT NOT NULL,
                charger_id INT NOT NULL,
                port_number INT NOT NULL,
                charger_type VARCHAR(50) NOT NULL,
                driver_name VARCHAR(100) NOT NULL,
                vehicle_model VARCHAR(100) NOT NULL,
                vehicle_reg_number VARCHAR(30) NOT NULL,
                booking_date DATE NOT NULL,
                start_time TIME NOT NULL,
                end_time TIME NOT NULL,
                duration_minutes INT NOT NULL,
                status ENUM('CONFIRMED', 'COMPLETED', 'CANCELLED', 'MISSED') NOT NULL DEFAULT 'CONFIRMED',
                grace_period_minutes INT NOT NULL DEFAULT 15,
                cancellation_reason VARCHAR(255) NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
                FOREIGN KEY (station_id) REFERENCES charging_stations(station_id) ON DELETE CASCADE,
                FOREIGN KEY (charger_id) REFERENCES station_chargers(charger_id) ON DELETE CASCADE,
                INDEX idx_user_bookings (user_id, status),
                INDEX idx_station_date_time (station_id, booking_date, status),
                INDEX idx_charger_slot (charger_id, booking_date, status)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
        """)

        # 3. Rapid walk-in queue table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS walkin_queue (
                queue_id INT AUTO_INCREMENT PRIMARY KEY,
                queue_ticket VARCHAR(32) NOT NULL UNIQUE,
                user_id INT NOT NULL,
                station_id INT NOT NULL,
                charger_type VARCHAR(50) NOT NULL,
                driver_name VARCHAR(100) NOT NULL,
                vehicle_model VARCHAR(100) NOT NULL,
                vehicle_reg_number VARCHAR(30) NOT NULL,
                status ENUM('WAITING', 'READY', 'CHARGING', 'COMPLETED', 'CANCELLED') NOT NULL DEFAULT 'WAITING',
                priority_score INT NOT NULL DEFAULT 0,
                estimated_wait_minutes INT NOT NULL DEFAULT 0,
                assigned_charger_id INT NULL,
                joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                called_at TIMESTAMP NULL,
                completed_at TIMESTAMP NULL,
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
                FOREIGN KEY (station_id) REFERENCES charging_stations(station_id) ON DELETE CASCADE,
                INDEX idx_queue_station_status (station_id, status),
                INDEX idx_queue_user (user_id, status)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
        """)

        # Seed station_chargers if any station lacks configured ports
        cursor.execute("SELECT station_id, station_name, charger_type, capacity_kw, total_ports FROM charging_stations")
        stations = cursor.fetchall()

        for st in stations:
            sid = st['station_id']
            tot = st['total_ports'] or 4
            ctype = st['charger_type'] or 'Fast DC'
            ckw = st['capacity_kw'] or 50.0

            cursor.execute("SELECT COUNT(*) AS cnt FROM station_chargers WHERE station_id = %s", (sid,))
            exists = cursor.fetchone()['cnt']
            if exists == 0:
                # Reserved gets ceil(tot / 2), Walkin gets the remaining ports
                reserved_count = (tot + 1) // 2
                for p in range(1, tot + 1):
                    alloc = 'RESERVED' if p <= reserved_count else 'WALKIN'
                    cursor.execute("""
                        INSERT INTO station_chargers (station_id, port_number, charger_type, capacity_kw, allocation_type, status)
                        VALUES (%s, %s, %s, %s, %s, 'AVAILABLE')
                    """, (sid, p, ctype, ckw, alloc))

        conn.commit()
        cursor.close()
        return True
    except Error as e:
        print(f"[Database Error] Could not ensure booking and queue tables: {e}")
        return False
    finally:
        if should_close and conn and conn.is_connected():
            conn.close()

def test_connection():
    """Helper function to test database connectivity and count existing stations and users."""
    conn = get_db_connection()
    if conn and conn.is_connected():
        try:
            ensure_users_table(conn)
            ensure_booking_and_queue_tables(conn)
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT COUNT(*) AS total_count FROM charging_stations;")
            station_res = cursor.fetchone()
            cursor.execute("SELECT COUNT(*) AS total_count FROM users;")
            user_res = cursor.fetchone()
            cursor.execute("SELECT COUNT(*) AS total_count FROM station_chargers;")
            chargers_res = cursor.fetchone()

            print("==================================================")
            print(" ChargeFindr AI - Database Connection Test")
            print("==================================================")
            print("[SUCCESS] Connected to MySQL database 'chargefindr_ai'.")
            print(f"[SUCCESS] 'charging_stations' table found with {station_res['total_count']} records.")
            print(f"[SUCCESS] 'users' table found with {user_res['total_count']} records.")
            print(f"[SUCCESS] 'station_chargers' table initialized with {chargers_res['total_count']} ports.")
            print("==================================================")
            cursor.close()
            conn.close()
            return True
        except Error as err:
            print(f"[ERROR] Query failed: {err}")
            conn.close()
            return False
    else:
        print("[ERROR] Failed to establish database connection.")
        return False

if __name__ == "__main__":
    test_connection()

