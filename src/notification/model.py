from dataclasses import dataclass
@dataclass
class Notification:
    id: int
    name: str
    email: str = ""
