"""Views of the medias app: folder tab, upload, edition, protected file access, archiving."""

import re
from typing import BinaryIO, Optional

from core.decorators import htmx_login_required
from core.modals import delete_confirm_modal
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.storage import FileSystemStorage
from django.db.models.fields.files import FieldFile
from django.http import FileResponse, Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.http import content_disposition_header
from django.views.decorators.http import require_GET, require_http_methods, require_POST
from inspections.models import InspectionFolder
from inspections.services.inspectionfolder import get_inspection_folder_by_id

from .forms import MediaUpdateForm, MediaUploadForm, target_choices
from .models import Media
from .services.media import (
    archive_media,
    create_media,
    delete_media,
    get_filtered_medias,
    get_folder_usage,
    get_media_by_id,
    unarchive_media,
    update_media,
)
from .services.tags import get_folder_tags
from .services.validation import ACCEPT_ATTRIBUTE

# Media types a browser can display inline; the Office files are always downloaded
INLINE_MEDIA_TYPES = {Media.MediaType.IMAGE, Media.MediaType.PDF, Media.MediaType.VIDEO}


def _tab_context(
    request: HttpRequest, folder: InspectionFolder, targets: Optional[list] = None
) -> dict:
    """Build the context of the medias tab from the filters of the query string.

    Args:
        request: Current request. Filters: ``q``, ``media_type``, ``target``, ``tag``, ``status``.
        folder: Folder of the medias.
        targets: Target choices, when the caller already holds them (saves a query).

    Returns:
        The context of ``tab_medias.html``.
    """
    params = request.GET
    status = "archived" if params.get("status") == "archived" else "active"
    q = params.get("q", "").strip()
    media_type = params.get("media_type", "")
    target = params.get("target", "")
    tag = params.get("tag", "").strip()
    return {
        "folder": folder,
        "status": status,
        "q": q,
        "media_type": media_type,
        "target": target,
        "tag": tag,
        "tags": get_folder_tags(folder, request.user),
        "media_types": Media.MediaType.choices,
        "targets": targets if targets is not None else target_choices(folder),
        "medias": get_filtered_medias(
            folder,
            request.user,
            q=q,
            media_type=media_type,
            target=target,
            tag=tag,
            status=status,
        ),
        "usage": get_folder_usage(folder),
        "active_count": folder.medias.filter(is_active=True).count(),
        "archived_count": folder.medias.filter(is_active=False).count(),
    }


def _render_medias_tab(request: HttpRequest, folder: InspectionFolder) -> HttpResponse:
    """Render the medias tab content (filters read from the query string).

    Args:
        request: Current request.
        folder: Folder of the medias.

    Returns:
        The tab fragment.
    """
    return render(
        request, "medias/partials/tabs/tab_medias.html", _tab_context(request, folder)
    )


def _invalid_modal(
    request: HttpRequest,
    template: str,
    context: dict,
    folder: InspectionFolder,
    targets: Optional[list] = None,
) -> HttpResponse:
    """Re-render a modal with its errors (422) and refresh the tab behind it.

    Args:
        request: Current request.
        template: Template of the modal.
        context: Context of the modal.
        folder: Folder of the medias.
        targets: Target choices of the folder, when the caller already holds them.

    Returns:
        A 422 with ``HX-Retarget`` on the modal container; the tab is swapped
        out-of-band so that the files accepted before the error are listed.
    """
    html = render_to_string(template, context, request)
    tab = render_to_string(
        "medias/partials/tabs/tab_medias.html",
        _tab_context(request, folder, targets),
        request,
    )
    # The tab is swapped out-of-band: files accepted before the error are listed
    response = HttpResponse(
        f'{html}<div id="tab-content" hx-swap-oob="innerHTML">{tab}</div>', status=422
    )
    response["HX-Retarget"] = "#modal-container"
    response["HX-Reswap"] = "innerHTML"
    return response


