from django import forms
from apps.seating.models import ClassroomLayout, SeatPlan


class ClassroomLayoutForm(forms.ModelForm):
    aisle_positions = forms.MultipleChoiceField(label="过道位置", required=False)

    class Meta:
        model = ClassroomLayout
        fields = [
            "name", "rows", "cols", "seats_per_desk",
            "aisle_count", "aisle_positions", "is_current",
        ]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "rows": forms.NumberInput(attrs={"class": "form-control", "min": "1", "max": "20"}),
            "cols": forms.NumberInput(attrs={"class": "form-control", "min": "1", "max": "20"}),
            "seats_per_desk": forms.NumberInput(attrs={"class": "form-control", "min": "1", "max": "4"}),
            "aisle_count": forms.NumberInput(attrs={"class": "form-control", "min": "0"}),
            "is_current": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        try:
            cols = int(self.data.get("cols") or self.instance.cols or 6)
        except (TypeError, ValueError):
            cols = 6
        self.fields["aisle_positions"].choices = [
            (str(position), f"第{position}-{position + 1}列中间")
            for position in range(1, max(1, cols))
        ]
        if not self.is_bound and not self.instance.pk:
            self.fields["aisle_count"].initial = 1
            self.fields["aisle_positions"].initial = [str(max(1, cols // 2))]

    def clean(self):
        cleaned_data = super().clean()
        cols = cleaned_data.get("cols") or 0
        rows = cleaned_data.get("rows") or 0
        seats_per_desk = cleaned_data.get("seats_per_desk") or 0
        aisle_count = cleaned_data.get("aisle_count") or 0
        positions = [int(position) for position in cleaned_data.get("aisle_positions", [])]
        if not 1 <= rows <= 20:
            self.add_error("rows", "排数必须为1至20。")
        if not 1 <= cols <= 20:
            self.add_error("cols", "座位列数必须为1至20。")
        if not 1 <= seats_per_desk <= 4:
            self.add_error("seats_per_desk", "每桌人数必须为1至4。")
        if aisle_count > cols:
            self.add_error("aisle_count", "过道数不能超过座位列数。")
        if aisle_count > max(0, cols - 1):
            self.add_error("aisle_count", "相邻座位列之间没有足够的过道位置。")
        if len(positions) != aisle_count:
            self.add_error("aisle_positions", "请选择与过道数相同数量的过道位置。")
        if len(set(positions)) != len(positions):
            self.add_error("aisle_positions", "过道位置不能重复。")
        cleaned_data["aisle_positions"] = positions
        return cleaned_data


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
