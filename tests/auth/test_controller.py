from src.auth.controller import AuthController
def test_controller_flow():
 c=AuthController(); c.create({"id":1,"name":"A"}); assert c.get(1).name=="A"; assert len(c.list())==1