@htmx_login_required
@require_GET
def folder_tab_medias(request: HttpRequest, pk: int) -> HttpResponse:
    """Render only the content of the medias tab.

    Args:
        request: Current request. Filters: ``q``, ``media_type``, ``target``, ``tag``, ``status``.
        pk: Primary key of the folder.

    Returns:
        The tab fragment.

    Raises:
        Http404: If the folder does not exist or belongs to another user.
    """
    folder = get_inspection_folder_by_id(pk, request.user)
    return _render_medias_tab(request, folder)


@htmx_login_required
@require_http_methods(["GET", "POST"])
def media_upload(request: HttpRequest, folder_id: int) -> HttpResponse:
    """Upload one or several files in a modal (HTMX, multipart).

    Each file is validated on its own: the valid ones are saved even when others
    are refused, and the refusals are listed in the modal (422).

    Args:
        request: Current request. On GET, ``target`` pre-selects the target.
        folder_id: Primary key of the folder.

    Returns:
        A 409 if the folder is archived. On GET, the modal. On a fully valid POST, the
        tab with ``HX-Trigger: closeModal``. If a file is refused or the form is
        invalid, the modal with its errors (422).

    Raises:
        Http404: If the folder does not exist or belongs to another user.
    """
    folder = get_inspection_folder_by_id(folder_id, request.user)
    if not folder.is_active:
        return HttpResponse("Le dossier est archivé.", status=409)

    def context(form: MediaUploadForm, errors: Optional[list] = None) -> dict:
        """Build the context of the upload modal.

        Args:
            form: Upload form.
            errors: ``(file name, message)`` pairs of the files refused by the service.

        Returns:
            The context of ``media_upload_modal.html``.
        """
        return {
            "folder": folder,
            "form": form,
            "usage": get_folder_usage(folder),
            "accept": ACCEPT_ATTRIBUTE,
            "limits_mb": settings.MEDIA_MAX_SIZE_BY_TYPE,
            "file_errors": errors or [],
            "file_errors_json": [f"« {n} » : {m}" for n, m in (errors or [])]
            + list(form.errors.get("files", []) if form.is_bound else []),
        }

    modal = "medias/partials/media/media_upload_modal.html"

    if request.method == "POST":
        form = MediaUploadForm(request.POST, request.FILES, folder=folder)
        if form.is_valid():
            visit, recommandation = form.visit, form.recommandation
            errors = []
            for uploaded in form.cleaned_data["files"]:
                try:
                    create_media(
                        folder,
                        request.user,
                        uploaded,
                        visit=visit,
                        recommandation=recommandation,
                        notes=form.cleaned_data["notes"],
                        tags=form.tag_names,
                    )
                except ValidationError as e:
                    errors.append((uploaded.name, " ".join(e.messages)))
            if not errors:
                response = _render_medias_tab(request, folder)
                response["HX-Trigger"] = "closeModal"
                return response
            return _invalid_modal(
                request,
                modal,
                context(form, errors),
                folder,
                form.fields["target"].choices,
            )
        return _invalid_modal(
            request, modal, context(form), folder, form.fields["target"].choices
        )

    form = MediaUploadForm(
        folder=folder, initial={"target": request.GET.get("target", "folder")}
    )
    return render(request, modal, context(form))


@htmx_login_required
@require_http_methods(["GET", "POST"])
def media_update(request: HttpRequest, pk: int) -> HttpResponse:
    """Edit the caption, the notes and the target of a media in a modal (HTMX).

    Args:
        request: Current request.
        pk: Primary key of the media.

    Returns:
        On GET, the form (``media_update_modal.html``). On a valid POST, the tab with
        ``HX-Trigger: closeModal``. On an invalid POST, the form with its errors (422).

    Raises:
        Http404: If the media does not exist or belongs to another user.
    """
    media = get_media_by_id(pk, request.user)
    folder = media.folder
    modal = "medias/partials/media/media_update_modal.html"

    if request.method == "POST":
        form = MediaUpdateForm.for_media(media, request.POST)
        if form.is_valid():
            try:
                update_media(
                    media,
                    request.user,
                    title=form.cleaned_data["title"],
                    notes=form.cleaned_data["notes"],
                    visit=form.visit,
                    recommandation=form.recommandation,
                    tags=form.tag_names,
                )
            except ValidationError as e:
                form.add_error("target", e)
            else:
                response = _render_medias_tab(request, folder)
                response["HX-Trigger"] = "closeModal"
                return response
        return _invalid_modal(request, modal, {"media": media, "form": form}, folder)

    return render(
        request, modal, {"media": media, "form": MediaUpdateForm.for_media(media)}
    )


