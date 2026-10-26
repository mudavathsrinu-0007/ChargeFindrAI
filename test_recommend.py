from backend.app import app

client = app.test_client()
response = client.post('/api/recommend', json={'location': 'Kondapur', 'charger_type': 'AC Type 2'})

print("HTTP STATUS:", response.status_code)
data = response.get_json()['data']
print("Total stations evaluated:", data['total_evaluated'])
print("\nRanked Recommendations:")
print("-" * 60)
for r in data['recommendations']:
    print(f"Rank #{r['rank']}: {r['station_name']} | Score: {r['recommendation_score']}")
    print(f"  Location: {r['location']} | Charger: {r['charger_type']}")
    print(f"  Ports: {r['available_ports']}/{r['total_ports']} | Wait: {r['estimated_wait_minutes']} mins")
    print(f"  Reasons: {', '.join(r['reasons'])}")
    print("-" * 60)

