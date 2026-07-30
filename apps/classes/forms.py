from django import forms
from apps.classes.models import SchoolClass, Semester


class SchoolClassForm(forms.ModelForm):
    """班级设置表单"""
    class Meta:
        model = SchoolClass
        fields = [
            "name", "grade", "school_name", "head_teacher",
            "classroom_name", "is_current", "sort_order",
        ]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control", "placeholder": "例如：高一(1)班"}),
            "grade": forms.TextInput(attrs={"class": "form-control", "placeholder": "例如：高一"}),
            "school_name": forms.TextInput(attrs={"class": "form-control"}),
            "head_teacher": forms.TextInput(attrs={"class": "form-control"}),
            "classroom_name": forms.TextInput(attrs={"class": "form-control", "placeholder": "例如：教学楼301"}),
            "is_current": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "sort_order": forms.NumberInput(attrs={"class": "form-control"}),
        }
        labels = {
            "name": "班级名称",
            "grade": "年级",
            "school_name": "学校名称",
            "head_teacher": "班主任",
            "classroom_name": "教室名称",
            "is_current": "设为当前班级",
            "sort_order": "排序",
        }


class SemesterForm(forms.ModelForm):
    """学期表单"""
    class Meta:
        model = Semester
        fields = [
            "school_class", "academic_year", "semester_type",
            "is_current", "start_date", "end_date",
        ]
        widgets = {
            "school_class": forms.Select(attrs={"class": "form-select"}),
            "academic_year": forms.TextInput(attrs={
                "class": "form-control", "placeholder": "例如：2026-2027",
            }),
            "semester_type": forms.Select(attrs={"class": "form-select"}),
            "is_current": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "start_date": forms.DateInput(attrs={
                "class": "form-control", "type": "date",
            }),
            "end_date": forms.DateInput(attrs={
                "class": "form-control", "type": "date",
            }),
        }
        labels = {
            "school_class": "班级",
            "academic_year": "学年",
            "semester_type": "学期",
            "is_current": "设为当前学期",
            "start_date": "开始日期",
            "end_date": "结束日期",
        }
