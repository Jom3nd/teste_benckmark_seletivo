from .model import Order
class OrderValidator:
    def validate(self,x:Order):
        if x.id < 0 or not x.name.strip(): raise ValueError("invalid order")
        return x
