import sys
sys.path.insert(0, '.')
from app import app

with app.test_client() as client:
    resp = client.get('/')
    print('STATUS:', resp.status_code)
    print(resp.data.decode('utf-8', errors='replace'))
