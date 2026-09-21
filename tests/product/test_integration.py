from src.product.controller import ProductController
from src.order.service import OrderService
def test_cross_module_integration():
 assert ProductController().create({"id":1,"name":"A"}).id==1
 assert OrderService().create(2,"B").id==2
