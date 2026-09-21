from src.order.controller import OrderController
def test_controller_flow():
 c=OrderController(); c.create({"id":1,"name":"A"}); assert c.get(1).name=="A"; assert len(c.list())==1
