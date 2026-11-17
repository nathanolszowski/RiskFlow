"""HTMX responses shared by the views of the apps (headers read by HTMX)."""

from django.http import HttpResponse

MODAL_CONTAINER = "#modal-container"


def htmx_refresh(status: int = 200) -> HttpResponse:
    """Return an empty response asking HTMX to reload the current page.

    Args:
        status: Status of the response (204 when nothing is swapped anyway).

    Returns:
        The response, with ``HX-Refresh``.
    """
    response = HttpResponse(status=status)
    response["HX-Refresh"] = "true"
    return response


def htmx_redirect(url: str, status: int = 200) -> HttpResponse:
    """Return an empty response asking HTMX to navigate to another page.

    Args:
        url: Destination.
        status: Status of the response.

    Returns:
        The response, with ``HX-Redirect``.
    """
    response = HttpResponse(status=status)
    response["HX-Redirect"] = url
    return response


def close_modal(response: HttpResponse) -> HttpResponse:
    """Ask the page to close the open modal once the response is swapped.

    The layout listens to ``closeModal`` and empties ``#modal-container``.

    Args:
        response: Response of a valid modal form (the updated grid or tab).

    Returns:
        The same response, with ``HX-Trigger: closeModal``.
    """
    response["HX-Trigger"] = "closeModal"
    return response


def retarget_modal(response: HttpResponse) -> HttpResponse:
    """Swap an invalid modal into the modal container instead of the form target.

    Used when the form of a modal targets another element (a tab, a grid).

    Args:
        response: The modal re-rendered with its errors.

    Returns:
        The same response, with ``HX-Retarget`` and ``HX-Reswap``.
    """
    response["HX-Retarget"] = MODAL_CONTAINER
    response["HX-Reswap"] = "innerHTML"
    return response
