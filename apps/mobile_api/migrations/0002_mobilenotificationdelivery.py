from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("mobile_api", "0001_initial"),
        ("todos", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="MobileNotificationDelivery",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("notification_key", models.CharField(max_length=255, unique=True)),
                ("status", models.CharField(default="pending", max_length=20)),
                ("response_data", models.JSONField(blank=True, default=dict)),
                ("error_message", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("sent_at", models.DateTimeField(blank=True, null=True)),
                ("device", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="deliveries", to="mobile_api.mobilepushdevice")),
                ("todo", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="mobile_deliveries", to="todos.todoitem")),
            ],
            options={"ordering": ["-created_at"]},
        ),
    ]
