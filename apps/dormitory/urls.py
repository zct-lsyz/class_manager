from django.urls import path
from apps.dormitory import views

app_name = "dormitory"

urlpatterns = [
    path("", views.index, name="index"),
    path("building/create/", views.building_create, name="building_create"),
    path("room/create/", views.room_create, name="room_create"),
    path("room/<int:pk>/", views.room_detail, name="room_detail"),
    path("bed/<int:pk>/assign/", views.bed_assign, name="bed_assign"),
    path("hygiene/", views.hygiene, name="hygiene"),
    path("hygiene/items/", views.hygiene_items, name="hygiene_items"),
    path("hygiene/items/<int:pk>/delete/", views.hygiene_item_delete, name="hygiene_item_delete"),
    path("hygiene/create/", views.hygiene_create, name="hygiene_create"),
    path("hygiene/<int:pk>/", views.hygiene_detail, name="hygiene_detail"),
    path("discipline/", views.discipline, name="discipline"),
    path("discipline/create/", views.discipline_create, name="discipline_create"),
]
