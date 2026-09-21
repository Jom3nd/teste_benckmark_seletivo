from src.notification.controller import NotificationController
from src.auth.service import AuthService
def test_cross_module_integration():
 assert NotificationController().create({"id":1,"name":"A"}).id==1
 assert AuthService().create(2,"B").id==2
