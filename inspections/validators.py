from pydantic import BaseModel
from typing import List, Optional, Literal
from django.core.validators import RegexValidator

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

reference_validator = RegexValidator(
    regex=r'^RF-\d{4}-\d{4}$',
    message="La référence doit respecter le format 'RF-YYYY-0000' (ex: RF-2026-0412).",
    code='invalid_reference_structure'
)