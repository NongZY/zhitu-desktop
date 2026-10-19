# Windows 桌面基础 D1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在独立应用版中交付可开发运行的 Windows 窗口，免登录进入本地空间，完成现有 PDF 导入、阅读续读和已有题目练习，退出后不遗留服务。

**Architecture:** 一个原生窗口宿主管理一个受控后端子进程；后端在导入现有配置及数据库模块之前安装专用桌面运行配置。每次启动的随机凭据由宿主持有，仅向本窗口发往精确本机来源的请求附加；前端仅取得非秘密的空间上下文，不存登录凭据。保留现有所有权和阅读协议，不在 D1 重构全部业务或实现后续 AI 补题。

**Tech Stack:** Windows 10/11 x64、Python 3.10+、FastAPI、SQLite、Vue 3／Vite、pywebview 6.2.1／EdgeChromium、Windows 文件锁和 Job Object。开发机现有 Python 为 `G:\python\python.exe`；使用应用版自己的虚拟环境，不复用网页版依赖目录。

**Spec:** [Windows 本地应用设计](../specs/2026-10-20-windows-local-app-design.md)、[教材内容驱动补题设计](../specs/2026-10-20-textbook-question-fill-design.md)。用户在 2026-10-20 指示“先跟着这版方案，构建另一端”，视为按当前设计推进应用版；本实施计划仍待审阅和执行方式选择。

## Global Constraints

- 只修改 `E:\项目\学习系统应用版`、分支 `desktop/windows-v0.2.0`；原网页版基线 `web-2026.10.20`／`bb7963256f3c79dff996013b6dde7976b63ea3ae` 不移动。
- “首个正式发布面向 Windows 10/11 x64”；D1 是开发运行里程碑，不是无开发环境可安装的正式发布，安装器与冻结包在 D4 验收。
- “运行数据默认位于 `%LOCALAPPDATA%\ZhiTu\`”；不能回退原项目数据目录、当前工作目录或临时解包目录。
- “桌面专用配置不读取当前工作目录 `.env`，不继承外部数据库、对象存储、Redis 或 AI 配置。”
- “不硬编码 `user_id=1`，不自动选择旧数据库第一名用户。”不移除所有权过滤，不提供匿名免密 Web 部署。
- “仅监听 `127.0.0.1`，由系统分配可用端口，不固定占用网页版 8081。”凭据不放 URL、持久化浏览器存储或日志。
- “只有当前请求对应的页面图片成功显示后，才作为新的阅读位置”；`document_revision` 和乐观并发语义保留。
- D1 不实现 DOCX/PPTX/TXT/MD、OCR、API 设置、迁移真实旧库、T1—T3 补题、答题草稿恢复或安装包；这些仍在整体方案，不因本批停止而取消。
- 教材补题只根据实际正文，不新增无教材题库／自由主题出题；现有模板不能被描述成新功能已完成。

## Review Focus

1. 恶意 `.env`／系统环境和提前导入配置：必须拒绝配置污染，不先连接旧数据库；由 Task 1 子进程测试覆盖。
2. 原生初始加载、重定向及外部链接：凭据不能发到相似域名、别的端口或外部页面；由 Task 2 请求测试及 Task 4 Windows 实测覆盖。
3. 页已显示但 1 秒防抖未到、保存正进行或发生 409 时关闭：不得虚报已保存或静默丢位置；由 Task 3 关闭协议测试覆盖。
4. 后端崩溃、僵住的解析线程、宿主强退和第二实例：锁、数据库和进程须可恢复，不结束其他 Python 程序；由 Task 4 生命周期测试覆盖。
5. 复制旧库但缺少本地空间清单、清单损坏、数据库只读或磁盘满：不得新建身份吞掉旧记录；由 Task 1 与 Task 5 失败验证覆盖。

## 范围与固定契约

- D1 开发版本标识为 `0.2.0-dev`，不创建 `0.2.0` 发布标签。
- 宿主启动服务等待上限 15 秒；关闭前端保存等待上限 8 秒；服务优雅退出等待 5 秒，超时仅终止本宿主创建并受 Job Object 管理的子进程。
- HTTP 凭据头固定 `X-ZhiTu-Desktop-Token`，每次启动用 `secrets.token_urlsafe(32)`，只在宿主内存、匿名管道和该次服务内存中存在。
- 原生启动桥仅返回 `DesktopContext`：`{schemaVersion: 1, mode: 'desktop', apiBaseUrl: string, version: '0.2.0-dev', workspace: {id: string, ownerId: number, label: '本地学习空间'}}`。`id` 是工作空间 UUID，`ownerId` 是稳定数据库整数 User ID；不得混用。
- 桌面所有 HTTP 路径，包括静态页面、健康检查和教材图像，校验凭据与精确 Host；有 Origin 时必须等于本次来源。无效请求拒绝；原 Swagger／注册／登录路由在桌面实例不挂载。
- 宿主 `request_sent` 事件只向本次精确 `http://127.0.0.1:{port}` 注入头，不向外部目标、相似域名、其他端口或带用户信息的 URL 注入。前端 Axios 不写 Authorization、不读取旧登录 localStorage；PDF 继续走 Axios → Blob → object URL。
- 原生导航只允许本次来源；用户主动点击的外部 HTTP(S) 链接交系统浏览器，不在特权窗口加载。文件、脚本和其他协议禁止。静态 CSP 阻止 CDN、远程字体、远程图片、对象和子框架，按现有 KaTeX 样式需求限定放行本地样式。

