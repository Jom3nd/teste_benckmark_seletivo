from src.payment.service import PaymentService
def test_create(): assert PaymentService().create(1,"A").name=="A"
def test_get():
 s=PaymentService(); s.create(1,"A"); assert s.get(1).id==1
