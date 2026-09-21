from src.auth.controller import AuthController
from src.user.service import UserService
def test_cross_module_integration():
 assert AuthController().create({"id":1,"name":"A"}).id==1
 assert UserService().create(2,"B").id==2
