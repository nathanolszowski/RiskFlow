from functools import wraps

from django.conf import settings
from django.http import HttpResponse
from django.shortcuts import resolve_url


def htmx_login_required(view=None, *, redirect=True):
    """
    Like login_required, but an expired session on an HTMX request answers 401, instead of a 302 that HTMX
    would follow and swap the login page into the current page.
    With redirect=True the 401 carries HX-Redirect to the login page. Screens that hold unsaved
    work (the visit form) use redirect=False and tell the user themselves.
    Usable as @htmx_login_required or @htmx_login_required(redirect=False).
    """

    def decorator(func):
        @wraps(func)
        def wrapper(request, *args, **kwargs):
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