## 文件职责

| 文件 | 职责 |
| --- | --- |
| `backend/app/desktop/profile.py` | 不依赖业务模块的启动 DTO、目录和一次性进程内配置安装 |
| `backend/app/desktop/workspace.py` | 本地空间清单、稳定所有者和失败保护 |
| `backend/app/desktop/security.py` | 本次请求边界、桌面身份依赖与本机应用装配 |
| `backend/app/desktop/service.py` | 子进程匿名管道协议、端口、准备／退出状态 |
| `backend/app/desktop/host.py` | 子进程与 Job Object 生命周期、关闭握手 |
| `backend/app/desktop/instance.py` | 数据目录文件锁、窗口激活与过期元信息 |
| `backend/app/desktop/window.py` | EdgeChromium 窗口、请求头、导航和受限 JS 桥 |
| `frontend/src/runtime/desktop.ts` | 桥接就绪、上下文验证和初始化失败 |
| `frontend/src/runtime/close.ts` | 可等待的关闭守卫与唯一请求响应 |
| `frontend/src/stores/workspace.ts` | 当前稳定本地空间，不承载登录／密码 |
| `run_desktop.py` | 应用版唯一开发启动入口；不使用 `run_local.py` 启动桌面 |

保留现有 `engine/SessionLocal` 的每进程单例，避免 D1 无关重写所有路由、Celery 和测试。隔离前提必须落实：桌面服务是新进程，安装 profile 之前不允许导入 `app.config/database/models/main`，不在同一进程切换 Web／桌面模式或切换空间。以后如改成同进程多实例，必须先另行完成运行上下文注入重构。

---

### Task 1：独立配置、目录与稳定本地身份

**Files:** Create `backend/app/desktop/__init__.py`, `profile.py`, `workspace.py`, `backend/tests/desktop_helpers.py`, `backend/tests/test_desktop_profile.py`, `backend/tests/test_desktop_workspace.py`; Modify `backend/app/config.py`。

