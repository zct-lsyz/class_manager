from django import forms
from apps.dormitory.models import DormBuilding, DormRoom, DormAssignment, DormHygieneItem, DormHygieneCheck
from apps.students.models import Student


class MultipleImageInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleImageField(forms.ImageField):
    widget = MultipleImageInput

    def clean(self, data, initial=None):
        files = data if isinstance(data, (list, tuple)) else ([data] if data else [])
        return [super(MultipleImageField, self).clean(file_item, initial) for file_item in files]


class DormBuildingForm(forms.ModelForm):
    class Meta:
        model = DormBuilding
        fields = ["name", "floors", "sort_order"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "floors": forms.NumberInput(attrs={"class": "form-control"}),
            "sort_order": forms.NumberInput(attrs={"class": "form-control"}),
        }


class DormRoomForm(forms.ModelForm):
    class Meta:
        model = DormRoom
        fields = ["building", "room_number", "floor", "room_type", "bed_count", "monitor", "is_active", "remarks"]
        widgets = {
            "building": forms.Select(attrs={"class": "form-select"}),
            "room_number": forms.TextInput(attrs={"class": "form-control"}),
            "floor": forms.NumberInput(attrs={"class": "form-control"}),
            "room_type": forms.Select(attrs={"class": "form-select"}),
            "bed_count": forms.NumberInput(attrs={"class": "form-control"}),
            "monitor": forms.Select(attrs={"class": "form-select"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "remarks": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["monitor"].queryset = Student.objects.filter(is_deleted=False)
        self.fields["monitor"].required = False


class DormAssignmentForm(forms.ModelForm):
    class Meta:
        model = DormAssignment
        fields = ["student", "room", "bed", "is_current"]
        widgets = {
            "student": forms.Select(attrs={"class": "form-select"}),
            "room": forms.Select(attrs={"class": "form-select"}),
            "bed": forms.Select(attrs={"class": "form-select"}),
            "is_current": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }


class DormHygieneItemForm(forms.ModelForm):
    class Meta:
        model = DormHygieneItem
        fields = ["name", "full_score", "default_deduction", "default_severity", "is_active", "sort_order"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "full_score": forms.NumberInput(attrs={"class": "form-control"}),
            "default_deduction": forms.NumberInput(attrs={"class": "form-control"}),
            "default_severity": forms.Select(attrs={"class": "form-select"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "sort_order": forms.NumberInput(attrs={"class": "form-control"}),
        }


class DormHygieneCheckForm(forms.ModelForm):
    photos = MultipleImageField(
        label="现场照片（可多选）", required=False,
        widget=MultipleImageInput(attrs={"class": "form-control", "accept": "image/*"}),
    )

    class Meta:
        model = DormHygieneCheck
        fields = ["room", "date", "check_time", "inspector", "rectification", "rectification_deadline", "needs_follow_up", "follow_up_date", "remarks"]
        widgets = {
            "room": forms.Select(attrs={"class": "form-select"}),
            "date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "check_time": forms.TimeInput(attrs={"class": "form-control", "type": "time"}),
            "inspector": forms.TextInput(attrs={"class": "form-control"}),
            "rectification": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
            "rectification_deadline": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "needs_follow_up": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "follow_up_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "remarks": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
        }
