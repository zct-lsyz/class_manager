from django import forms
from apps.attendance.models import AttendanceRecord
from apps.students.models import Student


class AttendanceForm(forms.ModelForm):
    """考勤表单：分值恒为正，用「加分/扣分」选择决定加还是扣。"""
    points_sign = forms.ChoiceField(
        label="加分/扣分", choices=[("add", "加分"), ("deduct", "扣分")],
        initial="deduct", widget=forms.Select(attrs={"class": "form-select"}),
    )

    class Meta:
        model = AttendanceRecord
        fields = ["student", "date", "period", "status", "points_sign", "points_deducted", "reason", "leave_proof", "needs_follow_up", "follow_up_date"]
        widgets = {
            "student": forms.Select(attrs={"class": "form-select"}),
            "date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "period": forms.Select(attrs={"class": "form-select"}),
            "status": forms.Select(attrs={"class": "form-select"}),
            "points_deducted": forms.NumberInput(attrs={"class": "form-control", "min": "0", "step": "1"}),
            "reason": forms.TextInput(attrs={"class": "form-control", "list": "attendance-reason-options"}),
            "leave_proof": forms.FileInput(attrs={"class": "form-control"}),
            "needs_follow_up": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "follow_up_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
        }
        labels = {
            "student": "学生",
            "date": "日期",
            "period": "时段",
            "status": "状态",
            "points_deducted": "分值（填正数）",
            "reason": "原因/备注",
            "leave_proof": "请假证明",
            "needs_follow_up": "需要跟进",
            "follow_up_date": "跟进日期",
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
        # 编辑时：分值恒为正显示，加减由选择决定
        if self.instance and self.instance.pk:
            self.fields["points_sign"].initial = "add" if self.instance.points_deducted >= 0 else "deduct"
            self.fields["points_deducted"].initial = abs(self.instance.points_deducted or 0)
