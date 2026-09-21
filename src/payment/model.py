from dataclasses import dataclass
@dataclass
class Payment:
    id: int
    name: str
    email: str = ""
