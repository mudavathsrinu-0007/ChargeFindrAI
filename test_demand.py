from backend.app import app

client = app.test_client()

# Test demand prediction for 18:00 (6 PM peak hour)
response = client.get('/api/demand?hour=18&day_of_week=2&charger_type=Fast%20DC')

print("HTTP STATUS:", response.status_code)
res_json = response.get_json()
data = res_json['data']

print("--------------------------------------------------")
print(f" Demand Prediction for Hour {data['hour']}:00 (Wednesday)")
print("--------------------------------------------------")
print(f" Model Used          : {data['model_used']}")
print(f" Dataset             : {data['dataset']}")
print(f" Predicted Demand    : {data['predicted_demand_kwh']} kWh")
print(f" Demand Level        : {data['demand_level']}")
print(f" Advisory Notice     : {data['advisory']}")
if data.get('metrics'):
    print(f" Model MAE           : {data['metrics']['MAE']} kWh")
    print(f" Model RMSE          : {data['metrics']['RMSE']} kWh")
    print(f" Model R2 Score      : {data['metrics']['R2_Score']}")
print("--------------------------------------------------")
print(f" 24-Hour Forecast Curve Sample (first 5 hours):")
for point in data['hourly_curve'][:5]:
    print(f"   {point['label']} -> {point['predicted_demand_kwh']} kWh ({point['demand_level']})")
print("--------------------------------------------------")

