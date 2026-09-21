from src.notification.controller import NotificationController
def test_controller_flow():
 c=NotificationController(); c.create({"id":1,"name":"A"}); assert c.get(1).name=="A"; assert len(c.list())==1
