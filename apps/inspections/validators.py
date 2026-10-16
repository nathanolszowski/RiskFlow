from typing import Any, Dict, List, Literal, Optional

from django.core.exceptions import ValidationError
from pydantic import (
    BaseModel,
    field_validator,
    model_validator,
)
from pydantic import (
    ValidationError as PydanticValidationError,
)

TEXT_MAX_LENGTH = 5000


# FieldSchema, SectionSchema, and VisitTemplateSchema are Pydantic models that define the structure of a visit template.
class FieldSchema(BaseModel):
    id: str
    label: str
    type: Literal["boolean", "text", "select", "number"]
    required: bool = True
    options: Optional[List[str]] = None
    order: int
    # Optional settings of the number fields
    unit: Optional[str] = None
    step: Optional[float] = None
    min: Optional[float] = None
    max: Optional[float] = None

    @model_validator(mode="after")
    def check_options(self):
        if self.type == "select":
            if not self.options:
                raise ValueError(
                    f"Le champ « {self.label} » est un choix : il faut au moins une option."
                )
            if len(set(self.options)) != len(self.options):
                raise ValueError(
                    f"Le champ « {self.label} » contient des options en double."
                )
        return self

    @model_validator(mode="after")
    def check_bounds(self):
        if self.min is not None and self.max is not None and self.min > self.max:
            raise ValueError(
                f"Le champ « {self.label} » a un minimum supérieur au maximum."
            )
        return self


class SectionSchema(BaseModel):
    id: str
    title: str
    order: int
    fields: List[FieldSchema]


class VisitTemplateSchema(BaseModel):
    version: str = "1.0"
    sections: List[SectionSchema]

    @field_validator("sections")
    @classmethod
    def check_not_empty(cls, sections):
        if not sections:
            raise ValueError("Le template doit contenir au moins une section.")
        return sections

    @model_validator(mode="after")
    def check_unique_ids(self):
        section_ids = [section.id for section in self.sections]
        if len(set(section_ids)) != len(section_ids):
            raise ValueError("Les identifiants de section doivent être uniques.")
        field_ids = [field.id for section in self.sections for field in section.fields]
        if len(set(field_ids)) != len(field_ids):
            raise ValueError(
                "Les identifiants de champ doivent être uniques dans tout le template."
            )
        return self


class AnswersValidationError(ValidationError):
    """Validation error of the visit answers, carrying one message per field id."""

    def __init__(self, errors: Dict[str, str]):
        self.field_errors = errors
        super().__init__(errors)


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
                        "order": 1,
                    }
                ],
            }
        ],
    }


def _format_pydantic_error(error: PydanticValidationError):
    messages = []
    for item in error.errors():
        location = " > ".join(str(part) for part in item["loc"])
        message = item["msg"].removeprefix("Value error, ")
        messages.append(f"{location} : {message}" if location else message)
    return " ; ".join(messages)


def validate_template_schema(schema) -> dict:
    """
    Validate the structure of a visit template (or of a visit snapshot) and return it unchanged.
    Raise a Django ValidationError so that it can be used by models, forms and services.
    """
    if not isinstance(schema, dict):
        raise ValidationError(
            "Le format JSON de la structure est invalide : un objet est attendu."
        )
    try:
        VisitTemplateSchema(**schema)
    except PydanticValidationError as e:
        raise ValidationError(
            f"Le format JSON de la structure est invalide : {_format_pydantic_error(e)}"
        )
    return schema


def iter_schema_fields(schema):
    """Yield (section, field) pairs of a schema, in display order."""
    for section in sorted(schema.get("sections", []), key=lambda s: s.get("order", 0)):
        for field in sorted(section.get("fields", []), key=lambda f: f.get("order", 0)):
            yield section, field


def _has_value(value) -> bool:
    return value is not None and value != ""


def _clean_answer(field: dict, value):
    """Return the cleaned value of one answer, or raise ValueError with a message for the user."""
    field_type = field.get("type")
    if field_type == "boolean":
        if not isinstance(value, bool):
            raise ValueError("Réponse attendue : oui ou non.")
        return value
    if field_type == "number":
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("Un nombre est attendu.")
        if field.get("min") is not None and value < field["min"]:
            raise ValueError(f"La valeur doit être au moins {field['min']}.")
        if field.get("max") is not None and value > field["max"]:
            raise ValueError(f"La valeur doit être au plus {field['max']}.")
        return value
    if field_type == "select":
        if value not in (field.get("options") or []):
            raise ValueError("Cette option n'existe pas pour ce champ.")
        return value
    if field_type == "text":
        if not isinstance(value, str):
            raise ValueError("Un texte est attendu.")
        if len(value) > TEXT_MAX_LENGTH:
            raise ValueError(
                f"Le texte ne peut pas dépasser {TEXT_MAX_LENGTH} caractères."
            )
        return value
    raise ValueError("Type de champ inconnu.")


def validate_answers(schema: dict, answers, *, strict: bool = False) -> dict:
    """
    Validate the answers of a visit against its (snapshot) schema and return the cleaned answers.
    Empty answers (None or "") are dropped. With strict=True, the required fields must be answered.
    Raise AnswersValidationError with one message per field id.
    """
    if not isinstance(answers, dict):
        raise AnswersValidationError({"__all__": "Les réponses doivent être un objet."})

    fields = {field["id"]: field for _, field in iter_schema_fields(schema)}
    errors: Dict[str, str] = {}
    cleaned: Dict[str, Any] = {}

    for field_id, value in answers.items():
        field = fields.get(field_id)
        if field is None:
            errors[field_id] = "Ce champ n'existe pas dans le formulaire de la visite."
            continue
        if not _has_value(value):
            continue
        try:
            cleaned[field_id] = _clean_answer(field, value)
        except ValueError as e:
            errors[field_id] = str(e)

    if strict:
        for field_id, field in fields.items():
            if (
                field.get("required", True)
                and field_id not in cleaned
                and field_id not in errors
            ):
                errors[field_id] = "Ce champ est obligatoire pour terminer la visite."

    if errors:
        raise AnswersValidationError(errors)
    return cleaned


def compute_progress(schema: dict, answers: dict) -> dict:
    """
    Progress of a visit: answered fields, required fields still missing, and the same figures per section.
    """
    answers = answers if isinstance(answers, dict) else {}
    sections = []
    done = total = missing_required = 0
    for section in sorted(schema.get("sections", []), key=lambda s: s.get("order", 0)):
        fields = sorted(section.get("fields", []), key=lambda f: f.get("order", 0))
        section_done = sum(1 for f in fields if _has_value(answers.get(f["id"])))
        section_missing = sum(
            1
            for f in fields
            if f.get("required", True) and not _has_value(answers.get(f["id"]))
        )
        sections.append(
            {
                "id": section["id"],
                "title": section.get("title", ""),
                "done": section_done,
                "total": len(fields),
                "missing_required": section_missing,
                "complete": section_done == len(fields),
            }
        )
        done += section_done
        total += len(fields)
        missing_required += section_missing
    return {
        "done": done,
        "total": total,
        "pct": round(done / total * 100) if total else 0,
        "missing_required": missing_required,
        "by_section": sections,
    }
