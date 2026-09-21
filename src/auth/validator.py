from .model import Auth
class AuthValidator:
    def validate(self,x:Auth):
        if x.id < 0 or not x.name.strip(): raise ValueError("invalid auth")
        return x
