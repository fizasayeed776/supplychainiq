from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("documents", "0001_initial"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="lineitem",
            constraint=models.UniqueConstraint(
                fields=("document", "position"),
                name="uniq_line_item_position",
            ),
        ),
    ]
