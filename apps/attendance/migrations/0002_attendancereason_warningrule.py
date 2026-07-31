from django.db import migrations, models
import django.db.models.deletion
import django.core.validators


class Migration(migrations.Migration):

    dependencies = [("attendance", "0001_initial"), ("classes", "0001_initial")]

    operations = [
        migrations.CreateModel(
            name="AttendanceReason",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="创建时间")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="更新时间")),
                ("name", models.CharField(max_length=100, verbose_name="原因项")),
                ("is_active", models.BooleanField(default=True, verbose_name="启用")),
                ("sort_order", models.IntegerField(default=0, verbose_name="排序")),
                ("school_class", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="attendance_reasons", to="classes.schoolclass", verbose_name="班级")),
            ],
            options={"verbose_name": "考勤原因项", "verbose_name_plural": "考勤原因项", "ordering": ["sort_order", "pk"], "unique_together": {("school_class", "name")}},
        ),
        migrations.CreateModel(
            name="WarningRule",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="创建时间")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="更新时间")),
                ("name", models.CharField(max_length=100, verbose_name="预警名称")),
                ("content", models.CharField(choices=[("attendance", "考勤管理"), ("discipline", "课堂纪律"), ("homework", "作业检查"), ("dormitory", "宿舍管理"), ("rewards", "奖惩管理"), ("duty", "值日管理")], max_length=30, verbose_name="内容")),
                ("unit", models.CharField(choices=[("count", "次"), ("points", "分")], default="count", max_length=10, verbose_name="单位")),
                ("threshold", models.PositiveSmallIntegerField(default=2, validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(20)], verbose_name="数量")),
                ("is_active", models.BooleanField(default=True, verbose_name="启用")),
                ("school_class", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="warning_rules", to="classes.schoolclass", verbose_name="班级")),
            ],
            options={"verbose_name": "预警条目", "verbose_name_plural": "预警条目", "ordering": ["pk"]},
        ),
    ]
