from django import forms
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm
from django.contrib.auth.models import User


class LoginForm(AuthenticationForm):
    """登录表单"""
    username = forms.CharField(
        label="用户名",
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": "请输入用户名",
            "autofocus": True,
        }),
    )
    password = forms.CharField(
        label="密码",
        widget=forms.PasswordInput(attrs={
            "class": "form-control",
            "placeholder": "请输入密码",
        }),
    )

    error_messages = {
        "invalid_login": "用户名或密码错误，请重试。",
        "inactive": "该账户已被禁用。",
    }


class CustomPasswordChangeForm(PasswordChangeForm):
    """修改密码表单"""
    old_password = forms.CharField(
        label="当前密码",
        widget=forms.PasswordInput(attrs={
            "class": "form-control",
            "placeholder": "请输入当前密码",
        }),
    )
    new_password1 = forms.CharField(
        label="新密码",
        widget=forms.PasswordInput(attrs={
            "class": "form-control",
            "placeholder": "请输入新密码",
        }),
    )
    new_password2 = forms.CharField(
        label="确认新密码",
        widget=forms.PasswordInput(attrs={
            "class": "form-control",
            "placeholder": "请再次输入新密码",
        }),
    )


class UsernameChangeForm(forms.ModelForm):
    """修改用户名表单"""
    class Meta:
        model = User
        fields = ["username"]
        widgets = {
            "username": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "请输入新用户名",
            }),
        }
        labels = {
            "username": "新用户名",
        }
