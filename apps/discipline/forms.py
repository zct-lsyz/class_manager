from django import forms
from apps.discipline.models import ConfigurableItem, ClassroomDisciplineRecord, DormDisciplineRecord
from apps.students.models import Student


class ItemPointsSelect(forms.Select):
    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex, attrs)
        if value and getattr(value, "instance", None):
            option["attrs"]["data-points"] = abs(value.instance.default_points)
            # default_points 为负表示加分条目
            option["attrs"]["data-add"] = "1" if value.instance.default_points < 0 else "0"
            option["attrs"]["data-severity"] = value.instance.default_severity
        return option


class ConfigurableItemForm(forms.ModelForm):
    class Meta:
        model = ConfigurableItem
        fields = ["name", "category", "default_severity", "default_points", "needs_follow_up", "is_active", "sort_order", "description"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "category": forms.TextInput(attrs={"class": "form-control"}),
            "default_severity": forms.Select(attrs={"class": "form-select"}),
            "default_points": forms.NumberInput(attrs={"class": "form-control"}),
            "needs_follow_up": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "sort_order": forms.NumberInput(attrs={"class": "form-control"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
        }


class ClassroomDisciplineForm(forms.ModelForm):
    """课堂纪律表单：分值恒为正，用「加分/扣分」选择决定加还是扣。"""
    points_sign = forms.ChoiceField(
        label="加分/扣分", choices=[("add", "加分"), ("deduct", "扣分")],
        initial="deduct", widget=forms.Select(attrs={"class": "form-select"}),
    )

    class Meta:
        model = ClassroomDisciplineRecord
        fields = [
            "student", "date", "time", "period", "subject",
            "item", "custom_content", "severity", "description",
            "action_taken", "points_sign", "points_deducted", "needs_follow_up",
            "follow_up_date", "follow_up_result", "remarks",
        ]
        widgets = {
            "student": forms.Select(attrs={"class": "form-select"}),
            "date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "time": forms.TimeInput(attrs={"class": "form-control", "type": "time"}),
            "period": forms.TextInput(attrs={"class": "form-control"}),
            "subject": forms.TextInput(attrs={"class": "form-control"}),
            "item": ItemPointsSelect(attrs={"class": "form-select"}),
            "custom_content": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
            "severity": forms.Select(attrs={"class": "form-select"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "action_taken": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
            "points_deducted": forms.NumberInput(attrs={"class": "form-control", "min": "0", "step": "1"}),
            "needs_follow_up": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "follow_up_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "follow_up_result": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
            "remarks": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
        }
        labels = {
            "points_deducted": "分值（填正数）",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["student"].queryset = Student.objects.filter(is_deleted=False)
        self.fields["item"].queryset = ConfigurableItem.objects.filter(
            module="classroom_discipline", is_active=True
        )
        self.fields["item"].required = False
        # 编辑时：分值恒为正显示，加减由选择决定（正=扣分、负=加分）
        if self.instance and self.instance.pk:
            self.fields["points_sign"].initial = "add" if self.instance.points_deducted < 0 else "deduct"
            self.fields["points_deducted"].initial = abs(self.instance.points_deducted or 0)


class DormDisciplineForm(forms.ModelForm):
    """宿舍纪律表单：分值恒为正，用「加分/扣分」选择决定加还是扣。"""
    points_sign = forms.ChoiceField(
        label="加分/扣分", choices=[("add", "加分"), ("deduct", "扣分")],
        initial="deduct", widget=forms.Select(attrs={"class": "form-select"}),
    )

    class Meta:
        model = DormDisciplineRecord
        fields = [
            "dorm_room", "student", "date", "time",
            "item", "custom_content", "severity", "description",
            "action_taken", "points_sign", "points_deducted", "needs_follow_up",
            "follow_up_date", "follow_up_result", "remarks",
        ]
        widgets = {
            "student": forms.Select(attrs={"class": "form-select"}),
            "dorm_room": forms.Select(attrs={"class": "form-select"}),
            "date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "time": forms.TimeInput(attrs={"class": "form-control", "type": "time"}),
            "item": ItemPointsSelect(attrs={"class": "form-select"}),
            "custom_content": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
            "severity": forms.Select(attrs={"class": "form-select"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "action_taken": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
            "points_deducted": forms.NumberInput(attrs={"class": "form-control", "min": "0", "step": "1"}),
            "needs_follow_up": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "follow_up_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "follow_up_result": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
            "remarks": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
        }
        labels = {
            "points_deducted": "分值（填正数）",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["student"].queryset = Student.objects.filter(is_deleted=False)
        self.fields["student"].label_from_instance = self._student_label
        self.fields["item"].queryset = ConfigurableItem.objects.filter(
            module="dorm_discipline", is_active=True
        )
        self.fields["item"].required = False
        # 编辑时：分值恒为正显示，加减由选择决定（正=扣分、负=加分）
        if self.instance and self.instance.pk:
            self.fields["points_sign"].initial = "add" if self.instance.points_deducted < 0 else "deduct"
            self.fields["points_deducted"].initial = abs(self.instance.points_deducted or 0)

    def _student_label(self, obj):
        """学生下拉选项显示床位号，如「张三（01号床）」。"""
        bed = obj.display_bed_number
        return f"{obj.name}（{bed}号床）" if bed else obj.name
