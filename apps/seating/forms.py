from django import forms
from apps.seating.models import ClassroomLayout, SeatPlan


class ClassroomLayoutForm(forms.ModelForm):
    class Meta:
        model = ClassroomLayout
        fields = [
            "name", "rows", "cols", "seats_per_desk",
            "has_middle_aisle", "has_left_aisle", "has_right_aisle",
            "podium_position", "is_current",
        ]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "rows": forms.NumberInput(attrs={"class": "form-control"}),
            "cols": forms.NumberInput(attrs={"class": "form-control"}),
            "seats_per_desk": forms.NumberInput(attrs={"class": "form-control"}),
            "has_middle_aisle": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "has_left_aisle": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "has_right_aisle": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "podium_position": forms.Select(attrs={"class": "form-select"}),
            "is_current": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }


class SeatPlanForm(forms.ModelForm):
    class Meta:
        model = SeatPlan
        fields = ["layout", "version", "reason"]
        widgets = {
            "layout": forms.Select(attrs={"class": "form-select"}),
            "version": forms.TextInput(attrs={"class": "form-control"}),
            "reason": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
        }
        labels = {
            "layout": "教室布局",
            "version": "版本号",
            "reason": "调整原因",
        }
