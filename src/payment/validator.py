from .model import Payment
class PaymentValidator:
    def validate(self,x:Payment):
        if x.id < 0 or not x.name.strip(): raise ValueError("invalid payment")
        return x