**Interfaces:**
- `DesktopProfile(data_dir: Path, origin: str, session_token: str)`：在 profile.py 定义的冻结 DTO，秘密字段禁止 repr；同文件定义供各模块使用的 Python `DesktopContext` TypedDict，字段与上方启动契约一致。`resolve_data_dir(local_app_data: Path) -> Path` 固定返回其 `ZhiTu` 子目录。
- `install_profile(profile: DesktopProfile) -> None`、`current_profile() -> DesktopProfile | None`：只可在业务配置导入前调用一次；提前导入或再次设置抛明确错误。
- `DesktopSettings` 继承字段但 `settings_customise_sources` 仅接受初始化来源，`get_settings()` 根据显式进程内 profile 选择它，默认 Web 路径不变。仅 `_env_file=None` 不足以隔离环境。
- workspace.py 定义冻结 `WorkspaceIdentity(workspace_id: str, owner_id: int, label: str)`；`ensure_workspace(db: Session, manifest_path: Path) -> WorkspaceIdentity` 返回该对象。
- 测试辅助接口位于 desktop_helpers.py：`probe_profile(local_app_data: Path, *, database_url: str, minio_endpoint: str, llm_api_key: str) -> dict[str, object]`，在新子进程设置恶意环境和不可解码的 `.env` 后读取实际配置、检查文件是否被尝试读取，返回下面断言所用四个字段；不得仅返回预设常量作为隔离证据。

- [ ] **Step 1：在应用版创建独立开发环境并写失败测试。** 用 `G:\python\python.exe -m venv backend\.venv`，在 backend 安装 `.[dev]`，前端执行 `npm ci`；不复制原 `.env`。测试辅助器用临时目录和新 Python 子进程验证配置，不复用已导入全局配置的 pytest 进程。

```python
def test_desktop_ignores_process_env_and_dotenv(tmp_path):
    report = probe_profile(tmp_path, database_url="postgresql://invalid/private",
                           minio_endpoint="invalid:9000", llm_api_key="sentinel")
    assert report["database_file"] == str(tmp_path / "ZhiTu" / "learning.db")
    assert report["storage_enabled"] is False
    assert report["llm_enabled"] is False
    assert report["dotenv_read"] is False
```

另测同源重启返回同一个 owner ID；预置合法空间清单绑定 owner 17，同时库中存在另一位 ID 1，证明既不硬编码也不取首用户。两个临时空间互不串数据；清单损坏、无清单但非空旧库、清单 owner 不匹配、只读目录／模拟磁盘满均拒绝启动且原记录不变。

- [ ] **Step 2：确认失败。** backend 执行 `.venv\Scripts\python.exe -m pytest tests/test_desktop_profile.py tests/test_desktop_workspace.py -q`；预期因缺少桌面模块／能力而失败，不接受依赖缺失作为业务失败证据。
- [ ] **Step 3：实现最小配置和身份。** 全部文件位于绝对数据目录；DesktopSettings 明确设置 `model_config.env_file=None`，再以仅初始化来源排除系统环境；关闭 MinIO、Redis、云端 AI。`workspace.json` 格式版本 1，先原子保存 UUID，再用 `workspace-{uuid}@local.invalid` 的内部唯一标记幂等创建／读取 User，事务完成后补齐实际 owner ID；禁止向前端展示内部邮箱或可登录密码。中断后按同 UUID 完成，不能创建第二个身份；旧库无清单时提示使用后续迁移入口，不自动选用户。
- [ ] **Step 4：验证。** 重跑上述测试及 `tests/test_auth.py tests/test_reading_progress.py tests/test_local_migration.py`；默认 Web 配置仍能使用隔离测试库，原迁移表范围不因新建桌面表改变（本任务不用新增业务表）。
- [ ] **Step 5：提交。** 只暂存本任务源码与测试，提交 `feat: isolate desktop configuration and local workspace`，不提交运行目录。

### Task 2：受限本机服务及匿名管道协议

**Files:** Create `backend/app/desktop/security.py`, `service.py`, `backend/tests/test_desktop_security.py`, `backend/tests/test_desktop_service.py`; Modify `backend/app/main.py`, `backend/app/services/import_dispatch.py`。

