from django import forms

from apps.backups.models import StorageAlertRule


class StorageAlertRuleForm(forms.ModelForm):
    class Meta:
        model = StorageAlertRule
        fields = ["name", "category", "threshold_mb", "recipient_emails", "is_active"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "category": forms.Select(attrs={"class": "form-select"}),
            "threshold_mb": forms.NumberInput(attrs={"class": "form-control", "min": 1}),
            "recipient_emails": forms.Textarea(attrs={"class": "form-control", "rows": 2, "placeholder": "多个邮箱用逗号分隔"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }
