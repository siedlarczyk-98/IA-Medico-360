from datetime import datetime

from pydantic import BaseModel


class UsageResponse(BaseModel):
    has_limit: bool
    usage_percentage: int | None
    week_reset_at: datetime | None
