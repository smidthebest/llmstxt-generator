from datetime import datetime

from pydantic import BaseModel


class ScheduleCreate(BaseModel):
    cron_expression: str
    is_active: bool = True


class ScheduleResponse(BaseModel):
    id: int
    site_id: int
    cron_expression: str
    is_active: bool
    last_run_at: datetime | None
    next_run_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}
