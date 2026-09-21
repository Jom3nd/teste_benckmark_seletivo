from src.payment.controller import PaymentController
def test_controller_flow():
 c=PaymentController(); c.create({"id":1,"name":"A"}); assert c.get(1).name=="A"; assert len(c.list())==1
