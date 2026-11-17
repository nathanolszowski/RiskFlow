"""View decorators shared by all apps."""

from functools import wraps
from typing import TYPE_CHECKING, Any, Callable, Optional, cast

from django.conf import settings
from django.http import HttpRequest, HttpResponse
from django.shortcuts import resolve_url

if TYPE_CHECKING:
    from accounts.models import CustomUser


def htmx_login_required(
    view: Optional[Callable[..., HttpResponse]] = None, *, redirect: bool = True
) -> Callable[..., Any]:
    """Like ``login_required``, but answers 401 to an unauthenticated HTMX request.

    An expired session on an HTMX request would otherwise get a 302 that HTMX
    follows, swapping the login page into the current page. Non-HTMX requests
    are redirected to the login page as usual.

    Usable as ``@htmx_login_required`` or ``@htmx_login_required(redirect=False)``.

    Args:
        view: View to protect, when used without arguments.
        redirect: If True, the 401 carries an ``HX-Redirect`` header to the login
            page. Screens that hold unsaved work (the visit form) pass False and
            tell the user themselves.

    Returns:
        The protected view, or a decorator when called with arguments.
    """

    def decorator(func: Callable[..., HttpResponse]) -> Callable[..., HttpResponse]:
        @wraps(func)
        def wrapper(request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
            if request.user.is_authenticated:
                return func(request, *args, **kwargs)
            if request.headers.get("HX-Request"):
                response = HttpResponse("Session expirée.", status=401)
                if redirect:
                    response["HX-Redirect"] = resolve_url(settings.LOGIN_URL)
                return response
            from django.contrib.auth.views import redirect_to_login

            return redirect_to_login(
                request.get_full_path(), resolve_url(settings.LOGIN_URL)
            )

        return wrapper

    return decorator(view) if view is not None else decorator


def logged_user(request: HttpRequest) -> "CustomUser":
    """Return the logged-in user of a request, typed as ``CustomUser``.

    For views protected by ``htmx_login_required`` (or ``login_required``): the user
    is never anonymous there, so the cast only tells the type checker so.

    Args:
        request: Current request.

    Returns:
        The user of the request.
    """
    return cast("CustomUser", request.user)
