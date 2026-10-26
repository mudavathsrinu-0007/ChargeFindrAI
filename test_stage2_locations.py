from backend.app import app
from backend.database.db_config import get_db_connection

client = app.test_client()

print("=" * 65)
print(" CHARGEFINDR AI - STAGE 2 LOCATION DROPDOWN VERIFICATION")
print("=" * 65)

# 1. Test GET /api/stations/locations
res_loc = client.get('/api/stations/locations')
print("\n[TEST 1] GET /api/stations/locations Response:")
print("  Status code:", res_loc.status_code)
loc_json = res_loc.get_json()
print("  JSON Output:", loc_json)
assert res_loc.status_code == 200
assert loc_json['success'] is True
locations = loc_json['data']
assert len(locations) == 5
assert "Gachibowli, Hyderabad" in locations
assert "Madhapur, Hyderabad" in locations
print(f"  Verified {len(locations)} distinct locations from MySQL database.")

# 2. Controlled Dynamic Test: Insert temporary location, verify endpoint detects it, then clean up
print("\n[TEST 2] Controlled Dynamic Location Test (Insert temporary station):")
conn = get_db_connection()
cursor = conn.cursor(dictionary=True)
test_station_sql = (
    "INSERT INTO charging_stations (station_id, station_name, location, distance_km, charger_type, "
    "capacity_kw, available_ports, total_ports, estimated_wait_minutes, demand_level, latitude, longitude) "
    "VALUES (999, 'Test Hub Jubilee', 'Jubilee Hills, Hyderabad', 4.5, 'Fast DC', 50.0, 2, 2, 5, 'Low', 17.4319, 78.4073);"
)
cursor.execute(test_station_sql)
conn.commit()
print("  Temporary station #999 ('Jubilee Hills, Hyderabad') inserted.")

# Query the endpoint again
res_loc_dynamic = client.get('/api/stations/locations')
dynamic_locations = res_loc_dynamic.get_json()['data']
print("  Locations returned after insertion:", dynamic_locations)
assert "Jubilee Hills, Hyderabad" in dynamic_locations
assert len(dynamic_locations) == 6
print("  [PASSED] Dynamic endpoint immediately reflects new location in MySQL!")

# Clean up temporary test record
cursor.execute("DELETE FROM charging_stations WHERE station_id = 999;")
conn.commit()
conn.close()
print("  Temporary station #999 deleted. Clean up verified.")

# Re-verify count after clean up
res_loc_after = client.get('/api/stations/locations')
assert len(res_loc_after.get_json()['data']) == 5
print("  Confirmed database returned to exact original 5 records.")

# 3. Test "All Hyderabad Areas" recommendation behavior
print("\n[TEST 3] Recommendation with 'All Hyderabad Areas' (location='Any'):")
res_rec_any = client.post('/api/recommend', json={'location': 'Any', 'charger_type': 'Any', 'priority': 'balanced'})
assert res_rec_any.status_code == 200
recs_any = res_rec_any.get_json()['data']['recommendations']
print(f"  Evaluated: {len(recs_any)} stations")
print(f"  Top Pick : {recs_any[0]['station_name']} (Score: {recs_any[0]['recommendation_score']})")
assert len(recs_any) == 5

# 4. Test recommendation with specific dynamic location
print("\n[TEST 4] Recommendation with specific locality ('Kondapur, Hyderabad'):")
res_rec_loc = client.post('/api/recommend', json={'location': 'Kondapur, Hyderabad', 'charger_type': 'AC Type 2'})
assert res_rec_loc.status_code == 200
recs_loc = res_rec_loc.get_json()['data']['recommendations']
top_loc = recs_loc[0]
print(f"  Top Pick : {top_loc['station_name']} (Score: {top_loc['recommendation_score']})")
print(f"  Reasons  : {', '.join(top_loc['reasons'])}")
assert top_loc['station_name'] == 'EcoCharge Station'
assert "Kondapur" in top_loc['location']

# 5. Demand prediction regression check
print("\n[TEST 5] Demand Prediction API Regression Check:")
res_dem = client.get('/api/demand?hour=14&day_of_week=1&charger_type=Fast%20DC')
assert res_dem.status_code == 200
dem_data = res_dem.get_json()['data']
print(f"  Predicted Demand: {dem_data['predicted_demand_kwh']} kWh ({dem_data['demand_level']}) via {dem_data['model_used']}")
assert dem_data['is_ml_model'] is True
assert len(dem_data['hourly_curve']) == 24

# 6. Frontend HTML check (ensuring no hardcoded options)
print("\n[TEST 6] Frontend HTML Dropdown Verification:")
res_html = client.get('/')
html_content = res_html.data.decode('utf-8')
assert '<option value="Any">All Hyderabad Areas</option>' in html_content
assert '<option value="Madhapur">Madhapur</option>' not in html_content
assert '<option value="Hitech City">Hitech City</option>' not in html_content
print("  Verified: Hardcoded static options are removed from HTML; dynamic population enabled.")

print("\n" + "=" * 65)
print(" ALL TESTS PASSED: DATABASE-DRIVEN LOCATION DROPDOWN VERIFIED!")
print("=" * 65)