**Interfaces:**
- Consumes Task 1 `DesktopProfile`、`install_profile`、`ensure_workspace`。
- security.py 的 `create_desktop_app(profile: DesktopProfile) -> FastAPI` 调用 main.py 新增 `create_app(*, desktop_profile: DesktopProfile | None = None) -> FastAPI` 装配业务与静态服务；传入 profile 必须与进程内已安装实例一致。覆写整个 `get_current_user` 依赖为 `get_desktop_user(request: Request, db: Session = Depends(get_db)) -> User`，不能修改 Web OAuth2 默认行为；main.py 的默认 `app=create_app()` 留作原有测试入口，不作为桌面服务监听对象。
- `serve_from_parent_streams(reader: TextIO, writer: TextIO) -> int`：首行格式版本 1 的 JSON 只接收托管目录、静态目录、随机凭据；在 `127.0.0.1:0` 绑定并获得来源，再安装 profile，最后导入配置及业务模块。
- 服务在数据库／空间／路由就绪后仅向管道写 `ready` 帧（实际 origin 与空间身份，不回显密钥）；控制帧为 `status`、`shutdown`，响应按 request_id 对应。stdout 只供协议，诊断去脱敏 stderr。

- [ ] **Step 1：写失败测试。** 隔离子进程内测试：正确头可读取自己的空教材库；无头／错误头／旧启动头拒绝；正确头但伪造 Host、非本来源 Origin 也拒绝。桌面 auth／docs 路由返回 404，不可凭查询参数改变身份；默认 Web 仍无 JWT 返回 401。

```python
def test_desktop_token_applies_to_api_and_pdf(desktop_service):
    assert desktop_service.get("/api/v1/textbooks", authenticated=False).status_code == 403
    assert desktop_service.get("/api/v1/textbooks", authenticated=True).status_code == 200
    assert desktop_service.get("/api/v1/auth/me", authenticated=True).status_code == 404
```

同时验证静态入口、健康检查和原页图片均被保护，路径穿越不能读数据目录；两个不同 profile 的进程保持不同库，测试的信号 token 不出现在响应或捕获日志中。用户可见拒绝信息只说明本地连接无效，不提示登录。

- [ ] **Step 2：确认失败。** `.venv\Scripts\python.exe -m pytest tests/test_desktop_security.py tests/test_desktop_service.py -q`；应在缺失装配／安全契约处失败。
- [ ] **Step 3：实现。** 原 `main.app` 保留默认 Web 使用方式；提取必要应用装配函数，在有可信桌面 profile 时才停用 auth/docs 并加入 middleware／身份覆写。常量时间比较凭据，Host 是实际 loopback 端口，Origin 缺省仅在持有正确凭据时允许。服务状态报告处理中导入数；`shutdown` 先封住新任务提交、取消队列，再触发 Uvicorn 优雅退出。运行中的旧线程可能无法及时退出，不能把 `shutdown(wait=False)` 当终止证明，Task 4 宿主负责限定时间及硬退出。
- [ ] **Step 4：验证。** 服务只在启动完成后发送 ready，错误配置或静态文件缺失发送脱敏失败并退出；父管道 EOF 触发退出。无 Redis／MinIO／外部 DB 连接尝试，旧模式测试及所有权测试继续通过。
- [ ] **Step 5：提交。** `feat: add protected desktop service and launch protocol`；只暂存本任务文件。

### Task 3：前端免登录、本地空间与可靠关闭

**Files:** Create `frontend/src/runtime/desktop.ts`, `close.ts`, `frontend/src/stores/workspace.ts`, their `.test.ts` files, `frontend/src/views/DesktopStartupView.vue`, `frontend/src/views/DesktopShell.test.ts`; Modify `main.ts`, `env.d.ts`, `api/http.ts`, `router/index.ts`, `layouts/AppLayout.vue`, `views/DashboardView.vue`, `views/TextbookDetailView.vue`, `views/ExamTakeView.vue`, `styles/index.css`, `composables/useReadingProgress.ts` and affected tests。

