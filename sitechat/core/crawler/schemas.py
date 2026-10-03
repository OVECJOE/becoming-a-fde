from pydantic import AnyHttpUrl, BaseModel


class Page(BaseModel):
    id: int
    url: AnyHttpUrl
    depth: int