class _Slice:
    """Read-only view on ``length`` bytes of an open file, for a partial response."""

    def __init__(self, handle: BinaryIO, length: int) -> None:
        """Wrap an open file, already positioned on the first byte to send.

        Args:
            handle: Open file.
            length: Number of bytes to expose.
        """
        self._handle, self._left = handle, length

    def read(self, size: int = -1) -> bytes:
        """Read at most ``size`` bytes, without going past the end of the slice.

        Args:
            size: Maximum number of bytes, the rest of the slice if negative.

        Returns:
            The bytes read.
        """
        size = self._left if size < 0 else min(size, self._left)
        data = self._handle.read(size)
        self._left -= len(data)
        return data

    def close(self) -> None:
        """Close the underlying file."""
        self._handle.close()


def _parse_range(header: str, size: int) -> Optional[tuple[int, int]]:
    """Return the ``(first, last)`` bytes of a single-range header.

    Args:
        header: Value of the ``Range`` header, e.g. ``bytes=0-1023``.
        size: Size of the file in bytes.

    Returns:
        The inclusive byte positions, or None if the header is invalid or out of range.
    """
    match = re.fullmatch(r"bytes=(\d*)-(\d*)", header.strip())
    if not match or not (match[1] or match[2]):
        return None
    if match[1]:
        first = int(match[1])
        last = int(match[2]) if match[2] else size - 1
    else:
        # Suffix range: the last N bytes
        first, last = max(size - int(match[2]), 0), size - 1
    last = min(last, size - 1)
    return (first, last) if first <= last else None


def _serve(
    request: HttpRequest, media: Media, field: FieldFile, *, inline: bool
) -> HttpResponse:
    """Serve a stored file; the caller has already checked the ownership.

    Local storage: streamed by Django, with byte ranges. Remote storage (S3/R2):
    redirect to a short-lived signed URL, so the bucket stays private.

    Args:
        request: Current request.
        media: Media the file belongs to.
        field: File to serve, the file or the thumbnail of the media.
        inline: True to display the file in the browser, False to download it.

    Returns:
        The file (200 or 206), a 416 for an invalid range, or a redirect to the signed URL.

    Raises:
        Http404: If there is no file or it is missing from the storage.
    """
    if not field:
        raise Http404("Fichier introuvable.")
    disposition = content_disposition_header(not inline, media.original_name)
    storage = field.storage
    if isinstance(storage, FileSystemStorage):
        try:
            handle = storage.open(field.name, "rb")
        except FileNotFoundError:
            raise Http404("Fichier introuvable.")
        size = storage.size(field.name)
        # Safari/iPadOS only plays a video served with byte ranges (206)
        range_header = request.headers.get("Range")
        if range_header:
            byte_range = _parse_range(range_header, size)
            if byte_range is None:
                handle.close()
                response = HttpResponse(status=416)
                response["Content-Range"] = f"bytes */{size}"
                return response
            first, last = byte_range
            handle.seek(first)
            response = FileResponse(
                _Slice(handle, last - first + 1),
                status=206,
                content_type=media.content_type,
            )
            response["Content-Range"] = f"bytes {first}-{last}/{size}"
            response["Content-Length"] = str(last - first + 1)
        else:
            response = FileResponse(handle, content_type=media.content_type)
            response["Content-Length"] = str(size)
        response["Accept-Ranges"] = "bytes"
        response["X-Content-Type-Options"] = "nosniff"
        if media.media_type != Media.MediaType.PDF:
            # Defense in depth: nothing served here may run scripts on the app origin
            # (the browser PDF viewer does not work in a sandboxed document)
            response["Content-Security-Policy"] = "sandbox"
        response["Content-Disposition"] = disposition
        response["Cache-Control"] = "private, max-age=300"
        return response
    url = storage.url(
        field.name,
        parameters={
            "ResponseContentDisposition": disposition,
            "ResponseContentType": media.content_type,
        },
    )
    return redirect(url)


