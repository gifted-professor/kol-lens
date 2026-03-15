import requests
import json
with open("test_upload.xlsx", "rb") as f:
    resp = requests.post("http://127.0.0.1:5001/api/upload", files={"file": f})
    print(resp.status_code)
    print(resp.json())
