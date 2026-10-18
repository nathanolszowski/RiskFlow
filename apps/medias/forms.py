"""Forms of the medias app: multiple upload and edition of a media."""

from functools import cached_property
from typing import TYPE_CHECKING, Any, Optional

from django import forms
from django.core.exceptions import ValidationError
from django.db.models import Q
from inspections.models import Recommandation, VisitInstance

from .models import Media, MediaTag
from .services.tags import normalize_tag_names, parse_tag_names
from .services.validation import ACCEPT_ATTRIBUTE

if TYPE_CHECKING:
    from inspections.models import InspectionFolder


class MultipleFileInput(forms.ClearableFileInput):
    """File input accepting several files."""

    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    """File field returning the list of the uploaded files."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Use the multiple file input unless another widget is given.

        Args:
            *args: Positional arguments passed to ``FileField``.
            **kwargs: Keyword arguments passed to ``FileField``.
        """
        kwargs.setdefault("widget", MultipleFileInput())
        super().__init__(*args, **kwargs)

    def clean(self, data: Any, initial: Any = None) -> list:
        """Clean every file; the format and the size are checked by the service.

        Args:
            data: One uploaded file or the list of the uploaded files.
            initial: Initial value of the field, unused.

        Returns:
            The list of the cleaned files.
        """
        clean_one = super().clean
        if isinstance(data, (list, tuple)):
            return [clean_one(d, initial) for d in data]
        return [clean_one(data, initial)]


def target_choices(folder: "InspectionFolder", current: Optional[str] = None) -> list:
    """Return the choices ``folder`` / ``visit:<pk>`` / ``recommandation:<pk>`` of a folder.

    Only active visits and recommendations are offered, plus the ``current`` target of
    a media being edited, even archived, so that saving never detaches it by accident.

    Args:
        folder: Folder of the media.
        current: Current target value of the media (``visit:<pk>`` or ``recommandation:<pk>``).

    Returns:
        The choices of a ``ChoiceField``, with the visits and the recommendations grouped.
    """
    current_visit = (
        int(current[6:]) if current and current.startswith("visit:") else None
    )
    current_reco = (
        int(current[15:]) if current and current.startswith("recommandation:") else None
    )

    def label(text: str, active: bool) -> str:
        """Flag the label of an archived target.

        Args:
            text: Label of the target.
            active: Whether the target is active.

        Returns:
            The label, followed by ``(archivée)`` when the target is archived.
        """
        return text if active else f"{text} (archivée)"

    visits = [
        (
            f"visit:{v.pk}",
            label(
                v.due_date.strftime("%d/%m/%Y") + f" · {v.display_template_name}"
                if v.due_date
                else v.display_template_name,
                v.is_active,
            ),
        )
        for v in VisitInstance.objects.filter(folder=folder).filter(
            Q(is_active=True) | Q(pk=current_visit)
        )
    ]
    recos = [
        (
            f"recommandation:{r.pk}",
            label(f"REC-{r.pk} · {r.topic or 'Sans sujet'}", r.is_active),
        )
        for r in Recommandation.objects.filter(folder=folder).filter(
            Q(is_active=True) | Q(pk=current_reco)
        )
    ]
    choices: list = [("folder", "Dossier (général)")]
    if visits:
        choices.append(("Visites", visits))
    if recos:
        choices.append(("Recommandations", recos))
    return choices


def split_target(
    value: str, folder: "InspectionFolder"
) -> tuple[Optional[VisitInstance], Optional[Recommandation]]:
    """Return the visit or the recommendation designated by a target value.

    Args:
        value: ``visit:<pk>``, ``recommandation:<pk>`` or ``folder``.
        folder: Folder the target must belong to.

    Returns:
        A ``(visit, recommendation)`` tuple, both None for ``folder``.

    Raises:
        DoesNotExist: If the target does not exist in the folder.
    """
    if value.startswith("visit:"):
        return VisitInstance.objects.get(pk=int(value[6:]), folder=folder), None
    if value.startswith("recommandation:"):
        return None, Recommandation.objects.get(pk=int(value[15:]), folder=folder)
    return None, None


