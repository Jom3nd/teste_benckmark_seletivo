from dataclasses import dataclass
@dataclass
class Auth:
    id: int
    name: str
    email: str = ""
