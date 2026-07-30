from django.urls import path
from django.contrib.auth.views import LogoutView
from apps.accounts import views

app_name = "accounts"

urlpatterns = [
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("settings/", views.account_settings, name="settings"),
    path("password-change/", views.password_change, name="password_change"),
    path("username-change/", views.username_change, name="username_change"),
]
