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

def test_connection():
    """Helper function to test database connectivity and count existing stations and users."""
    conn = get_db_connection()
    if conn and conn.is_connected():
        try:
            ensure_users_table(conn)
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT COUNT(*) AS total_count FROM charging_stations;")
            station_res = cursor.fetchone()
            cursor.execute("SELECT COUNT(*) AS total_count FROM users;")
            user_res = cursor.fetchone()

            print("==================================================")
            print(" ChargeFindr AI - Database Connection Test")
            print("==================================================")
            print("[SUCCESS] Connected to MySQL database 'chargefindr_ai'.")
            print(f"[SUCCESS] 'charging_stations' table found with {station_res['total_count']} records.")
            print(f"[SUCCESS] 'users' table found with {user_res['total_count']} records.")
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