class _TargetForm(forms.Form):
    """Common part: choice of the target of the media.

    Attributes:
        target: ``folder``, ``visit:<pk>`` or ``recommandation:<pk>``.
        folder: Folder the media belongs to.
    """

    target = forms.ChoiceField(label="Rattacher à", required=False)

    def __init__(
        self,
        *args: Any,
        folder: "InspectionFolder",
        current_target: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        """Limit the targets to the ones of the folder and style the widgets.

        Args:
            *args: Positional arguments passed to ``Form``.
            folder: Folder the media belongs to.
            current_target: Current target of a media being edited, kept selectable
                even when archived.
            **kwargs: Keyword arguments passed to ``Form``.
        """
        super().__init__(*args, **kwargs)
        self.folder = folder
        self.fields["target"].choices = target_choices(folder, current_target)
        for field in self.fields.values():
            if not isinstance(
                field.widget, (forms.FileInput, forms.CheckboxSelectMultiple)
            ):
                field.widget.attrs.setdefault("class", "form-input")

    @cached_property
    def _resolved_target(
        self,
    ) -> tuple[Optional[VisitInstance], Optional[Recommandation]]:
        """Look the chosen target up once (``visit`` and ``recommandation`` share it)."""
        return split_target(self.cleaned_data.get("target") or "", self.folder)

    @property
    def visit(self) -> Optional[VisitInstance]:
        """Return the chosen visit, if any."""
        return self._resolved_target[0]

    @property
    def recommandation(self) -> Optional[Recommandation]:
        """Return the chosen recommendation, if any."""
        return self._resolved_target[1]


class _TaggedForm(_TargetForm):
    """Common part: tags of the media, among the ones of the user or typed as new.

    Attributes:
        existing_tags: Tags the user already has.
        new_tags: Names of new tags, separated by commas.
    """

    existing_tags = forms.ModelMultipleChoiceField(
        queryset=MediaTag.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label="Tags existants",
    )
    new_tags = forms.CharField(
        label="Nouveaux tags",
        required=False,
        max_length=500,
        help_text="Séparés par des virgules.",
        widget=forms.TextInput(attrs={"placeholder": "ex. extincteurs, toiture"}),
    )

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Offer the tags of the owner of the folder.

        Args:
            *args: Positional arguments passed to ``Form``.
            **kwargs: Keyword arguments passed to ``Form``.
        """
        super().__init__(*args, **kwargs)
        self.fields["existing_tags"].queryset = MediaTag.objects.filter(
            created_by_id=self.folder.created_by_id, medias__isnull=False
        ).distinct()

    @property
    def tag_names(self) -> list[str]:
        """Return the names of all the chosen tags, existing and new."""
        existing = self.cleaned_data.get("existing_tags") or []
        return [tag.name for tag in existing] + parse_tag_names(
            self.cleaned_data.get("new_tags") or ""
        )

    @property
    def selected_tag_ids(self) -> list[str]:
        """Return the ids of the checked tags, as strings, for the template."""
        return [str(value) for value in (self["existing_tags"].value() or [])]

    def clean(self) -> dict[str, Any]:
        """Check the number and the length of the tags.

        Returns:
            The cleaned data.
        """
        cleaned = super().clean()
        try:
            normalize_tag_names(self.tag_names)
        except ValidationError as error:
            self.add_error("new_tags", error)
        return cleaned


class MediaUploadForm(_TaggedForm):
    """Upload of one or several files, with an optional target and shared notes.

    Attributes:
        files: Uploaded files.
        notes: Notes applied to every file.
    """

    files = MultipleFileField(
        label="Fichiers",
        widget=MultipleFileInput(attrs={"accept": ACCEPT_ATTRIBUTE}),
        # An empty file is refused on its own by validate_upload, not for the whole batch
        allow_empty_file=True,
        error_messages={"required": "Choisissez au moins un fichier."},
    )
    notes = forms.CharField(
        label="Notes (facultatif)",
        required=False,
        widget=forms.Textarea(attrs={"rows": 2}),
    )


class MediaUpdateForm(_TaggedForm):
    """Edition of the caption, the notes and the target of a media.

    Attributes:
        title: Caption.
        notes: Notes.
    """

    title = forms.CharField(label="Légende", required=False, max_length=255)
    notes = forms.CharField(
        label="Notes", required=False, widget=forms.Textarea(attrs={"rows": 3})
    )

    field_order = ["title", "notes", "target"]

    @classmethod
    def for_media(cls, media: Media, data: Any = None) -> "MediaUpdateForm":
        """Build the form pre-filled with the media.

        Args:
            media: Media being edited.
            data: POST data, None for an unbound form.

        Returns:
            The form.
        """
        if media.visit_id:
            target = f"visit:{media.visit_id}"
        elif media.recommandation_id:
            target = f"recommandation:{media.recommandation_id}"
        else:
            target = "folder"
        return cls(
            data,
            folder=media.folder,
            current_target=target,
            initial={
                "title": media.title,
                "notes": media.notes,
                "target": target,
                "existing_tags": list(media.tags.values_list("pk", flat=True)),
            },
        )
