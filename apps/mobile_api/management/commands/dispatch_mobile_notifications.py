from django.core.management.base import BaseCommand

from apps.mobile_api.push import dispatch_due_todos


class Command(BaseCommand):
    help = "向已注册的小米设备推送到期待办"

    def handle(self, *args, **options):
        result = dispatch_due_todos()
        self.stdout.write(self.style.SUCCESS(str(result)))
