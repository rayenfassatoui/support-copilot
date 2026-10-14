from pydantic import AnyHttpUrl

from app.schemas import KnowledgeCreate, RequestModel, Title, Version


class KnowledgeUpdate(KnowledgeCreate):
    version: Version


class URLImport(RequestModel):
    title: Title
    url: AnyHttpUrl
