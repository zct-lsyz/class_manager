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
        labels = {"name": "奖惩名称", "default_points": "默认积分"}


class RewardRecordForm(forms.ModelForm):
    class Meta:
        model = RewardRecord
        fields = ["student", "date", "record_type", "item", "custom_name", "level", "points", "description", "certificate_photo", "needs_follow_up", "follow_up_date"]
        widgets = {
            "student": forms.Select(attrs={"class": "form-select"}),
            "date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "record_type": forms.Select(attrs={"class": "form-select"}),
            "item": forms.Select(attrs={"class": "form-select"}),
            "custom_name": forms.TextInput(attrs={"class": "form-control"}),
            "level": forms.Select(attrs={"class": "form-select"}),
            "points": forms.NumberInput(attrs={"class": "form-control"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
            "certificate_photo": forms.FileInput(attrs={"class": "form-control"}),
            "needs_follow_up": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "follow_up_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
        }

    def __init__(self, *args, current_class=None, **kwargs):
        super().__init__(*args, **kwargs)
        students = Student.objects.filter(is_deleted=False)
        items = RewardItem.objects.filter(is_active=True)
        if current_class:
            students = students.filter(school_class=current_class)
            items = items.filter(school_class=current_class)
        self.fields["student"].queryset = students
        self.fields["item"].queryset = items
        self.fields["item"].required = False
        self.fields["item"].label = "奖惩条目（可选）"
        self.fields["custom_name"].label = "自定义奖惩名称"
        self.fields["points"].label = "积分变动"
        self.fields["description"].label = "奖惩说明"


class BatchRewardRecordForm(forms.ModelForm):
    students = forms.ModelMultipleChoiceField(
        label="学生（可多选）", queryset=Student.objects.none(),
        widget=forms.CheckboxSelectMultiple(attrs={"class": "list-unstyled"}),
    )

    class Meta:
        model = RewardRecord
        fields = ["date", "record_type", "item", "custom_name", "level", "points", "description", "certificate_photo", "needs_follow_up", "follow_up_date"]
        widgets = {
            "date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "record_type": forms.Select(attrs={"class": "form-select"}),
            "item": forms.Select(attrs={"class": "form-select"}),
            "custom_name": forms.TextInput(attrs={"class": "form-control"}),
            "level": forms.Select(attrs={"class": "form-select"}),
            "points": forms.NumberInput(attrs={"class": "form-control"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
            "certificate_photo": forms.FileInput(attrs={"class": "form-control"}),
            "needs_follow_up": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "follow_up_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
        }

    def __init__(self, *args, current_class=None, **kwargs):
        super().__init__(*args, **kwargs)
        students = Student.objects.filter(is_deleted=False)
        items = RewardItem.objects.filter(is_active=True)
        if current_class:
            students = students.filter(school_class=current_class)
            items = items.filter(school_class=current_class)
        self.fields["students"].queryset = students.order_by("student_id")
        self.fields["item"].queryset = items
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
