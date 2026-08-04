# 班级教学管理 Android 客户端

这是原生 Android 客户端，不使用 `WebView`。界面使用 Java/AppCompat，业务数据通过
`https://120.27.231.112/api/v1/` 与 Django 通信；登录令牌使用 Android Keystore 加密保存。
Android 端不提供任何业务数据或备份文件的导入、导出、下载入口。原卷和匿名小分表只作为
一次 AI 分析的输入，不会批量写入网站业务数据。

## 本地构建

需要 JDK 17、Android SDK Platform 34 和 Build Tools 34。

```powershell
cd android
.\gradlew.bat testDebugUnitTest lintDebug assembleDebug
```

调试 APK 输出到 `app/build/outputs/apk/debug/app-debug.apk`。

## 小米服务器推送

1. 在小米开放平台创建 Android 应用，包名必须为 `com.classmanager.app`。
2. 下载小米推送客户端 AAR，保存为 `android/app/libs/MiPush_SDK_Client.aar`。
3. 构建 APK 前设置客户端凭据：

```powershell
$env:XIAOMI_PUSH_APP_ID="小米 AppId"
$env:XIAOMI_PUSH_APP_KEY="小米 AppKey"
.\gradlew.bat assembleRelease
```

4. 服务器 `.env` 配置以下内容后重建容器：

```dotenv
XIAOMI_PUSH_APP_ID=小米AppId
XIAOMI_PUSH_APP_KEY=小米AppKey
XIAOMI_PUSH_APP_SECRET=小米AppSecret
XIAOMI_PUSH_PACKAGE_NAME=com.classmanager.app
```

`AppSecret` 只能放在服务器，不能写入 APK。备份调度容器会同时扫描到期待办并调用小米推送；
客户端仍会安排 Android 本地闹钟，作为打开 App 后的本地兜底。

## 服务器更新

将本次 Django 代码同步到 `/opt/classroom-manager/app` 后，在服务器项目目录执行：

> 不要用本地版本覆盖服务器现有的 `.env`、`compose.yaml` 和 `nginx/default.conf`；服务器版本
> 已包含公网 IP 的 HTTPS 证书挂载与 80/443 配置。

```bash
sudo docker compose up -d --build
sudo docker compose exec web python manage.py showmigrations mobile_api
sudo docker compose ps
curl -i https://120.27.231.112/api/v1/dashboard/
```

最后一个请求返回 `401` 和 JSON 格式的“请先登录”即表示 HTTPS 与移动 API 路由正常。

## 安装后的系统设置

- 首次启动允许通知权限。
- 在“账户与安全”点击“允许精确待办提醒”。
- 小米手机建议允许应用自启动，并将省电策略设为“不限制”。服务器推送不依赖 App 常驻，
  但系统通知权限仍必须开启。
- 正式发布前需要在 Android Studio 中创建并妥善保管 release 签名文件；不要提交签名密码或
  `.jks` 文件。
