import requests
import json

url = "http://localhost:7842/uploads"
try:
    resp = requests.get(url)
    print(json.dumps(resp.json(), indent=2))
except Exception as e:
    print(e)
