from src.order.service import OrderService
def test_create(): assert OrderService().create(1,"A").name=="A"
def test_get():
 s=OrderService(); s.create(1,"A"); assert s.get(1).id==1
