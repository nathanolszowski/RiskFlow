from django.db import migrations

PHASE_MAPPING = {
    'IN_PROGRESS': 'PREPARATION',
    'REVIEW': 'REPORT',
    'COMPLETED': 'CLOSED',
}


def forwards(apps, schema_editor):
    InspectionFolder = apps.get_model('inspections', 'InspectionFolder')
    for old, new in PHASE_MAPPING.items():
        InspectionFolder.objects.filter(current_phase=old).update(current_phase=new)


def backwards(apps, schema_editor):
    InspectionFolder = apps.get_model('inspections', 'InspectionFolder')
    reverse = {
        'PREPARATION': 'IN_PROGRESS',
        'VISIT': 'IN_PROGRESS',
        'REPORT': 'REVIEW',
        'FOLLOW_UP': 'REVIEW',
        'CLOSED': 'COMPLETED',
    }
    for new, old in reverse.items():
        InspectionFolder.objects.filter(current_phase=new).update(current_phase=old)


class Migration(migrations.Migration):

    dependencies = [
        ('inspections', '0010_alter_inspectionfolder_phases'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
