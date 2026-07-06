from pydantic import BaseModel
from typing import List, Optional, Literal

class FieldSchema(BaseModel):
    id: str
    label: str
    type: Literal['boolean', 'text', 'select', 'number']
    required: bool = True
    options: Optional[List[str]] = None
    order: int

class SectionSchema(BaseModel):
    id: str
    title: str
    order: int
    fields: List[FieldSchema]

class VisitTemplateSchema(BaseModel):
    version: str = "1.0"
    sections: List[SectionSchema]