**Interfaces:**
- `loadDesktopContext(timeoutMs = 15000): Promise<DesktopContext>` 等待 `pywebviewready` 后调用受限桥 `get_context()`；校验 schemaVersion、mode、同源 URL 和 ownerId，不把 URL/localStorage 当桌面身份来源。
- `useWorkspaceStore().initialize(context)` 保存非秘密空间；页面使用 `workspace.ownerId` 替代 `auth.user.id`。`api/http.ts` 以该上下文初始化 API 地址，原生宿主附加凭据，前端不接收 token。
- `registerCloseGuard(guard: () => Promise<'ready' | 'stay' | 'discard'>): () => void` 注册并返回撤销函数；`requestClose(requestId: string): Promise<void>` 串行等待守卫，通过桥 `respond_close(requestId, result)` 回应，只回应当前请求一次。
- `useReadingProgress(...).flush(): Promise<boolean>` 等待在途保存并发送最后一个已显示位置；未载入、有冲突或保存失败返回 false，不因 dispose 提前清空未保存位置。
- 以下测试的 `readyReadingAt(page: number)` 和 `lastConfirmedPage(): number` 定义在 useReadingProgress.test.ts，前者使用模拟 readingApi 建立已成功载入的 composable，后者读取模拟 API 最后确认的页，不能读本地预设值替代保存证据。

- [ ] **Step 1：写失败测试。** 第一次路由必须等桥就绪；localStorage 有旧 JWT、演示开关、伪造模式均无效。初始化无桥／失败显示“软件尚未连接本地服务”，不进入登录。页眉显示“本地学习空间”，无注册／登录／退出入口；401 显示本地连接恢复提示而非跳 `/auth`。

```ts
it('关闭时保存尚未到一秒的最后显示页', async () => {
  const reading = await readyReadingAt(15)
  reading.recordDisplayed(16, null)
  expect(await reading.flush()).toBe(true)
  expect(lastConfirmedPage()).toBe(16)
})
```

另测保存正在进行时新页排队、409、失败／超时返回 stay、失败后重试、旧迟到响应不会跨教材写入；从阅读页返回首页也要等 flush，避免守卫随卸载丢失最后位置。正文与弹窗继续经鉴权 Blob 加载并撤销 object URL。未提交练习关闭时明确提示当前作答尚未保存，用户可继续或放弃退出，不假装有草稿恢复。

- [ ] **Step 2：确认失败。** frontend 执行 `npm test -- src/runtime/desktop.test.ts src/runtime/close.test.ts src/views/DesktopShell.test.ts src/composables/useReadingProgress.test.ts`。
- [ ] **Step 3：实现。** 在安装 router 前完成上下文；应用版活动路由移除 `/auth`，旧 AuthView 源码无需为本批删尽。更新 Dashboard／阅读页身份与对应测试 mock，阅读页 `onBeforeRouteLeave` 复用可等待的 flush 和明确放弃选择。删除在线字体导入，改为系统字体；远程 cover_url 不自动加载，显示本地占位。关闭事件先 await flush，有未提交练习或保存失败则说明并停留；若用户明确放弃才回 discard，不能自动交卷或伪造保存成功。
- [ ] **Step 4：验证。** `npm test` 与 `npm run build`；保留全部原页图片显示、页码优先级、乐观并发、数学显示与五题型测试，不为绿色结果删除断言。构建文件不引用外部字体／CDN；API 请求中没有前端 Authorization 或持久 token 读写。
- [ ] **Step 5：提交。** `feat: bootstrap desktop workspace and flush reading before close`；不提交 node_modules 或 dist。

### Task 4：Windows 宿主、单实例、窗口与进程收尾

