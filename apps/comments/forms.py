from django import forms
from apps.comments.models import StudentComment, CommentTemplate
from apps.students.models import Student


class StudentCommentForm(forms.ModelForm):
    class Meta:
        model = StudentComment
        fields = ["student", "comment_type", "content", "status", "template"]
        widgets = {
            "student": forms.Select(attrs={"class": "form-select"}),
            "comment_type": forms.Select(attrs={"class": "form-select"}),
            "content": forms.Textarea(attrs={"class": "form-control", "rows": 5}),
            "status": forms.Select(attrs={"class": "form-select"}),
            "template": forms.Select(attrs={"class": "form-select"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["student"].queryset = Student.objects.filter(is_deleted=False)
        self.fields["template"].required = False


class CommentTemplateForm(forms.ModelForm):
    class Meta:
        model = CommentTemplate
        fields = ["title", "content", "category", "is_active"]
        widgets = {
            "title": forms.TextInput(attrs={"class": "form-control"}),
            "content": forms.Textarea(attrs={"class": "form-control", "rows": 4}),
            "category": forms.Select(attrs={"class": "form-select"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }
