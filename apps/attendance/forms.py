from django import forms
from apps.attendance.models import AttendanceRecord
from apps.students.models import Student


class AttendanceForm(forms.ModelForm):
    class Meta:
        model = AttendanceRecord
        fields = ["student", "date", "period", "status", "points_deducted", "reason", "leave_proof"]
        widgets = {
            "student": forms.Select(attrs={"class": "form-select"}),
            "date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "period": forms.Select(attrs={"class": "form-select"}),
            "status": forms.Select(attrs={"class": "form-select"}),
            "points_deducted": forms.NumberInput(attrs={"class": "form-control"}),
            "reason": forms.TextInput(attrs={"class": "form-control", "list": "attendance-reason-options"}),
            "leave_proof": forms.FileInput(attrs={"class": "form-control"}),
        }
        labels = {
            "student": "学生",
            "date": "日期",
            "period": "时段",
            "status": "状态",
            "points_deducted": "加减分（正加负扣）",
            "reason": "原因/备注",
            "leave_proof": "请假证明",
        }

    def __init__(self, *args, current_class=None, **kwargs):
        super().__init__(*args, **kwargs)
        students = Student.objects.filter(is_deleted=False)
        if current_class:
            students = students.filter(school_class=current_class)
        self.fields["student"].queryset = students
        self.fields["status"].choices = [
            choice for choice in AttendanceRecord.STATUS_CHOICES if choice[0] != "normal"
        ]
        if not self.is_bound and not self.instance.pk:
            self.initial.setdefault("status", "late")