**Files:** Create `run_desktop.py`, `backend/app/desktop/host.py`, `instance.py`, `window.py`, `backend/tests/test_desktop_host.py`, `test_desktop_window.py`, `test_desktop_instance.py`; Modify `backend/pyproject.toml` only for optional `desktop = ["pywebview==6.2.1"]`。

**Interfaces:**
- host.py 定义 `DesktopHost.start(data_dir: Path, static_dir: Path) -> DesktopContext`、`stop(timeout_seconds: float = 5) -> ShutdownReport`，以及 `ShutdownReport(status: Literal['graceful', 'forced'], child_pid: int, exited: bool)`。host.context 暴露已就绪的非秘密上下文；`host.authorize_request(request) -> None` 调用本任务的来源校验／注入函数，秘密留在宿主私有内存。
- `InstanceLease.try_acquire(data_dir: Path) -> InstanceLease | ExistingInstance`：使用 Windows 文件锁，持有至宿主退出；无秘密的窗口元信息只用于激活。陈旧 PID／HWND 不可用于结束任意程序，失效锁由操作系统释放。
- `create_desktop_window(host, lease) -> Window`：启动 about:blank，安装原生请求与导航边界后加载服务来源；`DesktopBridge.get_context()` 只给当前可信来源，`respond_close(request_id, decision)` 处理 Task 3 结果。
- window.py 定义 `NativeRequest` Protocol（url: str、method: str、headers: MutableMapping[str, str]），`inject_desktop_header(request: NativeRequest, origin: str, token: str) -> None` 仅匹配精确来源；`handle_navigation(uri: str, is_user_initiated: bool) -> Literal['allow', 'external', 'deny']` 明确禁止特权窗口加载其他来源。下方测试的 `fake_request(url: str)` 在 test_desktop_window.py 创建符合此协议的内存对象。

- [ ] **Step 1：写失败测试。** 假窗口／假进程测试初始页面加载前即安装请求守卫；检查其他端口、相似域名、URL 用户信息与重定向目标没有秘密头。第二实例只激活窗口，不再启动服务或升级库；锁拥有者崩溃后可重启，旧元信息不误杀其他程序。

```python
def test_header_is_never_sent_to_another_origin():
    request = fake_request("http://127.0.0.1.evil.invalid:8081/")
    inject_desktop_header(request, "http://127.0.0.1:8081", "sentinel")
    assert "X-ZhiTu-Desktop-Token" not in request.headers
```

另测服务就绪超时、异常退出、关闭重复点击、前端 stay/discard/ready、在途导入关闭和永不退出的子进程；只终止本宿主句柄，宿主异常结束由 Job Object 清理子进程。8 秒无前端回应应提示而不是当成 ready。

- [ ] **Step 2：确认失败。** `.venv\Scripts\python.exe -m pytest tests/test_desktop_host.py tests/test_desktop_window.py tests/test_desktop_instance.py -q`。
- [ ] **Step 3：实现并安装本批 GUI 依赖。** 在应用版环境安装 `.[dev,desktop]`，主线程调用 `webview.start(gui='edgechromium', private_mode=True, debug=False)`；用官方 request_sent 接口注入本次请求头，以 WebView2 NavigationStarting 阻止外部加载，不依赖 before_load 充当可取消导航事件。保护安装失败则不加载业务页。禁止 file URL、远程调试和自动下载，配合 CSP。启动／关闭回调不阻塞 GUI 线程；closing 首次返回 false，异步等待前端结果，再检查导入状态并允许等待／取消退出。窗口退出先请求服务停，再在限时后清理自己的子进程。缺少运行时、DLL 或网页构建时给中文原生错误提示，不回退 IE、不自动运行 npm 或下载。
- [ ] **Step 4：验证。** 上述单元测试通过后，在本 Windows 真实窗口验证请求头、初始加载、Blob 原页、外部导航、二次双击和关闭；这类行为不能只由 mock 证明。不能安装 pywebview／WebView2 时据实标明 GUI 未验收，不擅自换成浏览器并称桌面版完成。
- [ ] **Step 5：提交。** `feat: manage Windows desktop window and service lifecycle`；不提交桌面运行日志、依赖或用户资料。

