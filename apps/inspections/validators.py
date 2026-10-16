"""Pydantic schemas and validation of visit templates and visit answers.

A visit template describes a form in JSON. Each visit works on its own copy of it
(``VisitInstance.instance_schema``) and stores its answers as
``{"answers": {"<field id>": value}}``. These functions do not depend on the views,
so they can be tested alone.
"""

from typing import Any, Dict, Iterator, List, Literal, Optional

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
    """A question of a visit template.

    Attributes:
        id: Identifier of the field, unique in the whole template.
        label: Question displayed to the inspector.
        type: Kind of answer: ``boolean``, ``text``, ``select`` or ``number``.
        required: Whether the field must be answered to finish the visit.
        options: Possible answers of a ``select`` field (at least one, no duplicate).
        order: Display position inside the section.
        unit: Unit of a ``number`` field.
        step: Increment of a ``number`` field.
        min: Smallest accepted value of a ``number`` field.
        max: Largest accepted value of a ``number`` field.
    """

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
    def check_options(self) -> "FieldSchema":
        """Check that a ``select`` field has at least one option and no duplicate.

        Returns:
            The validated field.

        Raises:
            ValueError: If the options are missing or duplicated.
        """
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
    def check_bounds(self) -> "FieldSchema":
        """Check that the minimum is not greater than the maximum.

        Returns:
            The validated field.

        Raises:
            ValueError: If ``min`` is greater than ``max``.
        """
        if self.min is not None and self.max is not None and self.min > self.max:
            raise ValueError(
                f"Le champ « {self.label} » a un minimum supérieur au maximum."
            )
        return self


class SectionSchema(BaseModel):
    """A group of fields of a visit template.

    Attributes:
        id: Identifier of the section, unique in the template.
        title: Title displayed to the inspector.
        order: Display position in the template.
        fields: Fields of the section.
    """

    id: str
    title: str
    order: int
    fields: List[FieldSchema]


class VisitTemplateSchema(BaseModel):
    """Structure of a visit template: versioned list of sections.

    Attributes:
        version: Version of the schema format.
        sections: Sections of the template (at least one).
    """

    version: str = "1.0"
    sections: List[SectionSchema]

    @field_validator("sections")
    @classmethod
    def check_not_empty(cls, sections: List[SectionSchema]) -> List[SectionSchema]:
        """Check that the template has at least one section.

        Args:
            sections: Sections to validate.

        Returns:
            The sections, unchanged.

        Raises:
            ValueError: If there is no section.
        """
        if not sections:
            raise ValueError("Le template doit contenir au moins une section.")
        return sections

    @model_validator(mode="after")
    def check_unique_ids(self) -> "VisitTemplateSchema":
        """Check that section ids are unique, and field ids are unique in the template.

        Returns:
            The validated template.

        Raises:
            ValueError: If an id is duplicated.
        """
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
    """Validation error of the visit answers, carrying one message per field id.

    Attributes:
        field_errors: Error message by field id (``__all__`` for a global error).
    """

    def __init__(self, errors: Dict[str, str]) -> None:
        """Store the messages and build the Django error from them.

        Args:
            errors: Error message by field id.
        """
        self.field_errors = errors
        super().__init__(errors)


# get_default_template_structure returns the default JSON skeleton for a new visit template.
def get_default_template_structure() -> Dict[str, Any]:
    """Return the default JSON skeleton of a new visit template.

    Returns:
        A template with one example section holding one example boolean field.
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


def _format_pydantic_error(error: PydanticValidationError) -> str:
    """Turn a Pydantic error into one readable message.

    Args:
        error: Error raised by the schema validation.

    Returns:
        The messages joined by `` ; ``, each prefixed by the location of the field
        in the schema.
    """
    messages = []
    for item in error.errors():
        location = " > ".join(str(part) for part in item["loc"])
        message = item["msg"].removeprefix("Value error, ")
        messages.append(f"{location} : {message}" if location else message)
    return " ; ".join(messages)


def validate_template_schema(schema: Any) -> dict:
    """Validate the structure of a visit template (or of a visit snapshot).

    Args:
        schema: Structure to validate, expected to be a dict.

    Returns:
        The schema, unchanged.

    Raises:
        django.core.exceptions.ValidationError: If the structure is invalid. Django's
            error is used so that models, forms and services can all rely on it.
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


def iter_schema_fields(schema: dict) -> Iterator[tuple[dict, dict]]:
    """Iterate over the fields of a schema, in display order.

    Args:
        schema: Template structure or visit snapshot.

    Yields:
        A ``(section, field)`` pair of dicts for each field.
    """
    for section in sorted(schema.get("sections", []), key=lambda s: s.get("order", 0)):
        for field in sorted(section.get("fields", []), key=lambda f: f.get("order", 0)):
            yield section, field


def _has_value(value: Any) -> bool:
    """Tell whether an answer is filled: neither None nor an empty string."""
    return value is not None and value != ""


def _clean_answer(field: dict, value: Any) -> Any:
    """Check the answer of one field against its definition.

    Args:
        field: Field definition (type, options, bounds).
        value: Answer to check.

    Returns:
        The cleaned value.

    Raises:
        ValueError: With a message for the user, if the value is invalid.
    """
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


def validate_answers(schema: dict, answers: Any, *, strict: bool = False) -> dict:
    """Validate the answers of a visit against its (snapshot) schema.

    Checks the field id, the type, the options and the bounds. Empty answers
    (None or an empty string) are dropped.

    Args:
        schema: Snapshot of the visit structure.
        answers: Answers to validate, ``{field id: value}``.
        strict: If True, the required fields must also be answered. Only used when
            the visit is finished.

    Returns:
        The cleaned answers.

    Raises:
        AnswersValidationError: With one message per field id.
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
    """Compute the progress of a visit.

    Args:
        schema: Snapshot of the visit structure.
        answers: Answers of the visit, ``{field id: value}``.

    Returns:
        A dict with ``done`` (answered fields), ``total``, ``pct``,
        ``missing_required`` and ``by_section``, a list with the same figures for
        each section (``id``, ``title``, ``done``, ``total``,
        ``missing_required``, ``complete``).
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
