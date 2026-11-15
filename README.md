# 知途 · 本地自主学习桌面软件

知途是一款面向自主学习者的 Windows 桌面软件。你可以带着自己的课本来读、查、问、练，也可以只带一份题目，直接开始练习。每台电脑有自己的学习空间，首次打开即可使用，无需注册账号。

**当前测试版为 0.2.0-test.5。** [下载 Windows x64 安装包](https://github.com/NongZY/zhitu-desktop/releases/download/desktop-0.2.0-test.5/ZhiTu-0.2.0-test.5-Setup.exe) · [查看版本说明](https://github.com/NongZY/zhitu-desktop/releases/tag/desktop-0.2.0-test.5)

## 安装和首次使用

1. 下载上方的 `ZhiTu-0.2.0-test.5-Setup.exe`。如果已打开旧版知途，先关闭窗口，再运行安装包。
2. 安装后从开始菜单打开「知途（测试版）」。普通使用者无需安装 Python、Node.js 或 Docker。
3. 有学习资料时，从「我的课本 → 上传课本」开始。只有题目时，直接打开「我的题库 → 导入题目」。

支持 Windows 10 1809 或更新版本以及 Windows 11 的 x64 系统。安装器会检查 Microsoft Edge WebView2 Runtime 和 .NET Framework 4.6.2 或更高版本。若提示缺少组件，安装提示中的运行时后重新打开安装器。此版本已在开发机验证，尚未完成干净 Windows 系统的兼容性验收。[WebView2 官方下载](https://developer.microsoft.com/microsoft-edge/webview2/) · [.NET Framework 官方下载](https://dotnet.microsoft.com/download/dotnet-framework)

## 只带题目，怎么开始练习？

在「我的题库 → 导入题目」中保留默认的「独立题库」，选择 UTF-8 编码的 TXT 文件，或直接粘贴题目。每道题写明题型，答案单独一行，可附解析。可以先复制下面两题试用。

```text
【单选题】下列哪个数是偶数？
A. 3
B. 4
答案：B
解析：4 可以被 2 整除。

【判断题】0 是正数。
答案：错
```

核对预览后点「确认导入 → 练这组题 → 开始练习」。只有一道题也可以练。题库支持单选、多选、判断、填空和简答，每批最多 500 道，TXT 文件最大 2 MB。多选答案可以写成 `答案：A、C`。简答题填写参考答案，交卷后自行核对。已导入的重复题会跳过。也可以在导入时选择一本已有的教材，把练习题归到那本书。

## 带着教材学习

| 想做什么 | 在软件里怎么做 |
| --- | --- |
| 阅读和查找 | 在「我的课本」导入 PDF、DOCX、PPTX、TXT 或 Markdown（.md）。打开资料后按目录阅读、查找关键词，下次可继续上次的位置。 |
| 看清公式和图表 | 阅读 PDF 时查看原页，保留公式、插图和底色。纯扫描页可以阅读，文字搜索依赖可提取的文字。Word 和 PowerPoint 提供结构化阅读，复杂公式请对照原文件。 |
| 从教材中找答案 | 打开「问一问」，选择教材并输入问题。默认在本地查找相关片段，可根据引用回到原文核对。 |
| 依照教材补题 | 在「教材补题」选择教材与范围。离线规则覆盖部分数学内容，原题提取支持明确标注题目与答案的简答题。生成后先预览、修改，再把选中的题加入题库。 |
| 做练习和复习 | 在「做练习」选择题库或教材。教材练习可选章节、题型，并使用随机或自适应方式。交卷后到「学习记录」查看逐题答案与错题，到「学习进度」查看已有作答数据对应的知识点掌握情况。 |

## 可选的 AI 问答和补题

导入、阅读、原文查找、独立导题和本地练习均可离线使用。需要 AI 解释或配套练习时，在「设置 → AI 帮助」填写兼容 Chat Completions 的接口地址、模型名称和自己的 API 密钥，分别勾选问答或补题并保存。可先点「测试连接」验证配置。

AI 默认关闭。问答时选择 AI 解释、补题时确认发送后，程序才会将相应问题或必要的教材片段交给所配置的服务商，费用按服务商规则计算。生成的答案和题目可以对照原文核对。

## 数据保存、备份和换电脑

学习数据位于当前 Windows 账户的 `%LOCALAPPDATA%\ZhiTu\`。在「设置 → 备份和恢复」点「创建并导出备份」，可以将教材原件、题库和学习记录一起保存为 ZIP。

换电脑时先安装知途，在同一设置页选择备份 ZIP，核对教材、题目和练习数量，确认后重启。恢复会切换到备份中的学习空间，原空间会保留，两边的记录各自独立。AI 密钥保存在原电脑，换机后需重新填写。

## 从源码运行（开发者）

桌面窗口使用 pywebview 和 WebView2，界面使用 Vue 3 + TypeScript + Vite，FastAPI 本地服务使用 SQLite 保存学习数据。以下 PowerShell 命令从 Windows x64 的空目录开始。已验证的开发环境使用 Python 3.13、Node.js 24 和 npm。

```powershell
git clone https://github.com/NongZY/zhitu-desktop.git
cd zhitu-desktop
py -3.13 -m venv backend\.venv
.\backend\.venv\Scripts\python.exe -m pip install -e "./backend[desktop,dev,migration]"
npm.cmd --prefix frontend ci
npm.cmd --prefix frontend run build
.\backend\.venv\Scripts\python.exe run_desktop.py
```

使用 PyCharm 时，打开仓库根目录，完成首次依赖安装和界面构建，选择 `backend\.venv\Scripts\python.exe` 作为解释器，右键运行 `run_desktop.py`。源码版与安装版使用同一 Windows 账户的学习空间，开发测试请使用测试夹具。

**运行测试**

```powershell
npm.cmd --prefix frontend test
Push-Location backend
.\.venv\Scripts\python.exe -m pytest
Pop-Location
```

**构建 Windows 发行包**

```powershell
.\backend\.venv\Scripts\python.exe -m pip install -r packaging\requirements-build.txt
.\packaging\build.ps1
```

完成后打开 `dist\ZhiTu-0.2.0-test.5\知途.exe`。需要制作安装器时，安装 Inno Setup 6，再运行 `.\packaging\build.ps1 -InnoCompiler "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"`，按实际安装位置调整路径。安装器位于 `dist\installers\`。

## 反馈与开源许可

欢迎报告问题和提交改进。反馈时附上软件版本、Windows 版本、复现步骤和报错提示。若问题与文件有关，可附一小段自制示例。[提交 Issue](https://github.com/NongZY/zhitu-desktop/issues)

本仓库的原创代码（含已发布的 0.2.0-test.4 和 0.2.0-test.5）采用 **GNU Affero General Public License v3.0（AGPL-3.0-only）**。第三方组件遵循其各自的许可证。学习者导入的教材和题目，其权利归各自权利人。[项目许可证](LICENSE) · [PyMuPDF 许可说明](https://pymupdf.readthedocs.io/en/latest/about.html#license-and-copyright)
