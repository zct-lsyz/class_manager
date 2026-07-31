from django import forms
from apps.communications.models import StudentConversation, HomeSchoolContact, ConcernRecord
from apps.students.models import Student


class ConversationForm(forms.ModelForm):
    class Meta:
        model = StudentConversation
        fields = [
            "student", "date", "location", "reason", "main_content",
            "student_feedback", "follow_up_actions", "follow_up_date", "is_private",
        ]
        widgets = {
            "student": forms.Select(attrs={"class": "form-select"}),
            "date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "location": forms.TextInput(attrs={"class": "form-control"}),
            "reason": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
            "main_content": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "student_feedback": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
            "follow_up_actions": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
            "follow_up_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "is_private": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["student"].queryset = Student.objects.filter(is_deleted=False)


class HomeSchoolContactForm(forms.ModelForm):
    class Meta:
        model = HomeSchoolContact
        fields = [
            "student", "contact_date", "contact_person", "contact_method",
            "reason", "summary", "parent_feedback", "follow_up_items",
            "follow_up_date", "is_private",
        ]
        widgets = {
            "student": forms.Select(attrs={"class": "form-select"}),
            "contact_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "contact_person": forms.TextInput(attrs={"class": "form-control"}),
            "contact_method": forms.Select(attrs={"class": "form-select"}),
            "reason": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
            "summary": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "parent_feedback": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
            "follow_up_items": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
            "follow_up_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "is_private": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["student"].queryset = Student.objects.filter(is_deleted=False)


class ConcernRecordForm(forms.ModelForm):
    class Meta:
        model = ConcernRecord
        fields = [
            "student", "concern_type", "level", "observation",
            "conversation_notes", "action_plan", "next_follow_up",
            "status", "is_private",
        ]
        widgets = {
            "student": forms.Select(attrs={"class": "form-select"}),
            "concern_type": forms.Select(attrs={"class": "form-select"}),
            "level": forms.Select(attrs={"class": "form-select"}),
            "observation": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "conversation_notes": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "action_plan": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
            "next_follow_up": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "status": forms.Select(attrs={"class": "form-select"}),
            "is_private": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }
