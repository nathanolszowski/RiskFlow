from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("medias", "0003_media_metadata"),
    ]

    operations = [
        migrations.RenameField(
            model_name="media",
            old_name="kind",
            new_name="media_type",
        ),
    ]
