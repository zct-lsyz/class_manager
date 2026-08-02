from django import forms

from apps.evaluation.models import EvaluationProject


class EvaluationProjectForm(forms.ModelForm):
    class Meta:
        model = EvaluationProject
        fields = ["name", "description", "cycle", "is_active"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
            "cycle": forms.Select(attrs={"class": "form-select"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }
        labels = {
            "name": "评选名称",
            "description": "项目描述",
            "cycle": "评选周期",
            "is_active": "启用",
        }
