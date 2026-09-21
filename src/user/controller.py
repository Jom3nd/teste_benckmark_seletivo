from .service import UserService
class UserController:
    def __init__(self): self.service=UserService()
    def create(self,payload): return self.service.create(payload['id'],payload['name'],payload.get('email',''))
    def get(self,i): return self.service.get(i)
    def list(self): return self.service.list_all()
