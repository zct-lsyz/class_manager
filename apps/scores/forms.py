from django import forms
from apps.scores.models import Exam, ExamSubject, Score, SupportPlan, SupportFollowUp
from apps.students.models import Student
from apps.classes.subjects import Subject


class ExamForm(forms.ModelForm):
    class Meta:
        model = Exam
        fields = ["name", "exam_type", "date", "total_score", "remarks"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "exam_type": forms.Select(attrs={"class": "form-select"}),
            "date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "total_score": forms.NumberInput(attrs={"class": "form-control"}),
            "remarks": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
        }


class ExamSubjectForm(forms.ModelForm):
    class Meta:
        model = ExamSubject
        fields = ["subject", "full_score", "sort_order"]
        widgets = {
            "subject": forms.Select(attrs={"class": "form-select"}),
            "full_score": forms.NumberInput(attrs={"class": "form-control"}),
            "sort_order": forms.NumberInput(attrs={"class": "form-control"}),
        }


class ScoreForm(forms.ModelForm):
    class Meta:
        model = Score
        fields = ["student", "score", "status", "remarks"]
        widgets = {
            "student": forms.Select(attrs={"class": "form-select"}),
            "score": forms.NumberInput(attrs={"class": "form-control", "step": "0.1"}),
            "status": forms.Select(attrs={"class": "form-select"}),
            "remarks": forms.TextInput(attrs={"class": "form-control"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["student"].queryset = Student.objects.filter(is_deleted=False)


class SupportPlanForm(forms.ModelForm):
    class Meta:
        model = SupportPlan
        fields = ["student", "plan_type", "subject", "target_score", "stage_goal", "is_active"]
        widgets = {
            "student": forms.Select(attrs={"class": "form-select"}),
            "plan_type": forms.Select(attrs={"class": "form-select"}),
            "subject": forms.Select(attrs={"class": "form-select"}),
            "target_score": forms.NumberInput(attrs={"class": "form-control"}),
            "stage_goal": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }
