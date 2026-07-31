from django.db import migrations, models


def migrate_layouts(apps, schema_editor):
    ClassroomLayout = apps.get_model("seating", "ClassroomLayout")
    for layout in ClassroomLayout.objects.all():
        positions = []
        if layout.has_left_aisle and layout.cols > 1:
            positions.append(1)
        if layout.has_middle_aisle and layout.cols > 1:
            positions.append(max(1, layout.cols // 2))
        if layout.has_right_aisle and layout.cols > 1:
            positions.append(layout.cols - 1)
        positions = sorted(set(positions))
        layout.aisle_count = len(positions)
        layout.aisle_positions = positions
        layout.podium_position = "back"
        layout.save(update_fields=["aisle_count", "aisle_positions", "podium_position"])


class Migration(migrations.Migration):

    dependencies = [
        ("seating", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="classroomlayout",
            name="aisle_count",
            field=models.PositiveSmallIntegerField(default=0, verbose_name="过道数"),
        ),
        migrations.AddField(
            model_name="classroomlayout",
            name="aisle_positions",
            field=models.JSONField(blank=True, default=list, verbose_name="过道位置"),
        ),
        migrations.AddField(
            model_name="seatplan",
            name="arrangement_priorities",
            field=models.JSONField(blank=True, default=list, verbose_name="智能排座优先级"),
        ),
        migrations.AddField(
            model_name="seatplan",
            name="last_rotated_at",
            field=models.DateField(blank=True, null=True, verbose_name="上次轮换日期"),
        ),
        migrations.AddField(
            model_name="seatplan",
            name="rotation_interval_months",
            field=models.PositiveSmallIntegerField(default=0, verbose_name="轮换周期(月)"),
        ),
        migrations.RunPython(migrate_layouts, migrations.RunPython.noop),
        migrations.RemoveField(model_name="classroomlayout", name="has_left_aisle"),
        migrations.RemoveField(model_name="classroomlayout", name="has_middle_aisle"),
        migrations.RemoveField(model_name="classroomlayout", name="has_right_aisle"),
        migrations.AlterField(
            model_name="classroomlayout",
            name="podium_position",
            field=models.CharField(choices=[("front", "前方"), ("back", "后方")], default="back", max_length=20, verbose_name="讲台位置"),
        ),
    ]
