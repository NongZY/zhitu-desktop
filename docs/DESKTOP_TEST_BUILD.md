# 知途 Windows 测试包 0.2.0-test.1

> 本文保留 D1 安装记录。2026-10-25 新生成的 `0.2.0-test.2` 多格式测试安装包及其验证结果见 [D2 测试版说明](DESKTOP_DOCUMENTS_D2.md)。旧桌面快捷方式需安装新版后才会更新。

制作日期：2026-10-21。本批按用户“制作安装包拿来测试”的要求，将已完成的 D1 功能提前打包供本机试用，不代表 D2/D3/T1—T3 或 D4 正式发布验收已完成。

## 直接使用

- 桌面快捷方式：`知途（测试版）`。
- 已安装程序：`%LOCALAPPDATA%\Programs\ZhiTuTest\知途.exe`。
- 安装包：`E:\项目\学习系统应用版\dist\installers\ZhiTu-0.2.0-test.1-Setup.exe`。
- 免安装目录：`E:\项目\学习系统应用版\dist\ZhiTu-0.2.0-test.1\`，双击其中的 `知途.exe`，整个目录必须一起保留。

安装包约 48.2 MiB，完整程序目录约 104.5 MiB。安装到当前用户，无需管理员权限，创建桌面和开始菜单入口；默认卸载保留 `%LOCALAPPDATA%\ZhiTu\` 学习数据。安装版与目录版使用同一学习空间，单实例限制继续生效。原网页版及其数据库不参与安装。

已包含 Python 和当前业务依赖、Vue 静态界面，不需要使用者安装 Python、Node、PyCharm、Docker 或数据库服务。使用系统现有的 WebView2 和 .NET Framework 4.6.2+；安装器缺少运行时时停止并提示微软下载来源，不静默下载。没有捆绑完整离线 WebView2 发行包，也未做干净 Windows 兼容验收。

## 建议先测试

1. 打开“我的课本”，导入 PDF。
2. 检查章节、原页插图与底色，阅读几页后关闭软件。
3. 再次打开，检查继续阅读的位置。
4. 使用已保存的题目练习，查看学习记录和错题。

当前问答是本地资料检索。其他文档格式、可选 AI API 设置、按教材正文智能补题仍待后续批次；题库为空时不会自动拥有完整配套题。

## 实现与验证

主窗口 `知途.exe` 使用窗口子系统；`ZhiTuService.exe` 使用控制台子系统保留匿名协议管道，由主窗口以隐藏方式启动。每次启动的凭据依旧只经匿名管道传递，后台服务仍归属 Windows Job Object。打包后定位相邻服务程序和自带界面，不查找源码 `.venv`，不使用安装目录保存学习数据。

打包工具：PyInstaller 6.22.3 / hooks-contrib 2026.9，Inno Setup 6.7.3。Inno 编译工具从官方链接下载，并确认 Authenticode 签名有效、发布者为 Pyrsys B.V.；工具仅用于构建，不纳入知途运行依赖。

验证结果：

- 3 项冻结启动回归先失败后通过，涵盖不依赖 `.venv`、运行相邻服务、程序缺失时停止。
- 对真实打包 EXE 清除 Python 环境路径，使用临时目录与合成 PDF，验证导入、目录、受保护原页、阅读进度、练习、错题、退出重启与持久化；并验证静态文件保护和登录接口缺失。
- 整体后端 162 项通过、4 项未提供真实教材跳过；前端 112 项通过；桌面改动 Ruff 检查通过。
- 目录包的真实原生窗口显示免登录学习首页，关闭后宿主及本地服务退出。
- 安装器实际安装成功，桌面快捷方式存在，已安装主程序与构建包 SHA-256 一致。
- 已从 `%LOCALAPPDATA%\Programs\ZhiTuTest\知途.exe` 实际打开安装后的窗口，显示“本地学习空间”和免登录学习总览；与目录包分别验证。

当前安装包 SHA-256：`3795E9C44632C52DD2EC6A2D73CC04A0E1574034D93D5557D90B0D93D6A7DBED`。主程序 SHA-256：`E69982A2DA804EB37BD8A4DF0375E3CC1FF03A148A9CFE84C51F092974B75804`。重新构建会产生新的校验值。

2026-10-23 交付复核：安装包、桌面快捷方式和已安装程序均存在，上述校验值未变化。直接针对已安装目录再次运行真实 EXE 的 PDF／练习／重启闭环及静态资源保护测试，2 项通过，数据使用临时目录，没有读写真实学习资料。

独立审查范围 `c2c4285..fc7584c`：无 Critical、无 Important，可交付本机测试。保留 1 项 Minor 到后续兼容验收：WebView2 检测应分别校验 HKLM/HKCU 的版本，避免机器级残留空值遮蔽用户级有效安装。本机机器级版本为 `155.0.4283.62`，实际安装已成功，不受该边界影响。

审查范围说明：多格式、AI 配置与教材补题仍属后续批次；离线 WebView2 分发、干净 Windows 兼容性和签名尚未验收；卸载数据保留目前依据安装脚本不删除数据目录，未在真实学习资料上执行卸载验证。上述限制不妨碍当前电脑试用，也不作正式发布承诺。

本机验证不等于已验证所有 Windows 配置。测试包未做代码签名，未创建正式发布标签，未上传远程仓库。首次独立包闭环测试直接通过，因为 D1 业务闭环已存在；启动分支改动有单独的先失败后通过测试。

## 重新制作

在已配置的应用版开发环境运行（使用者不需要执行）：

```powershell
backend\.venv\Scripts\python.exe -m pip install -r packaging\requirements-build.txt
./packaging/build.ps1 -InnoCompiler 'E:\项目\学习系统应用版\build\packaging-tools\inno\ISCC.exe'
```

验证真实包时，将 `ZHITU_TEST_BUNDLE` 设为打包目录，再运行后端 pytest。构建产物和工具位于已被 Git 忽略的 `dist/` 与 `build/`，源码提交不含程序包、教材、密钥或数据库。

技术依据：[PyInstaller 运行路径](https://pyinstaller.org/en/stable/runtime-information.html)、[pywebview 打包](https://pywebview.flowrl.com/guide/freezing.html)、[微软运行时分发说明](https://learn.microsoft.com/en-us/microsoft-edge/webview2/concepts/distribution)、[Inno Setup 官方下载](https://jrsoftware.org/isdl.php)。
