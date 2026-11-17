from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0003_user_profile_fields"),
    ]

    operations = [
        migrations.RenameField("customuser", "address_line1", "street"),
        migrations.RenameField("customuser", "address_line2", "address_complement"),
    ]
