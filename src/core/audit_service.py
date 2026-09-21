class AuditService:
    def record(self, action, entity_id): return f'{action}:{entity_id}'
