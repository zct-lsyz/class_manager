将小米开放平台下载的客户端 AAR 重命名为 `MiPush_SDK_Client.aar` 放在此目录，
并在构建环境设置 `XIAOMI_PUSH_APP_ID`、`XIAOMI_PUSH_APP_KEY`。
未放置 AAR 时，App 仍使用 AlarmManager 提供本地系统待办通知。
