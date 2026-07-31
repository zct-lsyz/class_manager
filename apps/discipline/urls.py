from django.urls import path
from apps.discipline import views

app_name = "discipline"

urlpatterns = [
    # 课堂纪律
    path("classroom/", views.classroom_list, name="classroom_list"),
    path("classroom/create/", views.classroom_create, name="classroom_create"),
    path("classroom/<int:pk>/edit/", views.classroom_edit, name="classroom_edit"),
    path("classroom/<int:pk>/delete/", views.classroom_delete, name="classroom_delete"),
    path("classroom/<int:pk>/follow-up/", views.classroom_follow_up, name="classroom_follow_up"),
    path("classroom/items/", views.classroom_items, name="classroom_items"),
    # 宿舍纪律
    path("dorm/", views.dorm_list, name="dorm_list"),
    path("dorm/create/", views.dorm_create, name="dorm_create"),
    path("dorm/<int:pk>/edit/", views.dorm_edit, name="dorm_edit"),
    path("dorm/<int:pk>/delete/", views.dorm_delete, name="dorm_delete"),
    path("dorm/<int:pk>/follow-up/", views.dorm_follow_up, name="dorm_follow_up"),
    path("dorm/items/", views.dorm_items, name="dorm_items"),
    # 条目删除
    path("item/<int:pk>/delete/", views.item_delete, name="item_delete"),
]
