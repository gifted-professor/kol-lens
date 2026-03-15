import json
import time
import requests
import os

def get_token():
    auth_file = os.path.expanduser("~/.apify/auth.json")
    try:
        with open(auth_file, 'r') as f:
            return json.load(f).get('token')
    except:
        return 'YOUR_APIFY_API_TOKEN_HERE' # Fallback

def test_apify_rest_api():
    token = get_token()
    actor_id = "clockworks~tiktok-profile-scraper"
    
    # 1. Start the run
    run_url = f"https://api.apify.com/v2/acts/{actor_id}/runs?token={token}"
    input_data = {
        "profiles": ["apple"],
        "resultsPerPage": 1
    }
    
    print(f"--> [1] Triggering Actor Run via REST API ({actor_id})...")
    resp = requests.post(run_url, json=input_data)
    
    if resp.status_code not in (200, 201):
        print(f"❌ Failed to start run. Status: {resp.status_code}, Body: {resp.text}")
        return
        
    run_info = resp.json()['data']
    run_id = run_info['id']
    dataset_id = run_info['defaultDatasetId']
    print(f"✅ Run successfully started! Run ID: {run_id}, Dataset ID: {dataset_id}")
    
    # 2. Poll for completion
    status_url = f"https://api.apify.com/v2/actor-runs/{run_id}?token={token}"
    print("\n--> [2] Polling Run Status...")
    
    while True:
        s_resp = requests.get(status_url)
        if s_resp.status_code != 200:
            print(f"Failed to get status: {s_resp.text}")
            break
            
        status_data = s_resp.json()['data']
        status = status_data['status']
        print(f"    Current Status: {status}")
        
        if status == 'SUCCEEDED':
            print("✅ Run Completed Successfully!")
            break
        elif status in ('FAILED', 'ABORTED', 'TIMED-OUT'):
            print(f"❌ Run ended with error state: {status}")
            return
            
        time.sleep(3)
        
    # 3. Retrieve default dataset
    print(f"\n--> [3] Downloading Dataset ({dataset_id})...")
    dataset_url = f"https://api.apify.com/v2/datasets/{dataset_id}/items?token={token}"
    d_resp = requests.get(dataset_url)
    
    if d_resp.status_code == 200:
        items = d_resp.json()
        print(f"✅ Successfully downloaded {len(items)} records.")
        if items:
            author = items[0].get('authorMeta', {}).get('name', 'Unknown')
            text = items[0].get('text', '')[:50]
            print(f"Preview -> Author: {author} | Text: {text}...")
    else:
        print(f"❌ Failed to download dataset: {d_resp.text}")

if __name__ == "__main__":
    test_apify_rest_api()
