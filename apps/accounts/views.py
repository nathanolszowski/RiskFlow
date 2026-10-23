"""Views of the profile page. Every section is an HTMX fragment swapped in place."""

from core.decorators import htmx_login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET, require_http_methods

from .forms import AddressForm, EmailForm, ProfilePasswordForm
from .services import profile as profile_service

PARTIALS = "accounts/partials/profile/"


@htmx_login_required
@require_GET
def profile(request: HttpRequest) -> HttpResponse:
    """Render the profile page."""
    return render(
        request,
        "accounts/profile.html",
        {
            "inspector": profile_service.get_inspector_profile(request.user),
            "password_form": ProfilePasswordForm(request.user),
        },
    )


def _section(request, name, form, editing, status=200, **extra):
    """Render one profile section, in read or edit mode."""
    return render(
        request,
        f"{PARTIALS}{name}.html",
        {"form": form, "editing": editing, **extra},
        status=status,
    )


@htmx_login_required
@require_http_methods(["GET", "POST"])
def profile_email(request: HttpRequest) -> HttpResponse:
    """Show the e-mail (``?edit=1`` for the form) or save it."""
    if request.method == "POST":
        form = EmailForm(request.POST, instance=request.user)
        if not form.is_valid():
            return _section(request, "email", form, True, status=422)
        profile_service.update_email(request.user, form.cleaned_data["email"])
        return _section(request, "email", EmailForm(instance=request.user), False)
    return _section(
        request,
        "email",
        EmailForm(instance=request.user),
        "edit" in request.GET,
    )


@htmx_login_required
@require_http_methods(["GET", "POST"])
def profile_address(request: HttpRequest) -> HttpResponse:
    """Show the home address (``?edit=1`` for the form) or save it."""
    if request.method == "POST":
        form = AddressForm(request.POST, instance=request.user)
        if not form.is_valid():
            return _section(request, "address", form, True, status=422)
        profile_service.update_address(request.user, form.cleaned_data)
        return _section(request, "address", AddressForm(instance=request.user), False)
    return _section(
        request,
        "address",
        AddressForm(instance=request.user),
        "edit" in request.GET,
    )


@htmx_login_required
@require_http_methods(["POST"])
def profile_password(request: HttpRequest) -> HttpResponse:
    """Change the password and keep the user logged in."""
    form = ProfilePasswordForm(request.user, request.POST)
    if not form.is_valid():
        return _section(request, "password", form, True, status=422)
    profile_service.change_password(request, form)
    return _section(
        request, "password", ProfilePasswordForm(request.user), False, saved=True
    )
