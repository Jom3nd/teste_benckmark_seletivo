from dataclasses import dataclass
@dataclass
class Order:
    id: int
    name: str
    email: str = ""
