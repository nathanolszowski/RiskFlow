from django.contrib import admin
from .models import Company

@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ('reference', 'name', 'siret', 'business_line', 'is_active', 'created_at')
    list_filter = ('is_active', 'business_line')
    search_fields = ('name', 'reference', 'siret')
    readonly_fields = ('created_by', 'created_at', 'updated_by', 'updated_at', 'archived_at', 'archived_by')
    
    def save_model(self, request, obj, form, change):
        """
        Fill in the created_by and updated_by fields automatically based on the current user.
        """
        if not change:
            obj.created_by = request.user
        else:
            obj.updated_by = request.user
        super().save_model(request, obj, form, change)