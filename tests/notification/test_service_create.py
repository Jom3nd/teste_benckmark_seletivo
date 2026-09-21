from src.notification.service import NotificationService
def test_create(): assert NotificationService().create(1,"A").name=="A"
def test_get():
 s=NotificationService(); s.create(1,"A"); assert s.get(1).id==1
