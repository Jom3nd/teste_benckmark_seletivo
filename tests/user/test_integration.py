from src.user.controller import UserController
from src.product.service import ProductService
def test_cross_module_integration():
 assert UserController().create({"id":1,"name":"A"}).id==1
 assert ProductService().create(2,"B").id==2
