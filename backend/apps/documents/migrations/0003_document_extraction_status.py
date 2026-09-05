from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("documents", "0002_lineitem_position"),
    ]

    operations = [
        migrations.AddField(
            model_name="document",
            name="extraction_status",
            field=models.CharField(
                choices=[
                    ("pending", "Pending"),
                    ("running", "Running"),
                    ("done", "Done"),
                    ("failed", "Failed"),
                ],
                default="pending",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="document",
            name="failure_reason",
            field=models.TextField(blank=True),
        ),
    ]
