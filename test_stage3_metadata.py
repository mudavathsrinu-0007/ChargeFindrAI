import json
import os
from backend.app import app

client = app.test_client()

print("=" * 65)
print(" CHARGEFINDR AI - STAGE 3 DYNAMIC ML METADATA VERIFICATION")
print("=" * 65)

# Load ground-truth metrics from artifact
artifact_path = os.path.join("ml", "model_metrics.json")
with open(artifact_path, "r") as f:
    ground_truth = json.load(f)

# 1. Test GET /api/demand/metadata
res_meta = client.get('/api/demand/metadata')
print("\n[TEST 1] GET /api/demand/metadata Endpoint:")
print("  Status code:", res_meta.status_code)
meta_json = res_meta.get_json()
print("  JSON Output:", json.dumps(meta_json, indent=2))
assert res_meta.status_code == 200
assert meta_json['success'] is True
data = meta_json['data']

# Verify against ground truth artifact
assert data['train_samples'] == ground_truth['train_samples']
assert data['test_samples'] == ground_truth['test_samples']
assert data['metrics']['MAE'] == ground_truth['metrics']['MAE']
assert data['metrics']['RMSE'] == ground_truth['metrics']['RMSE']
assert data['metrics']['R2_Score'] == ground_truth['metrics']['R2_Score']
assert data['is_available'] is True
print("  [PASSED] API values match ml/model_metrics.json exactly!")
print(f"    Train Samples : {data['train_samples']:,}")
print(f"    Test Samples  : {data['test_samples']:,}")
print(f"    Split Type    : {data['split_type']}")
print(f"    MAE / RMSE    : {data['metrics']['MAE']:.2f} kWh / {data['metrics']['RMSE']:.2f} kWh")

# 2. Test GET /api/demand includes metadata in prediction response
print("\n[TEST 2] GET /api/demand Prediction Payload Integration:")
res_dem = client.get('/api/demand?hour=12&day_of_week=3')
assert res_dem.status_code == 200
dem_json = res_dem.get_json()['data']
assert 'metadata' in dem_json
assert dem_json['metadata']['train_samples'] == 58284
assert dem_json['metadata']['test_samples'] == 14572
assert dem_json['metadata']['split_type'] == "80/20 Chronological Split (No Data Leakage)"
print("  [PASSED] /api/demand includes complete verified metadata alongside hourly prediction.")

# 3. Verify Frontend index.html does NOT contain hardcoded static values
print("\n[TEST 3] Frontend HTML Inspection (Ensuring Zero Hardcoded Metadata):")
res_html = client.get('/')
html_str = res_html.data.decode('utf-8')

# Assert static numbers are NOT hardcoded in HTML
assert '<strong id="metric-mae">10.29 kWh</strong>' not in html_str
assert '<strong id="metric-rmse">13.44 kWh</strong>' not in html_str
assert '<strong>80/20 Chronological</strong>' not in html_str
assert '<strong>58,284</strong>' not in html_str

# Assert dynamic IDs exist in HTML
assert 'id="metric-mae"' in html_str
assert 'id="metric-rmse"' in html_str
assert 'id="metric-split"' in html_str
assert 'id="metric-train-records"' in html_str
assert 'id="model-dataset-badge"' in html_str
print("  [PASSED] Verified: Static metadata labels replaced with dynamic placeholder IDs.")

# 4. Regression Test: Stations & Locations
print("\n[TEST 4] Regression Check - Stations & Dynamic Locations:")
res_s = client.get('/api/stations')
assert res_s.status_code == 200
assert len(res_s.get_json()['data']) == 5

res_l = client.get('/api/stations/locations')
assert res_l.status_code == 200
assert len(res_l.get_json()['data']) == 5
print("  [PASSED] /api/stations and /api/stations/locations operating normally.")

# 5. Regression Test: Recommendations
print("\n[TEST 5] Regression Check - AI Recommendation Engine:")
res_r = client.post('/api/recommend', json={'location': 'Madhapur, Hyderabad', 'charger_type': 'Fast DC'})
assert res_r.status_code == 200
recs = res_r.get_json()['data']['recommendations']
assert len(recs) == 5
assert recs[0]['station_name'] == 'GreenCharge Hub'
print(f"  [PASSED] Recommendation engine responded: Top Pick is {recs[0]['station_name']} (Score: {recs[0]['recommendation_score']}).")

print("\n" + "=" * 65)
print(" ALL TESTS PASSED: DYNAMIC ML METADATA INTEGRATION VERIFIED!")
print("=" * 65)

