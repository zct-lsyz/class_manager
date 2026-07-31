from django import forms
from apps.duty.models import DutyTask, DutyGroup, DutyRecord
from apps.students.models import Student


class DutyTaskForm(forms.ModelForm):
    class Meta:
        model = DutyTask
        fields = ["name", "area", "is_active", "sort_order"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "area": forms.TextInput(attrs={"class": "form-control"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "sort_order": forms.NumberInput(attrs={"class": "form-control"}),
        }


class DutyGroupForm(forms.ModelForm):
    members = forms.ModelMultipleChoiceField(
        queryset=Student.objects.filter(is_deleted=False),
        widget=forms.SelectMultiple(attrs={"class": "form-select", "size": 10}),
        label="成员",
        required=False,
    )
    tasks = forms.ModelMultipleChoiceField(
        queryset=DutyTask.objects.filter(is_active=True),
        widget=forms.SelectMultiple(attrs={"class": "form-select", "size": 5}),
        label="任务",
        required=False,
    )

    class Meta:
        model = DutyGroup
        fields = ["name", "leader", "week", "is_active"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "leader": forms.Select(attrs={"class": "form-select"}),
            "week": forms.NumberInput(attrs={"class": "form-control"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["leader"].queryset = Student.objects.filter(is_deleted=False)


class DutyRecordForm(forms.ModelForm):
    class Meta:
        model = DutyRecord
        fields = ["date", "student", "is_completed", "is_absent", "evaluation", "remark"]
        widgets = {
            "date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "student": forms.Select(attrs={"class": "form-select"}),
            "is_completed": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "is_absent": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "evaluation": forms.Select(attrs={"class": "form-select"}),
            "remark": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
        }
