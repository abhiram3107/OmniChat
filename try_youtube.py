from fastapi.testclient import TestClient
import app

client = TestClient(app.app)
print('Health:', client.get('/health').json())

payload = {"session_id":"yt-test","message":"What is YouTube? Summarize from the site.","k":4}
resp = client.post('/chat', json=payload)
print('Status:', resp.status_code)
print(resp.text)
