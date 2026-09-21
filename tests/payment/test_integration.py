from src.payment.controller import PaymentController
from src.notification.service import NotificationService
def test_cross_module_integration():
 assert PaymentController().create({"id":1,"name":"A"}).id==1
 assert NotificationService().create(2,"B").id==2
