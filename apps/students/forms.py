from django import forms
from apps.students.models import Student, Guardian


class StudentForm(forms.ModelForm):
    """学生表单"""
    class Meta:
        model = Student
        fields = [
            "school_class", "student_id", "name", "gender",
            "birth_date", "height", "vision", "seat_requirement",
            "class_position", "home_address",
            "is_league_member", "is_boarder",
            "dormitory", "bed_number",
            "primary_contact", "primary_phone", "secondary_contact",
            "secondary_phone", "remarks", "sort_order",
        ]
        widgets = {
            "school_class": forms.Select(attrs={"class": "form-select"}),
            "student_id": forms.TextInput(attrs={"class": "form-control", "placeholder": "19位数字", "inputmode": "numeric", "pattern": "[0-9]{19}", "maxlength": "19"}),
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "gender": forms.Select(attrs={"class": "form-select"}),
            "birth_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "height": forms.NumberInput(attrs={"class": "form-control", "placeholder": "cm", "min": "50", "max": "250", "step": "1"}),
            "vision": forms.TextInput(attrs={"class": "form-control", "placeholder": "如：左眼5.0 右眼4.8"}),
            "seat_requirement": forms.TextInput(attrs={"class": "form-control", "placeholder": "如：需前排座位"}),
            "class_position": forms.TextInput(attrs={"class": "form-control"}),
            "home_address": forms.TextInput(attrs={"class": "form-control", "placeholder": "如：XX省XX市XX区XX路XX号"}),
            "is_league_member": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "is_boarder": forms.CheckboxInput(attrs={"class": "form-check-input", "data-toggle": "dormitory"}),
            "dormitory": forms.TextInput(attrs={"class": "form-control"}),
            "bed_number": forms.TextInput(attrs={"class": "form-control"}),
            "primary_contact": forms.TextInput(attrs={"class": "form-control"}),
            "primary_phone": forms.TextInput(attrs={"class": "form-control", "placeholder": "请输入11位手机号", "inputmode": "numeric", "pattern": "[0-9]{11}", "maxlength": "11"}),
            "secondary_contact": forms.TextInput(attrs={"class": "form-control"}),
            "secondary_phone": forms.TextInput(attrs={"class": "form-control", "placeholder": "请输入11位手机号", "inputmode": "numeric", "pattern": "[0-9]{11}", "maxlength": "11"}),
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
            "home_address": "家庭住址",
            "is_league_member": "是否团员",
            "is_boarder": "是否住校",
            "dormitory": "宿舍",
            "bed_number": "床位",
            "primary_contact": "主要联系人",
            "primary_phone": "主要联系电话",
            "secondary_contact": "备用联系人",
            "secondary_phone": "备用联系电话",
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
        self.fields["class_position"].disabled = True
        # 宿舍/床位字段设为非必填，由是否住校控制
        self.fields["dormitory"].required = False
        self.fields["bed_number"].required = False
        self.fields["is_league_member"].required = False
        self.fields["is_boarder"].required = False


class GuardianForm(forms.ModelForm):
    """家长联系方式表单（联系人关系/电话 + 备用 + 家庭地址 + 备注）"""
    class Meta:
        model = Guardian
        fields = [
            "contact_relation", "contact_phone",
            "backup_relation", "backup_phone",
            "home_address", "remarks",
        ]
        widgets = {
            "contact_relation": forms.TextInput(attrs={"class": "form-control", "placeholder": "如：母亲"}),
            "contact_phone": forms.TextInput(attrs={"class": "form-control", "placeholder": "请输入11位手机号", "inputmode": "numeric", "pattern": "[0-9]{11}", "maxlength": "11"}),
            "backup_relation": forms.TextInput(attrs={"class": "form-control", "placeholder": "如：父亲"}),
            "backup_phone": forms.TextInput(attrs={"class": "form-control", "placeholder": "请输入11位手机号", "inputmode": "numeric", "pattern": "[0-9]{11}", "maxlength": "11"}),
            "home_address": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
            "remarks": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
        }
        labels = {
            "contact_relation": "联系人关系",
            "contact_phone": "联系人电话",
            "backup_relation": "备用联系人关系",
            "backup_phone": "备用联系人电话",
            "home_address": "家庭地址",
            "remarks": "备注",
        }
