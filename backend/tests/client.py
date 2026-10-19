"""Legacy feature tests use an explicit fictional staff login, not an auth bypass."""
from fastapi.testclient import TestClient as RawClient

TEST_PASSWORD='only-for-isolated-tests-123'

def TestClient(*args, role='doctor', **kwargs):
    headers={'X-Practice-Client':'portal',**kwargs.pop('headers',{})}
    client=RawClient(*args,headers=headers,**kwargs)
    username={'doctor':'dr.asha','medical_admin':'admin','nurse':'nurse'}[role]
    response=client.post('/api/staff/login',json={'username':username,'password':TEST_PASSWORD})
    assert response.status_code==200,response.text
    return client
