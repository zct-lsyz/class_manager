from django import forms
from apps.rewards.models import RewardItem, RewardRecord, PointRecord
from apps.students.models import Student


class RewardItemForm(forms.ModelForm):
    class Meta:
        model = RewardItem
        fields = ["item_type", "name", "default_points", "category", "is_active", "sort_order"]
        widgets = {
            "item_type": forms.Select(attrs={"class": "form-select"}),
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "default_points": forms.NumberInput(attrs={"class": "form-control", "min": "0"}),
            "category": forms.TextInput(attrs={"class": "form-control"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "sort_order": forms.NumberInput(attrs={"class": "form-control"}),
        }
        labels = {
            "item_type": "条目类型",
            "name": "条目名称",
            "default_points": "默认分值（恒为正，按类型自动加/扣）",
        }


# 等级选项 → 适用于哪种奖惩类型（"" 表示两者通用）
LEVEL_TYPE = {
    "class": "reward",
    "school": "reward",
    "serious": "penalty",
    "moderate": "penalty",
    "mild": "penalty",
    "other": "",
}


class RewardItemSelect(forms.Select):
    """奖惩条目下拉：为每个选项附加 data-type（reward/penalty）与 data-points（默认分值）。"""

    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex, attrs)
        if value and getattr(value, "instance", None):
            item = value.instance
            option["attrs"]["data-type"] = item.item_type
            option["attrs"]["data-points"] = abs(item.default_points)
        return option


class RewardLevelSelect(forms.Select):
    """等级下拉：为每个选项附加 data-type，前端按奖惩类型过滤显示。"""

    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex, attrs)
        if value:
            option["attrs"]["data-type"] = LEVEL_TYPE.get(value, "")
        return option


class RewardRecordForm(forms.ModelForm):
    class Meta:
        model = RewardRecord
        fields = ["student", "date", "record_type", "item", "custom_name", "level", "points", "description", "certificate_photo", "needs_follow_up", "follow_up_date"]
        widgets = {
            "student": forms.Select(attrs={"class": "form-select"}),
            "date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "record_type": forms.Select(attrs={"class": "form-select"}),
            "item": RewardItemSelect(attrs={"class": "form-select"}),
            "custom_name": forms.TextInput(attrs={"class": "form-control"}),
            "level": RewardLevelSelect(attrs={"class": "form-select"}),
            "points": forms.NumberInput(attrs={"class": "form-control", "min": "0", "step": "1"}),
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
        self.fields["item"].label = "奖励条目（可选）"
        self.fields["custom_name"].label = "自定义名称"
        self.fields["points"].label = "分值（加分/扣分由奖惩类型决定）"
        self.fields["description"].label = "说明"
        self.fields["level"].label = "等级"
        # 编辑时：分值恒为正显示（加/扣由奖惩类型决定）
        if self.instance and self.instance.pk:
            self.fields["points"].initial = abs(self.instance.points)


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
            "item": RewardItemSelect(attrs={"class": "form-select"}),
            "custom_name": forms.TextInput(attrs={"class": "form-control"}),
            "level": RewardLevelSelect(attrs={"class": "form-select"}),
            "points": forms.NumberInput(attrs={"class": "form-control", "min": "0", "step": "1"}),
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
        self.fields["students"].queryset = students.order_by("name", "student_id")
        self.fields["item"].queryset = items
        self.fields["item"].required = False
        self.fields["item"].label = "奖励条目（可选）"
        self.fields["custom_name"].label = "自定义名称"
        self.fields["points"].label = "分值（加分/扣分由奖惩类型决定）"
        self.fields["description"].label = "说明"
        self.fields["level"].label = "等级"


class PointRecordForm(forms.ModelForm):
    """手工积分调整：分数恒为正，用「加减分」选择框决定加还是扣。"""
    points_sign = forms.ChoiceField(
        label="加减分", choices=[("add", "加分"), ("deduct", "扣分")],
        initial="add", widget=forms.Select(attrs={"class": "form-select"}),
    )

    class Meta:
        model = PointRecord
        fields = ["student", "date", "points", "reason", "source_type", "manual_reason"]
        widgets = {
            "student": forms.Select(attrs={"class": "form-select"}),
            "date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "points": forms.NumberInput(attrs={"class": "form-control", "min": "0", "step": "1"}),
            "reason": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
            "source_type": forms.Select(attrs={"class": "form-select"}),
            "manual_reason": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
        }
        labels = {
            "points": "分值（恒为正）",
            "source_type": "积分类型",
            "manual_reason": "调整说明",
        }
