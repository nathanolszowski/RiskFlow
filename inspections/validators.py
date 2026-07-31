from pydantic import BaseModel
from typing import List, Optional, Literal

# FieldSchema, SectionSchema, and VisitTemplateSchema are Pydantic models that define the structure of a visit template.
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

# get_default_template_structure returns the default JSON skeleton for a new visit template.
def get_default_template_structure():
    """
    Retourne le squelette JSON par défaut pour un nouveau gabarit de visite.
    """
    return {
        "version": "1.0",
        "sections": [
            {
                "id": "sec_exemple",
                "title": "Nom de la Section (Ex: Sécurité)",
                "order": 1,
                "fields": [
                    {
                        "id": "f_champ_exemple",
                        "label": "Libellé de la question ?",
                        "type": "boolean",
                        "required": True,
                        "order": 1
                    }
                ]
            }
        ]
    }
