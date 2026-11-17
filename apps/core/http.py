"""Reading of the request parameters shared by the views of the apps."""

from django.http import HttpRequest


def filter_params(
    request: HttpRequest, *names: str, include_post: bool = False
) -> dict[str, str]:
    """Return the list filters of a request, stripped, as keyword arguments of a service.

    Only the parameters present in the request are returned, so that the service
    applies its own defaults to the missing ones. A parameter sent empty is kept
    (``status=`` means "every status" in some lists).

    Args:
        request: Current request.
        *names: Names of the filters to read.
        include_post: Also read the POST data, the GET value winning when not empty
            (a form posted from a filtered list).

    Returns:
        The filters, by name.
    """
    sources = [request.GET, request.POST] if include_post else [request.GET]
    params = {}
    for name in names:
        if any(name in source for source in sources):
            value = next((s.get(name) for s in sources if s.get(name)), "")
            params[name] = value.strip()
    return params
