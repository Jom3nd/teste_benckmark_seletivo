from src.product.service import ProductService
def test_create(): assert ProductService().create(1,"A").name=="A"
def test_get():
 s=ProductService(); s.create(1,"A"); assert s.get(1).id==1
