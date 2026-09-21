from src.auth.service import AuthService
def test_create(): assert AuthService().create(1,"A").name=="A"
def test_get():
 s=AuthService(); s.create(1,"A"); assert s.get(1).id==1
