from django import forms
from apps.rewards.models import RewardItem, RewardRecord, PointRecord
from apps.students.models import Student


class RewardItemForm(forms.ModelForm):
    class Meta:
        model = RewardItem
        fields = ["name", "default_points", "category", "is_active", "sort_order"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "default_points": forms.NumberInput(attrs={"class": "form-control"}),
            "category": forms.TextInput(attrs={"class": "form-control"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "sort_order": forms.NumberInput(attrs={"class": "form-control"}),
        }


class RewardRecordForm(forms.ModelForm):
    class Meta:
        model = RewardRecord
        fields = ["student", "date", "item", "custom_name", "level", "points", "description", "certificate_photo"]
        widgets = {
            "student": forms.Select(attrs={"class": "form-select"}),
            "date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "item": forms.Select(attrs={"class": "form-select"}),
            "custom_name": forms.TextInput(attrs={"class": "form-control"}),
            "level": forms.Select(attrs={"class": "form-select"}),
            "points": forms.NumberInput(attrs={"class": "form-control"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
            "certificate_photo": forms.FileInput(attrs={"class": "form-control"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["student"].queryset = Student.objects.filter(is_deleted=False)
        self.fields["item"].queryset = RewardItem.objects.filter(is_active=True)
        self.fields["item"].required = False


class PointRecordForm(forms.ModelForm):
    class Meta:
        model = PointRecord
        fields = ["student", "date", "points", "reason", "source_type", "manual_reason"]
        widgets = {
            "student": forms.Select(attrs={"class": "form-select"}),
            "date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "points": forms.NumberInput(attrs={"class": "form-control"}),
            "reason": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
            "source_type": forms.Select(attrs={"class": "form-select"}),
            "manual_reason": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
        }
