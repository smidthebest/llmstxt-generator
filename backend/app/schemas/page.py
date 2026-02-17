from pydantic import BaseModel


class PageResponse(BaseModel):
    id: int
    url: str
    title: str | None
    description: str | None
    category: str
    relevance_score: float
    depth: int

    model_config = {"from_attributes": True}
