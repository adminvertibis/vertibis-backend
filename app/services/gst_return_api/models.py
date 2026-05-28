from dataclasses import dataclass, field
from typing import Any


@dataclass
class GSTAPIResult:
    success: bool
    data: Any = field(default_factory=dict)
    error: str = ""
    raw: Any = field(default_factory=dict)
    endpoint: str = ""
    action: str = ""
    status_code: int | None = None
    method: str = "GET"


@dataclass
class GSTReturnCall:
    return_type: str
    action: str
    period: str
    method: str = "GET"
    endpoint: str = ""
