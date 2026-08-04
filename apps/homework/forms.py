from django import forms
from apps.homework.models import HomeworkTask, HomeworkRecord, HomeworkStatus
from apps.students.models import Student


class HomeworkTaskForm(forms.ModelForm):
    class Meta:
        model = HomeworkTask
        fields = ["subject", "title", "content", "assigned_date", "due_date", "person_in_charge", "remarks", "needs_follow_up", "follow_up_date"]
        widgets = {
            "subject": forms.Select(attrs={"class": "form-select"}),
            "title": forms.TextInput(attrs={"class": "form-control"}),
            "content": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "assigned_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "due_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "person_in_charge": forms.TextInput(attrs={"class": "form-control"}),
            "remarks": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
            "needs_follow_up": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "follow_up_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
        }


class HomeworkRecordForm(forms.ModelForm):
    class Meta:
        model = HomeworkRecord
        fields = ["student", "status", "submission_date", "correction_deadline", "remark"]
        widgets = {
            "student": forms.Select(attrs={"class": "form-select"}),
            "status": forms.Select(attrs={"class": "form-select"}),
            "submission_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "correction_deadline": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "remark": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["student"].queryset = Student.objects.filter(is_deleted=False)


class HomeworkStatusForm(forms.ModelForm):
    class Meta:
        model = HomeworkStatus
        fields = ["name", "is_positive", "is_active", "sort_order"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "is_positive": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "sort_order": forms.NumberInput(attrs={"class": "form-control"}),
        }
