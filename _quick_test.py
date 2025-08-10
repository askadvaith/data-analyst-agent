from app.main import app
from starlette.testclient import TestClient

c=TestClient(app)
files=[('x',('myqs.txt', b'Output [1,2,3] as JSON array','text/plain'))]
r=c.post('/api/', files=files)
print(r.status_code)
print(r.text)
