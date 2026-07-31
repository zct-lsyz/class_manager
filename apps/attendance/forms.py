from django import forms
from apps.attendance.models import AttendanceRecord
from apps.students.models import Student


class AttendanceForm(forms.ModelForm):
    class Meta:
        model = AttendanceRecord
        fields = ["student", "date", "period", "status", "reason", "leave_proof"]
        widgets = {
            "student": forms.Select(attrs={"class": "form-select"}),
            "date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "period": forms.Select(attrs={"class": "form-select"}),
            "status": forms.Select(attrs={"class": "form-select"}),
            "reason": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
            "leave_proof": forms.FileInput(attrs={"class": "form-control"}),
        }
        labels = {
            "student": "学生",
            "date": "日期",
            "period": "时段",
            "status": "状态",
            "reason": "原因/备注",
            "leave_proof": "请假证明",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["student"].queryset = Student.objects.filter(is_deleted=False)
