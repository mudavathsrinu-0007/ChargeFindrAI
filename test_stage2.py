from backend.app import app

client = app.test_client()

print("=" * 60)
print(" CHARGEFINDR AI - STAGE 2 COMPREHENSIVE VERIFICATION")
print("=" * 60)

# 1. Health check
res_h = client.get('/api/health')
print("\n[TEST 1] Backend & Database Health Check:")
print("  Status code:", res_h.status_code)
print("  Response   :", res_h.get_json())
assert res_h.status_code == 200
assert res_h.get_json()['database'] == 'connected'

# 2. Stations with coordinates
res_s = client.get('/api/stations')
stations = res_s.get_json()['data']
print(f"\n[TEST 2] Stations API (Count: {len(stations)}):")
assert res_s.status_code == 200
assert len(stations) == 5
for s in stations:
    print(f"  Station #{s['station_id']}: {s['station_name']} ({s['location']})")
    print(f"    Coords: lat={s['latitude']}, lng={s['longitude']}")
    print(f"    Ports : {s['available_ports']}/{s['total_ports']} | Charger: {s['charger_type']} ({s['capacity_kw']} kW)")
    assert s['latitude'] is not None and s['longitude'] is not None
    assert isinstance(s['latitude'], float) and isinstance(s['longitude'], float)

# 3. Recommendation Regression Check
res_r = client.post('/api/recommend', json={'location': 'Kondapur', 'charger_type': 'AC Type 2'})
assert res_r.status_code == 200
recommendations = res_r.get_json()['data']['recommendations']
print(f"\n[TEST 3] Recommendation Engine Regression (Evaluated: {len(recommendations)}):")
top = recommendations[0]
print(f"  Top Pick : {top['station_name']} (Score: {top['recommendation_score']})")
print(f"  Location : {top['location']} | Coords: ({top['latitude']}, {top['longitude']})")
print(f"  Reasons  : {', '.join(top['reasons'])}")
assert top['station_name'] == 'EcoCharge Station'
assert top['latitude'] == 17.4699

# 4. Demand Prediction Regression Check
res_d = client.get('/api/demand?hour=17&day_of_week=4&charger_type=Fast%20DC')
assert res_d.status_code == 200
d_data = res_d.get_json()['data']
print(f"\n[TEST 4] ML Demand Prediction Regression (Hour 17:00, Friday):")
print(f"  Model Used       : {d_data['model_used']}")
print(f"  Predicted Demand : {d_data['predicted_demand_kwh']} kWh ({d_data['demand_level']})")
print(f"  24-Hour Curve    : {len(d_data['hourly_curve'])} points generated")
assert d_data['is_ml_model'] is True
assert len(d_data['hourly_curve']) == 24

# 5. Frontend Files Serving Check
r_index = client.get('/')
r_css = client.get('/style.css')
r_js = client.get('/script.js')
print(f"\n[TEST 5] Frontend File Delivery:")
print(f"  /          : HTTP {r_index.status_code} ({len(r_index.data):,} bytes)")
print(f"  /style.css : HTTP {r_css.status_code} ({len(r_css.data):,} bytes)")
print(f"  /script.js : HTTP {r_js.status_code} ({len(r_js.data):,} bytes)")
assert r_index.status_code == 200
assert r_css.status_code == 200
assert r_js.status_code == 200
assert b'id="map"' in r_index.data
assert b'map-fallback-banner' in r_index.data
assert b'YOUR_GOOGLE_MAPS_API_KEY' in r_js.data

print("\n" + "=" * 60)
print(" ALL 5 REGRESSION & INTEGRATION TESTS PASSED SUCCESSFULLY!")
print("=" * 60)

