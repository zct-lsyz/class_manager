"""
一键清除指定用户及其全部关联数据
用法：python manage.py wipe_user --username admin
      python manage.py wipe_user --username admin --force  # 跳过确认
"""
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.models import User


class Command(BaseCommand):
    help = "删除指定用户及其全部关联数据"

    def add_arguments(self, parser):
        parser.add_argument("--username", required=True, help="要删除的用户名")
        parser.add_argument("--force", action="store_true", help="跳过确认")

    def handle(self, *args, **options):
        username = options["username"]
        force = options["force"]

        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            raise CommandError(f"用户「{username}」不存在。")

        if not force:
            self.stdout.write(self.style.WARNING(
                f"即将删除用户「{username}」(id={user.pk}, email={user.email}) 及其全部数据，不可撤销！"
            ))
            confirm = input("输入 yes 确认：")
            if confirm.strip().lower() != "yes":
                self.stdout.write("已取消。")
                return

        from apps.accounts.views import _cascade_delete_user_data
        self.stdout.write("正在清理关联数据...")
        _cascade_delete_user_data(user)

        user.delete()
        self.stdout.write(self.style.SUCCESS(f"用户「{username}」及全部关联数据已删除。"))
