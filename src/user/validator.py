from .model import User
class UserValidator:
    def validate(self,x:User):
        if x.id < 0 or not x.name.strip(): raise ValueError("invalid user")
        return x
