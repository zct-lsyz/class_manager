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
    # 注册 + 验证
    path("register/", views.register, name="register"),
    path("verify/", views.verify_email, name="verify_email"),
    path("verify-device/", views.verify_device, name="verify_device"),
    # 信任设备
    path("devices/<int:pk>/delete/", views.device_delete, name="device_delete"),
    # 注销账号
    path("delete/", views.delete_account, name="delete_account"),
]
