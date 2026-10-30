import os
import sys
import json

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from backend.database.db_config import get_db_connection

def create_freeze_backup():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("DESCRIBE charging_stations")
    schema = cursor.fetchall()

    cursor.execute("SELECT * FROM charging_stations ORDER BY station_id ASC")
    records = cursor.fetchall()

    db_dir = os.path.dirname(os.path.abspath(__file__))
    json_path = os.path.join(db_dir, "backup_charging_stations_freeze_20261025.json")
    sql_path = os.path.join(db_dir, "backup_charging_stations_freeze_20261025.sql")

    # 1. JSON Backup
    with open(json_path, "w") as f:
        json.dump({"schema": schema, "records": records}, f, default=str, indent=2)

    # 2. SQL Insert Script Backup
    with open(sql_path, "w") as f:
        f.write("-- ChargeFindr AI Freeze Backup Created 2026-10-25\n")
        f.write("-- Table: charging_stations\n\n")
        for r in records:
            lat = "NULL" if r["latitude"] is None else str(r["latitude"])
            lng = "NULL" if r["longitude"] is None else str(r["longitude"])
            f.write(
                f"INSERT INTO charging_stations (station_id, station_name, location, distance_km, "
                f"charger_type, capacity_kw, available_ports, total_ports, estimated_wait_minutes, "
                f"demand_level, latitude, longitude) VALUES ("
                f"{r['station_id']}, '{r['station_name']}', '{r['location']}', {r['distance_km']}, "
                f"'{r['charger_type']}', {r['capacity_kw']}, {r['available_ports']}, {r['total_ports']}, "
                f"{r['estimated_wait_minutes']}, '{r['demand_level']}', {lat}, {lng});\n"
            )

    conn.close()
    print(f"[BACKUP SUCCESS]")
    print(f"  JSON Backup : {json_path}")
    print(f"  SQL Backup  : {sql_path}")
    print(f"  Total Rows  : {len(records)}")

if __name__ == "__main__":
    create_freeze_backup()
