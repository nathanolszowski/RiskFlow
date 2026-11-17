"""Admin of the crm app: companies."""

from django.contrib import admin
from django.forms import ModelForm
from django.http import HttpRequest

from .models import Company


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    """Admin of ``Company``, with the tracking fields in read-only."""

    list_display = (
        "reference",
        "name",
        "siret",
        "business_line",
        "is_active",
        "created_at",
    )
    list_filter = ("is_active", "business_line")
    search_fields = ("name", "reference", "siret")
    readonly_fields = (
        "created_by",
        "created_at",
        "updated_by",
        "updated_at",
        "archived_at",
        "archived_by",
    )

    def save_model(
        self, request: HttpRequest, obj: Company, form: ModelForm, change: bool
    ) -> None:
        """Set ``created_by`` on creation and ``updated_by`` on update to the current user.

        Args:
            request: Current request.
            obj: Company being saved.
            form: Admin form used to edit the company.
            change: True when an existing company is modified, False on creation.
        """
        if not change:
            obj.created_by = request.user
        else:
            obj.updated_by = request.user
        super().save_model(request, obj, form, change)
