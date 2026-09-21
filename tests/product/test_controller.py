from src.product.controller import ProductController
def test_controller_flow():
 c=ProductController(); c.create({"id":1,"name":"A"}); assert c.get(1).name=="A"; assert len(c.list())==1