### Task 5：D1 集成证明与交付说明

**Files:** Create `backend/tests/test_desktop_flow.py`, `docs/DESKTOP_D1.md`; Modify `README.md`, `docs/VERSION_LINEAGE.md` with real evidence only。

**Interfaces:** 消费前四项全部契约；集成测试通过匿名管道启动真实临时服务，用该次凭据请求 API，使用临时合成 PDF 和题目，不读取原项目账户库或教材。

- [ ] **Step 1：先写失败的闭环测试。** 在空临时空间启动，创建并导入合成 PDF，确认解析完成；阅读第 15 页、保存后停服再启，owner ID 不变、token 变化且旧 token 失效，恢复第 15 页；创建已有支持的客观题并练习、交卷、查结果及错题。关闭后端口不可连接，第二次正常启动；模拟只读／磁盘满时不覆盖旧数据或显示假成功。
- [ ] **Step 2：运行并确认闭环未接通时失败。** `.venv\Scripts\python.exe -m pytest tests/test_desktop_flow.py -q`；不能用跳过所有测试作为完成证据。
- [ ] **Step 3：仅补齐前述契约内的集成接线。** 不趁验收添加设置、扫描 OCR、多格式或 AI 出题。独立运行命令是应用版环境的 `python run_desktop.py`；D1 仍需开发环境，不把此命令当作最终使用者操作要求。
- [ ] **Step 4：完整验证和人工记录。** 后端 `python -m pytest -q -rs -o addopts=''`；前端 `npm test`、`npm run build`；`git diff --check`。真实窗口完成导入、续读、现有练习、断外网、重复启动、保存失败和导入中关闭。对照整体设计 V1/V3/V4/V9/V11 的 D1 部分逐项给证据，V2 安装、V5 多格式、V10 AI、V12 真实迁移、V13 补题留给相应批次，不勾成完成。
- [ ] **Step 5：检查分支并提交。** 原网页版 baseline 分支及 tag 仍为 bb79632，原业务源码不变；应用版只提交本批源码／测试／说明。记录提交、环境、已运行与未运行验收、既有警告和下一批 D2/T1 边界，提交 `test: verify desktop foundation and document delivery limits`。

## 自审及执行交接

设计批准与计划执行是不同阶段：本次只写 D1 计划，没有安装依赖或修改业务代码。计划只覆盖桌面基础，不把整体方案承诺删掉；后续每批沿用源码隔离、数据保护和教材依据要求。

自审记录：D1 的配置／空间、服务访问、前端接线／保存、原生生命周期、实际闭环分别落在 Task 1—5；其余设计要求明确留在后续批次。已核对跨任务接口、DTO 字段和示例测试辅助函数的归属；五项 Review Focus 均有对应测试步骤。此记录是计划自审，不是运行验收。

执行时先确认计划和方式。建议 **Native／由当前代理直接实现**：配置、服务、原生窗口和前端关闭协议紧密相连，按顺序实现更便于统一接口；完成后由独立代理审查整批差异。也可选择逐任务实现并逐任务独立审查的 Subagent-driven 方式。不得把本次设计认可当作已审阅尚未呈现的实施计划。

技术依据：[pywebview API 与窗口事件](https://pywebview.flowrl.com/api/)、[安全说明](https://pywebview.flowrl.com/guide/security.html)、[WebView2 可取消导航事件](https://learn.microsoft.com/en-us/dotnet/api/microsoft.web.webview2.core.corewebview2.navigationstarting)、[pywebview 官方 PyPI 元数据](https://pypi.org/project/pywebview/)。6.2.1 是本轮核对的版本，尚未在新应用环境安装验证；不预先宣称 Python 3.13 原生依赖兼容性已通过。
