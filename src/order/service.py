from .model import Order
from .repository import OrderRepository
from .validator import OrderValidator
from src.core.audit_service import AuditService
class OrderService:
    def __init__(self,repo=None): self.repo=repo or OrderRepository(); self.validator=OrderValidator(); self.audit=AuditService()
    def create(self,i,name,email=""): x=self.validator.validate(Order(i,name,email)); self.repo.save(x); self.audit.record("create",i); return x
    def get(self,i): return self.repo.get(i)
    def update(self,i,name):
        x=self.repo.get(i)
        if not x: raise KeyError(i)
        x.name=name; self.validator.validate(x); self.audit.record("update",i); return self.repo.save(x)
    def delete(self,i): self.audit.record("delete",i); return self.repo.delete(i)
    def list_all(self): return sorted(self.repo.list_all(),key=lambda x:x.id)
    def find_by_name(self,n): return self.repo.find_by_name(n)
