# services/gateway/app/schema.py
from pydantic import BaseModel


class WebhookResponse(BaseModel):
    status:    str
    pr_number: int = 0
    repo:      str = ""
    message:   str = ""


class HealthResponse(BaseModel):
    status:  str = "healthy"
    service: str = "gateway"
