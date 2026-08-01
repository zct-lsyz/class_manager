import re

from django import forms
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm
from django.contrib.auth.models import User


class RegisterForm(forms.ModelForm):
    """注册表单"""
    email = forms.EmailField(
        label="邮箱",
        required=True,
        widget=forms.EmailInput(attrs={
            "class": "form-control",
            "placeholder": "用于接收验证邮件",
        }),
    )
    password1 = forms.CharField(
        label="密码",
        widget=forms.PasswordInput(attrs={
            "class": "form-control",
            "placeholder": "至少6位，含数字",
        }),
    )
    password2 = forms.CharField(
        label="确认密码",
        widget=forms.PasswordInput(attrs={
            "class": "form-control",
            "placeholder": "再次输入密码",
        }),
    )

    class Meta:
        model = User
        fields = ["username", "email"]
        widgets = {
            "username": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "登录用户名",
            }),
        }
        labels = {
            "username": "用户名",
        }

    def clean_username(self):
        username = self.cleaned_data.get("username", "").strip()
        existing = User.objects.filter(username=username).first()
        if existing and existing.is_active:
            raise forms.ValidationError("该用户名已被使用。")
        # 未激活的账号允许覆盖（重新注册）
        return username

    def clean_email(self):
        email = self.cleaned_data.get("email", "").strip()
        existing = User.objects.filter(email=email).first()
        if existing and existing.is_active:
            raise forms.ValidationError("该邮箱已被注册。")
        # 未激活的账号允许覆盖
        return email

    def clean_password1(self):
        pwd = self.cleaned_data.get("password1", "")
        if len(pwd) < 6:
            raise forms.ValidationError("密码至少6位。")
        if not re.search(r"\d", pwd):
            raise forms.ValidationError("密码需包含数字。")
        return pwd

    def clean(self):
        data = super().clean()
        if data.get("password1") != data.get("password2"):
            raise forms.ValidationError({"password2": "两次密码不一致。"})
        return data


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
