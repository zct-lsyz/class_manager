# 班级管理 Android 壳 App

一个最简化的 Android WebView 应用，将服务器上的「班级教学管理平台」以 App 形式呈现，并提供原生系统通知。

## 功能

- **WebView 容器**：加载 Django 服务器网页，所有功能与网页版一致
- **系统通知**：后台每 5 分钟轮询服务器的 `/dashboard/api/notifications/` 接口
  - 今日值日提醒
  - 学生预警提醒
  - 备份失败提醒
- **开机自启**：设备重启后自动恢复通知轮询

## 构建

需要安装 [Android Studio](https://developer.android.com/studio) 或 Android SDK + JDK 17。

```bash
cd android
./gradlew assembleRelease
# 输出 APK: app/build/outputs/apk/release/app-release.apk
```

Windows 下使用：

```bat
cd android
gradlew.bat assembleRelease
```

## 配置服务器地址

首次启动 App 会弹出「设置服务器地址」对话框。填入服务器 HTTPS 地址（如 `https://class.example.com/`）即可。

后续可在 `SharedPreferences`（key: `server_url`）中修改，或重新安装 App。

## 通知接口（服务端）

App 轮询的接口为：

```
GET /dashboard/api/notifications/
```

返回示例：

```json
{
  "ok": true,
  "timestamp": "2026-08-01",
  "has_current_class": true,
  "today_duty": {
    "roster_name": "第5周值日表",
    "summary": "扫地：张三、李四；擦黑板：王五"
  },
  "warning_count": 2,
  "warnings": ["张三(缺勤)", "李四(作业未交)"],
  "today_backup_alert": false
}
```

## 部署注意

- 服务端若启用了登录保护，此壳 App 的轮询请求需要携带登录 Cookie。
  生产环境建议将 `/dashboard/api/notifications/` 作为无需登录的只读接口，
  或在此 App 中实现登录状态同步（进阶改造）。
- 通知轮询是「拉模式」，非 WebPush，实时性约 5 分钟。
