from src.user.service import UserService
def test_create(): assert UserService().create(1,"A").name=="A"
def test_get():
 s=UserService(); s.create(1,"A"); assert s.get(1).id==1
