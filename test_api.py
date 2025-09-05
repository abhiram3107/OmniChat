from fastapi.testclient import TestClient
import app

client = TestClient(app.app)

resp = client.get('/health')
print('HEALTH', resp.status_code, resp.text)

payload = {"session_id":"test","message":"Hello there","k":4, "domain":"example.com"}
resp = client.post('/chat', json=payload)
print('CHAT', resp.status_code)
print(resp.text)
