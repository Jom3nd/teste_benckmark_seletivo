from .model import Product
class ProductValidator:
    def validate(self,x:Product):
        if x.id < 0 or not x.name.strip(): raise ValueError("invalid product")
        return x
