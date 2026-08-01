from django.contrib import admin

from apps.todos.models import TodoItem


@admin.register(TodoItem)
class TodoItemAdmin(admin.ModelAdmin):
    list_display = ("title", "school_class", "deadline", "is_completed", "created_at")
    list_filter = ("is_completed", "is_deleted", "school_class")
    search_fields = ("title",)
