from django import forms
from apps.students.models import Student, Guardian


class StudentForm(forms.ModelForm):
    """学生表单"""
    class Meta:
        model = Student
        fields = [
            "school_class", "student_id", "name", "gender",
            "birth_date", "height", "vision", "seat_requirement",
            "class_position", "dormitory", "bed_number",
            "primary_contact", "primary_phone", "remarks", "sort_order",
        ]
        widgets = {
            "school_class": forms.Select(attrs={"class": "form-select"}),
            "student_id": forms.TextInput(attrs={"class": "form-control", "placeholder": "如：2026001"}),
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "gender": forms.Select(attrs={"class": "form-select"}),
            "birth_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "height": forms.NumberInput(attrs={"class": "form-control", "placeholder": "cm"}),
            "vision": forms.TextInput(attrs={"class": "form-control", "placeholder": "如：左眼5.0 右眼4.8"}),
            "seat_requirement": forms.TextInput(attrs={"class": "form-control", "placeholder": "如：需前排座位"}),
            "class_position": forms.TextInput(attrs={"class": "form-control"}),
            "dormitory": forms.TextInput(attrs={"class": "form-control"}),
            "bed_number": forms.TextInput(attrs={"class": "form-control"}),
            "primary_contact": forms.TextInput(attrs={"class": "form-control"}),
            "primary_phone": forms.TextInput(attrs={"class": "form-control", "placeholder": "13800138000"}),
            "remarks": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "sort_order": forms.NumberInput(attrs={"class": "form-control"}),
        }
        labels = {
            "school_class": "班级",
            "student_id": "学号",
            "name": "姓名",
            "gender": "性别",
            "birth_date": "出生日期",
            "height": "身高(cm)",
            "vision": "视力情况",
            "seat_requirement": "特殊座位需求",
            "class_position": "班级职务",
            "dormitory": "宿舍",
            "bed_number": "床位",
            "primary_contact": "主要联系人",
            "primary_phone": "主要联系电话",
            "remarks": "备注",
            "sort_order": "排序",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.initial.update({
                "class_position": self.instance.display_class_position,
                "dormitory": self.instance.display_dormitory,
                "bed_number": self.instance.display_bed_number,
                "primary_contact": self.instance.display_primary_contact,
                "primary_phone": self.instance.display_primary_phone,
            })
        for field_name in (
            "class_position", "dormitory", "bed_number",
            "primary_contact", "primary_phone",
        ):
            self.fields[field_name].disabled = True


class GuardianForm(forms.ModelForm):
    """家长联系方式表单"""
    class Meta:
        model = Guardian
        fields = [
            "father_name", "father_phone",
            "mother_name", "mother_phone",
            "other_guardian", "primary_contact",
            "home_address", "remarks",
        ]
        widgets = {
            "father_name": forms.TextInput(attrs={"class": "form-control"}),
            "father_phone": forms.TextInput(attrs={"class": "form-control", "placeholder": "13800138000"}),
            "mother_name": forms.TextInput(attrs={"class": "form-control"}),
            "mother_phone": forms.TextInput(attrs={"class": "form-control", "placeholder": "13800138000"}),
            "other_guardian": forms.TextInput(attrs={"class": "form-control"}),
            "primary_contact": forms.Select(attrs={"class": "form-select"}),
            "home_address": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
            "remarks": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
        }
        labels = {
            "father_name": "父亲姓名",
            "father_phone": "父亲电话",
            "mother_name": "母亲姓名",
            "mother_phone": "母亲电话",
            "other_guardian": "其他监护人",
            "primary_contact": "主要联系人",
            "home_address": "家庭地址",
            "remarks": "备注",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["primary_contact"] = forms.ChoiceField(
            choices=[
                ("", "请选择"),
                ("father", "父亲"),
                ("mother", "母亲"),
                ("other", "其他监护人"),
            ],
            widget=forms.Select(attrs={"class": "form-select"}),
            label="主要联系人",
            required=False,
        )