@htmx_login_required
@require_GET
def media_file(request: HttpRequest, pk: int) -> HttpResponse:
    """Serve the file of a media to its owner.

    Images, PDF and videos are displayed inline; ``?download=1`` forces the download
    and the Office files are always downloaded.

    Args:
        request: Current request.
        pk: Primary key of the media.

    Returns:
        The file, or a redirect to its signed URL.

    Raises:
        Http404: If the media does not exist or belongs to another user.
    """
    media = get_media_by_id(pk, request.user)
    inline = media.media_type in INLINE_MEDIA_TYPES and not request.GET.get("download")
    return _serve(request, media, media.file, inline=inline)


@htmx_login_required
@require_GET
def media_thumbnail(request: HttpRequest, pk: int) -> HttpResponse:
    """Serve the thumbnail of an image to its owner.

    Args:
        request: Current request.
        pk: Primary key of the media.

    Returns:
        The thumbnail, or a redirect to its signed URL.

    Raises:
        Http404: If the media does not exist, has no thumbnail or belongs to another user.
    """
    media = get_media_by_id(pk, request.user)
    return _serve(request, media, media.thumbnail, inline=True)


@htmx_login_required
@require_POST
def media_archive(request: HttpRequest, pk: int) -> HttpResponse:
    """Archive a media.

    Args:
        request: Current request.
        pk: Primary key of the media.

    Returns:
        The tab for an HTMX request, otherwise a redirect to the folder.

    Raises:
        Http404: If the media does not exist or belongs to another user.
    """
    media = get_media_by_id(pk, request.user)
    archive_media(media, request.user)
    if request.headers.get("HX-Request"):
        return _render_medias_tab(request, media.folder)
    return redirect("inspections:folder_detail", pk=media.folder_id)


@htmx_login_required
@require_POST
def media_unarchive(request: HttpRequest, pk: int) -> HttpResponse:
    """Unarchive a media.

    Args:
        request: Current request.
        pk: Primary key of the media.

    Returns:
        The tab for an HTMX request, otherwise a redirect to the folder.

    Raises:
        Http404: If the media does not exist or belongs to another user.
    """
    media = get_media_by_id(pk, request.user)
    unarchive_media(media, request.user)
    if request.headers.get("HX-Request"):
        return _render_medias_tab(request, media.folder)
    return redirect("inspections:folder_detail", pk=media.folder_id)


@htmx_login_required
@require_http_methods(["GET", "POST"])
def media_delete(request: HttpRequest, pk: int) -> HttpResponse:
    """Permanently delete an archived media (confirmation modal on GET).

    Args:
        request: Current request.
        pk: Primary key of the media.

    Returns:
        On GET, the confirmation modal. On POST, a 409 if the media is still active,
        otherwise the tab for an HTMX request or a redirect to the folder.

    Raises:
        Http404: If the media does not exist or belongs to another user.
    """
    media = get_media_by_id(pk, request.user)

    if request.method == "GET":
        return delete_confirm_modal(
            request,
            media,
            title="Supprimer définitivement ce média ?",
            label=media.display_name,
            post_url=reverse("medias:media_delete", args=[media.pk]),
            post_target="#tab-content",
            sections=[{"warning": True, "title": "Cette action est irréversible."}],
        )

    if media.is_active:
        return HttpResponse(
            "Le média doit être archivé avant d'être supprimé.", status=409
        )

    folder = media.folder
    delete_media(media)
    if request.headers.get("HX-Request"):
        return _render_medias_tab(request, folder)
    return redirect("inspections:folder_detail", pk=folder.pk)
