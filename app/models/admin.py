from typing import Any
from pydantic import BaseModel


class ExplainResult(BaseModel):
    endpoint: str
    collection: str
    explain: dict[str, Any]
