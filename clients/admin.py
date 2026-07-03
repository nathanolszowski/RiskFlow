from django.contrib import admin
from .models import Clients

@admin.register(Clients)
class ClientsAdmin(admin.ModelAdmin):
    list_display = ('reference', 'name', 'siret', 'business_line', 'is_active', 'created_at')
    
    # Filters on right sidebar for quick filtering
    list_filter = ('is_active', 'business_line')
    
    # Search fields for quick lookup
    search_fields = ('name', 'reference', 'siret')
    
    # Readonly fields pour éviter la modification directe de ces champs
    readonly_fields = ('created_by', 'created_at', 'updated_by', 'updated_at')

    def save_model(self, request, obj, form, change):
        """
        Fill in the created_by and updated_by fields automatically based on the current user.
        """
        if not change:
            obj.created_by = request.user
        else:
            obj.updated_by = request.user
        super().save_model(request, obj, form, change)