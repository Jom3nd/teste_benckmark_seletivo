from src.order.controller import OrderController
from src.payment.service import PaymentService
def test_cross_module_integration():
 assert OrderController().create({"id":1,"name":"A"}).id==1
 assert PaymentService().create(2,"B").id==2
