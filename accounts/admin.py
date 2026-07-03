from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import CustomUser, Inspector

class InspectorInline(admin.StackedInline):
    model = Inspector
    can_delete = False
    verbose_name_plural = "Détails de l'Inspecteur"
    fk_name = "user"

class CustomUserAdmin(UserAdmin):

    inlines = [InspectorInline]
    
    fieldsets = list(UserAdmin.fieldsets) + [
        (None, {'fields': ('phone_number',)}),
    ]
    
    add_fieldsets = list(UserAdmin.add_fieldsets) + [
        (None, {'fields': ('phone_number',)}),
    ]

admin.site.register(CustomUser, CustomUserAdmin)