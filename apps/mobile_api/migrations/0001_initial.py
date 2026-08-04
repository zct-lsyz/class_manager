from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = [migrations.swappable_dependency(settings.AUTH_USER_MODEL)]

    operations = [
        migrations.CreateModel(
            name="MobileApiToken",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("token_hash", models.CharField(max_length=64, unique=True)),
                ("device_id", models.CharField(max_length=128)),
                ("device_name", models.CharField(blank=True, default="", max_length=200)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("last_used_at", models.DateTimeField(auto_now=True)),
                ("expires_at", models.DateTimeField()),
                ("revoked_at", models.DateTimeField(blank=True, null=True)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="mobile_api_tokens", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-last_used_at"]},
        ),
        migrations.CreateModel(
            name="MobilePushDevice",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("device_id", models.CharField(max_length=128)),
                ("provider", models.CharField(choices=[("xiaomi", "小米推送"), ("local", "本地通知")], default="local", max_length=20)),
                ("registration_id", models.CharField(blank=True, default="", max_length=500)),
                ("device_name", models.CharField(blank=True, default="", max_length=200)),
                ("app_version", models.CharField(blank=True, default="", max_length=50)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("last_seen_at", models.DateTimeField(auto_now=True)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="mobile_push_devices", to=settings.AUTH_USER_MODEL)),
            ],
            options={"unique_together": {("user", "device_id", "provider")}},
        ),
        migrations.AddIndex(
            model_name="mobileapitoken",
            index=models.Index(fields=["user", "device_id"], name="mobile_api__user_id_9b4899_idx"),
        ),
    ]
