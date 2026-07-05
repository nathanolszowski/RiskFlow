from django import forms
from .models import InspectionFolder

class InspectionFolderForm(forms.ModelForm):
    class Meta:
        model = InspectionFolder
        fields = ['reference', 'client']
        
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Taillwind CSS classes for styling the input fields
        input_classes = "block w-full rounded-md border-0 bg-white/5 py-2 text-white shadow-xs ring-1 ring-inset ring-white/10 focus:ring-2 focus:ring-inset focus:ring-indigo-500 sm:text-sm"
        
        self.fields['reference'].widget.attrs.update({
            'class': input_classes,
            'placeholder': 'ex: INSP-2026-001'
        })
        self.fields['client'].widget.attrs.update({
            'class': "block w-full rounded-md border-0 bg-gray-800 py-2 text-white shadow-xs ring-1 ring-inset ring-white/10 focus:ring-2 focus:ring-inset focus:ring-indigo-500 sm:text-sm cursor-pointer"
        })