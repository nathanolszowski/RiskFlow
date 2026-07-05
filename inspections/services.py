
from inspections.models import InspectionFolder


def create_inspection_folder(form, user):
    folder = form.save(commit=False)
    folder.created_by = user
    folder.save()
    return folder

def get_inspection_folders_by_user(user):
    return InspectionFolder.objects.filter(
        created_by=user,
        is_active=True
    ).select_related("client")

#modified_inspection_folder
#archived_inspection_folder
#unarchive_inspection_folder
#delete_inspection_folder