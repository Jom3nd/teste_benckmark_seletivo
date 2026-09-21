from .model import Notification
class NotificationRepository:
    def __init__(self): self.data={}
    def save(self,x:Notification): self.data[x.id]=x; return x
    def get(self,i): return self.data.get(i)
    def delete(self,i): return self.data.pop(i,None)
    def list_all(self): return list(self.data.values())
    def find_by_name(self,n): return next((x for x in self.data.values() if x.name==n),None)
