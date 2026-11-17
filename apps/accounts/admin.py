"""Admin of the accounts app: users with their inspector profile."""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import CustomUser, Inspector


class InspectorInline(admin.StackedInline):
    """Inspector profile edited inside the user page."""

    model = Inspector
    can_delete = False
    verbose_name_plural = "Détails de l'Inspecteur"
    fk_name = "user"
    extra = 0  # avoid showing extra empty forms for the inline


@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    """Admin of ``CustomUser``, with the phone number and the inspector profile."""

    # Manage the inline for the Inspector model
    inlines = [InspectorInline]

    # Columns to display in the user list view
    list_display = (
        "username",
        "email",
        "first_name",
        "last_name",
        "phone_number",
        "is_staff",
    )

    # Set the fieldsets to include the phone_number field
    fieldsets = (
        (None, {"fields": ("username", "password")}),
        (
            "Informations personnelles",
            {"fields": ("first_name", "last_name", "email", "phone_number")},
        ),
        (
            "Permissions",
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                )
            },
        ),
        ("Dates importantes", {"fields": ("last_login", "date_joined")}),
    )

    add_fieldsets = UserAdmin.add_fieldsets + (
        (
            "Informations complémentaires",
            {
                "classes": ("collapse",),
                "fields": ("email", "first_name", "last_name", "phone_number"),
            },
        ),
    )
