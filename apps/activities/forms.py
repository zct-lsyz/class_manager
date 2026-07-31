from django import forms
from apps.activities.models import ClassMeeting, Activity, ClassCultureTask
from apps.students.models import Student


class ClassMeetingForm(forms.ModelForm):
    participants = forms.ModelMultipleChoiceField(
        queryset=Student.objects.filter(is_deleted=False),
        widget=forms.SelectMultiple(attrs={"class": "form-select", "size": 8}),
        label="参与学生", required=False,
    )

    class Meta:
        model = ClassMeeting
        fields = ["topic", "date", "goal", "agenda", "host", "materials", "summary", "follow_up"]
        widgets = {
            "topic": forms.TextInput(attrs={"class": "form-control"}),
            "date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "goal": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
            "agenda": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "host": forms.TextInput(attrs={"class": "form-control"}),
            "materials": forms.FileInput(attrs={"class": "form-control"}),
            "summary": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "follow_up": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
        }


class ActivityForm(forms.ModelForm):
    participants = forms.ModelMultipleChoiceField(
        queryset=Student.objects.filter(is_deleted=False),
        widget=forms.SelectMultiple(attrs={"class": "form-select", "size": 8}),
        label="报名学生", required=False,
    )

    class Meta:
        model = Activity
        fields = ["name", "activity_type", "date", "person_in_charge", "result", "award", "summary", "photo"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "activity_type": forms.Select(attrs={"class": "form-select"}),
            "date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "person_in_charge": forms.TextInput(attrs={"class": "form-control"}),
            "result": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
            "award": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
            "summary": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "photo": forms.FileInput(attrs={"class": "form-control"}),
        }


class ClassCultureTaskForm(forms.ModelForm):
    class Meta:
        model = ClassCultureTask
        fields = ["task_type", "title", "person_in_charge", "deadline", "is_completed", "summary"]
        widgets = {
            "task_type": forms.Select(attrs={"class": "form-select"}),
            "title": forms.TextInput(attrs={"class": "form-control"}),
            "person_in_charge": forms.TextInput(attrs={"class": "form-control"}),
            "deadline": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "is_completed": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "summary": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
        }
