from src.user.controller import UserController
def test_controller_flow():
 c=UserController(); c.create({"id":1,"name":"A"}); assert c.get(1).name=="A"; assert len(c.list())==1
