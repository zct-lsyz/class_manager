from django.urls import path
from apps.dormitory import views

app_name = "dormitory"

urlpatterns = [
    path("", views.index, name="index"),
    path("building/create/", views.building_create, name="building_create"),
    path("building/<int:pk>/edit/", views.building_edit, name="building_edit"),
    path("building/<int:pk>/delete/", views.building_delete, name="building_delete"),
    path("room/create/", views.room_create, name="room_create"),
    path("room/<int:pk>/", views.room_detail, name="room_detail"),
    path("room/<int:pk>/edit/", views.room_edit, name="room_edit"),
    path("bed/<int:pk>/assign/", views.bed_assign, name="bed_assign"),
    path("bed/<int:pk>/monitor/", views.bed_set_monitor, name="bed_set_monitor"),
    path("hygiene/", views.hygiene, name="hygiene"),
    path("hygiene/items/", views.hygiene_items, name="hygiene_items"),
    path("hygiene/items/<int:pk>/delete/", views.hygiene_item_delete, name="hygiene_item_delete"),
    path("hygiene/items/<int:pk>/edit/", views.hygiene_item_edit, name="hygiene_item_edit"),
    path("hygiene/create/", views.hygiene_create, name="hygiene_create"),
    path("hygiene/<int:pk>/", views.hygiene_detail, name="hygiene_detail"),
    path("hygiene/<int:pk>/delete/", views.hygiene_delete, name="hygiene_delete"),
    path("discipline/", views.discipline, name="discipline"),
    path("discipline/create/", views.discipline_create, name="discipline_create"),
]
