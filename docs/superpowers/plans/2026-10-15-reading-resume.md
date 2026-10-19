# 阅读位置保存与首页继续阅读 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 学习者阅读位置保存成功后，可以刷新、重新登录或重启服务，并从首页继续同一 PDF 页。

**Architecture:** 沿用 Vue 3、FastAPI 和当前数据库。新增独立的阅读进度记录；父页面统一决定目标页，阅读器报告实际显示成功的页，进度服务负责保存和冲突处理。首页单独请求继续阅读信息，不依赖图表成功加载。

**Tech Stack:** Python、SQLAlchemy、PyMuPDF、SQLite／PostgreSQL、Vue 3、TypeScript、pytest、Vitest。复用现有依赖，不安装新服务。

**Spec:** `E:/项目/学习系统/docs/superpowers/specs/2026-10-14-learner-foundation-design.md`，仅实施 A 批及全局约束。

状态：2026-10-19 A 批代码、自动测试、构建及核心浏览器流程已完成。实际验证及未实测边界见 `docs/READING_RESUME.md`；执行记录见 `.superpowers/sdd/2026-10-15-reading-resume/progress.md`。下列复选项保留原计划明细，不把未实测的 PostgreSQL／真实网络场景标为通过。

## Global Constraints

- 第一批开发仅做：**阅读位置保存＋首页继续阅读入口**。
- 没有教师、管理员、班级或身份等级。
- 页码统一为从 1 开始的 PDF 物理页码，明确与印刷页码的区别。
- 页面稳定后 1 秒内发起保存；保存成功才显示“已保存”。
- 阅读恢复不依赖大模型、Redis 或 Docker。
- 失败页不覆盖最后一次成功位置；旧响应不能覆盖新教材状态。
- 只在同一账户内恢复；更换原文件后不直接套用旧页。
- 不增加阅读计时，不把阅读页码推断成知识掌握度。
- 不实现作答草稿、问答面板、错题重做、应用端，不改变题库与评分。
- 不删除、覆盖或重新导入现有账户、教材和学习记录。

## Review Focus

- 图片接口成功但图片解码失败：不能保存该页。任务 3 验证 `img.load/error`。
- PDF 被替换且页数相同：旧进度失效；相同内容重新上传仍有效。任务 1、2 验证内容指纹。
- 快速切书、切账户及迟到请求：不得串书、串账户或覆盖新位置。任务 3 验证请求代次与清理。
- 两个标签页使用同一旧 revision 保存：只允许一个成功，另一个提示冲突。任务 2、3 验证条件更新。
- 旧 PostgreSQL 备份没有新增表：迁移工具不能因此拒绝合法旧备份，也不能放松对其他缺表的检查。任务 2 验证精确白名单。

## 执行前保护

项目已有大量未提交改动，不能从旧 HEAD 另建工作区后误以为包含这些改动。实施前按工作区技能检查可用附件；如果隔离，必须先安全带入当前代码基线，不能清理、回滚或夹带提交用户改动。

- [ ] 记录本次修改文件的初始内容与 Git 状态；用项目外独立备份目录或已核对的临时工作区保留副本，不能提交数据库、PDF、密钥。
- [ ] 测试只使用 `backend/tests/test.db` 或临时数据库；核对 pytest fixture 后再运行。测试不能使用 `data/local/learning.db`。
- [ ] 真正启动升级前，对正在使用的数据库做一致性备份；SQLite 使用备份接口或停机复制，不能漏掉 WAL。教材文件另外保存。
- [ ] 记录旧功能测试基线。失败若与本任务无关，单独报告，不扩大修复范围。

## Task 1: 原文件版本与阅读元数据

**Files:**
- Modify: `backend/app/services/pdf_reader.py`、`backend/app/services/storage.py`、`backend/app/api/textbooks.py`
- Test: `backend/tests/test_pdf_reader.py`
- Create test: `backend/tests/test_reader_metadata.py`

**Interfaces:**
- Produces: `ReaderMetadata(page_count: int, document_revision: str | None)`，不可变数据对象。
- Produces: `reader_metadata(file_path: str | None) -> ReaderMetadata`，位于 `pdf_reader.py`。
- Produces: `source_signature(uri: str) -> tuple`，位于 `storage.py`，仅内部缓存使用，不返回客户端。
- Preserves: `page_count(file_path: str | None) -> int`，委派元数据函数；搜索接口不改契约。
- Extends: `GET /textbooks/{id}/reader` 为 `{page_count, document_revision}`；无 PDF 返回 `{page_count: 0, document_revision: null}`。

- [ ] 写失败测试：`test_content_revision_and_cache` 验证 `same_bytes.document_revision == original.document_revision`、`changed_bytes.document_revision != original.document_revision`、重复读取未变化文件只执行一次内容散列与 PDF 打开。
- [ ] 写失败测试：`test_missing_encrypted_and_remote_pdf` 验证缺失文件 404、损坏／加密文件 422；模拟 MinIO 元数据变化能失效缓存；下载临时文件即使出错也被清理；不清理原文件。
- [ ] 运行：在 `backend` 下执行 `.\.venv\Scripts\python.exe -m pytest tests/test_reader_metadata.py -q`。预期新增符号／字段缺失导致失败。
- [ ] 实现 SHA-256 内容版本与页数缓存：本地失效键使用规范 URI、文件标识、大小、纳秒修改时间；MinIO 使用对象 key、version ID／ETag、大小及修改时间，只作为失效依据，不能把 ETag 当内容 SHA-256。使用进程内有界缓存，最多 128 项。先验证所有权再调用。读取前后失效键变化则丢弃结果并报告文件正在更新，不缓存错误结果。
- [ ] 更新旧 `test_pdf_reader.py` 中两个完整字典断言，明确核对新增字段，不删除原页数与隔离断言。
- [ ] 验证：`.\.venv\Scripts\python.exe -m pytest tests/test_reader_metadata.py tests/test_pdf_reader.py tests/test_textbook_page_image.py -q`，预期全部通过。
- [ ] 保存该任务差异；提交只包含本任务新增／修改的相关部分，不把既有未提交代码整文件夹带。

## Task 2: 持久化进度与首页接口

**Files:**
- Modify: `backend/app/models.py`、`backend/app/schemas.py`、`backend/app/main.py`、`backend/app/api/textbooks.py`、`backend/scripts/migrate_local_data.py`
- Create: `backend/app/services/schema_upgrades.py`、`backend/app/services/reading_progress.py`、`backend/app/api/reading.py`
- Create tests: `backend/tests/test_reading_progress.py`、`backend/tests/test_reading_upgrade.py`
- Modify test: `backend/tests/test_local_migration.py`

**Interfaces:**
- Consumes: Task 1 `reader_metadata`。
- Produces: `ReadingProgress` 表，字段 `id, user_id, textbook_id, page_number, chapter_id?, document_revision, revision, updated_at`；唯一 `(user_id, textbook_id)`，页码与 revision 为正整数；UTC 时间。
- Produces: `SchemaMigration` 表，字段 `version` 主键、`applied_at`；本次升级版本 `20261015_reading_progress_v1`。
- Produces: `apply_schema_upgrades(engine: Engine) -> None`，只增加本次表和版本记录；启动时先创建旧表，再调用版本化升级，不让通用 `create_all` 抢先创建本次两表。
- Produces: `GET /learning/reading-progress/{textbook_id}` 返回 `{progress: ReadingProgressRead | null}`。
- Produces: `PUT /learning/reading-progress/{textbook_id}` 接收 `{page_number, chapter_id?, document_revision, expected_revision}`，返回 `ReadingProgressRead`；首次 `expected_revision=0`，成功 revision 从 1 开始递增。
- Produces: `GET /learning/home` 返回 `{textbook_count, continue_reading: ContinueReading | null, reading_notice: string | null}`；`ContinueReading` 为进度字段加 `title, chapter_title?, page_count`。
- DTO `ReadingProgressRead` 为 `{textbook_id, page_number, chapter_id, document_revision, revision, updated_at}`；ID 使用整数，revision 不接受布尔值。
- `reading_progress.py` 导出 `get_progress(db, user_id, textbook_id)`、`save_progress(db, user_id, textbook_id, payload)`、`get_reading_home(db, user_id)`；路由仅负责依赖、响应与异常映射。

- [ ] 在临时 PDF 上写 API 测试，固定断言：首次 GET 为 null；保存第 15 页返回 revision 1；重新创建客户端仍读到 15；旧 revision 的第二次 PUT 返回 409 且原值不变；另一账户 GET／PUT 为 404。
- [ ] 写边界测试：`page_number` 为 0、负数、布尔值、非整数、超过页数时 422；其他书的章节 422；文件版本不匹配 409；删除目录不影响已存物理页；删除教材后进度不可查询。
- [ ] 写首页与升级测试：新账户 `{textbook_count: 0, continue_reading: null}`；按 `updated_at`、`id` 倒序选择有效记录；缺失／更新后的文件显示说明而非失效继续按钮；升级执行两遍只一条版本记录，旧表逐行值不变。
- [ ] 写旧备份测试：仅缺少 `reading_progress` 和 `schema_migrations` 可以补空表；缺少 `users`、多出未知表或任一旧表列不匹配仍拒绝；保留“目标数据库已存在禁止覆盖”的断言。
- [ ] 运行新增测试，确认因接口／模型缺失失败，不以语法错误或错误的数据库连接作为有效失败证据。
- [ ] 实现进度条件写入：更新使用 `WHERE revision=expected_revision`；创建竞争依靠唯一约束；冲突返回 `409 detail={code:'reading_conflict', message:'其他页面已更新阅读位置，请重新载入', current:...}`。文件替换冲突 code 为 `document_changed`。不自动覆盖，不使用客户端时间排序。
- [ ] 校验教材所有权后验证文件版本、页码和章节归属。`chapter_id` 仅作可失效提示，允许无章节；查询时忽略已删除章节。删除教材接口在同一事务内删除所属进度，不能依赖 SQLite 默认未启用的级联。
- [ ] 首页遇到原文件不可读时记录 `reading_notice` 并继续选择有效候选；按批次读取候选，不能逐页生成图片，也不能把文件故障变为 HTTP 500。所有新接口返回 `Cache-Control: private, no-store`。
- [ ] 升级与旧备份适配使用精确的新表白名单；新旧数据都不丢弃未知字段来“兼容”。只在单个维护／启动进程中执行建表升级，多进程部署先执行一次升级再启动其他进程。
- [ ] 验证：`.\.venv\Scripts\python.exe -m pytest tests/test_reading_progress.py tests/test_reading_upgrade.py tests/test_local_migration.py tests/test_personal_library_isolation.py -q`，预期全部通过。SQLite 并发测试使用两个独立连接。PostgreSQL 只能用专门测试库验证，未获得测试库时如实标记未实测，不连接用户数据库做破坏性测试。
- [ ] 保存并复核本任务差异，继续遵守执行前的提交隔离约束。

## Task 3: 统一页码导航与保存状态

**Files:**
- Modify: `frontend/src/api/types.ts`、`frontend/src/api/index.ts`、`frontend/src/components/OriginalPdfReader.vue`、`frontend/src/views/TextbookDetailView.vue`
- Create: `frontend/src/utils/readingNavigation.ts`、`frontend/src/composables/useReadingProgress.ts`
- Create tests: `frontend/src/utils/readingNavigation.test.ts`、`frontend/src/composables/useReadingProgress.test.ts`
- Modify tests: `frontend/src/components/OriginalPdfReader.test.ts`、`frontend/src/views/TextbookDetailView.test.ts`

**Interfaces:**
- Consumes: Task 1 `ReaderMetadata`、Task 2 进度接口及 DTO。
- Produces: `readingApi.getProgress(bookId, signal?)`、`saveProgress(bookId, payload, signal?)`、`home(signal?)`；复用现有 Axios，不新建网络层。
- Produces: `resolveReadingTarget({pageQuery, chapterQuery, chapters, pageCount, progress, documentRevision})` 返回 `{page: number | null, chapterId: number | null, notice: string | null}`；位于 `readingNavigation.ts`。查询参数类型为 `unknown`，章节树使用现有 `Chapter[]`，pageCount 为 0 时 page 为 null。
- Produces: `useReadingProgress({bookId: Ref<number>, userId: Ref<number | null>, documentRevision: Ref<string | null>})` 返回响应式 `progress, status, error`，以及 `load(): Promise<void>`、`recordDisplayed(page: number, chapterId: number | null): void`、`retry(): Promise<void>`、`reload(): Promise<ReadingProgressRead | null>`、`dispose(): void`；status 为 `idle|loading|saving|saved|error|conflict`。reload 返回服务器位置供父页显式导航。
- Reader 改为受控组件：props `{bookId, chapter?, page: number | null, pageCount: number, navigationId: number}`；emit `navigate(page: number)` 和 `page-displayed({page: number, navigationId: number})`。父页负责元数据与目标页；阅读器保留查找、缩放、背景、图片请求取消及资源回收。

- [ ] 写目标页纯函数测试：保存 15、URL page 9、chapter 起始 20 时 `page===9`；只有显式 chapter 时 `page===20`；无显式参数恢复 15；非法 URL 页提示后按有效章节／进度／默认页回退；pageCount 0 返回 null；章节重叠选择包含页的最深层。
- [ ] 写受控 reader 测试：HTTP 返回 Blob 后尚未触发 `img.load` 时无 `page-displayed`；触发当前图片 load 后仅发一次；旧图片事件／error 不发送；点击翻页和搜索只发 navigate，由测试父组件更新 prop 后才换页。
- [ ] 写进度 composable 测试：稳定显示后使用假时钟推进 1000ms 发起保存；未返回成功不显示 saved；保存期间翻页只合并最新待保存页，下一次使用上一响应 revision；409 停止自动覆盖；不同 bookId／userId 和 dispose 取消旧定时器与请求。
- [ ] 写父页测试：用可控 Promise 调换目录、元数据、进度的返回顺序，显式目标不变；元数据已可读但进度失败时仍可阅读，提示无法恢复／保存并提供重试；切书后的旧响应不能改新书。
- [ ] 运行：在 `frontend` 下执行 `& 'C:\Program Files\nodejs\npm.cmd' test -- src/utils/readingNavigation.test.ts src/composables/useReadingProgress.test.ts src/components/OriginalPdfReader.test.ts src/views/TextbookDetailView.test.ts`，确认新增行为尚未实现导致失败。
- [ ] 实现单一父级导航：route `page/chapter`、目录点击、翻页和搜索统一改变目标。主动点目录清除旧 page 参数；翻页替换当前 URL 页码而不生成大量浏览历史。保留浏览器前进后退行为，章节高亮变化本身不触发跳页。
- [ ] 父页递增 navigationId；只有当前教材、当前导航的成功图片事件进入 `recordDisplayed`。迟到事件与未加载图片不保存；没有进度版本时暂停保存直到 GET 成功，不能擅自以 revision 0 覆盖未知状态。
- [ ] 渲染“保存中／已保存／位置暂未保存，可重试”；冲突提供“重新载入位置”，不做隐式强制覆盖。旧文件版本提示“教材已更新，请重新选择阅读位置”，按正常导航显示新文件后由明确的新写入更新版本。
- [ ] 更新已有测试 mocks：增加 reader `document_revision`、readingApi 方法、响应式 route 和 router.replace；不删掉原有公式提示、原色、图片释放与章节跳转测试。
- [ ] 重跑该组测试并执行 npm `typecheck`，预期全部通过；保存本任务差异。

## Task 4: 首页继续阅读与整体验证

**Files:**
- Modify: `frontend/src/views/DashboardView.vue`、`frontend/src/views/LearningDetails.test.ts`、`docs/LOCAL_RUN.md`
- Create test: `frontend/src/views/DashboardResume.test.ts`

**Interfaces:**
- Consumes: `readingApi.home()` 与 `ContinueReading`。
- Produces: 首页继续阅读卡片，链接 `/textbooks/{id}?page={page_number}`；无可靠章节时不附 chapter。不添加继续作答的假入口。

- [ ] 写失败测试：返回教材页 15 时“继续阅读”跳正确 URL；零教材显示“上传第一本教材”；有教材无记录显示“打开教材”；home 失败仍可打开教材与练习；dashboard/mastery 失败不隐藏继续阅读卡片。
- [ ] 运行：`& 'C:\Program Files\nodejs\npm.cmd' test -- src/views/DashboardResume.test.ts`，确认缺少入口导致失败。
- [ ] 将继续阅读区放到统计之前；独立 loading/error/retry，不等待图表完成。复用 `/textbooks` 上传／教材入口，不新增上传页面。把“每天的有效学习时长”“学习 N 分钟”分别改为“每天的练习时长”“练习 N 分钟”。
- [ ] 更新 `LearningDetails.test.ts` 的 readingApi mock，保留近期练习与知识点详情跳转断言。
- [ ] 运行所有后端测试：在 `backend` 下 `.\.venv\Scripts\python.exe -m pytest -q`；运行前再次确认测试数据库，不启动实际用户库。记录通过／跳过数量及原因。
- [ ] 在 `frontend` 下依次运行 npm `test`、`typecheck`、`build`。每项退出码必须为 0；不能用构建通过替代交互测试。
- [ ] 在一致性备份之后，用测试数据或用户授权的账户完成 A1—A6 页面验收；至少验证保存 15、刷新、重登、服务重启、显式 page 9、断网提示及账户隔离。未做真实页面测试时不得声称已完成全部验收。
- [ ] 更新本地运行说明：新增数据位置、保存状态含义、文件更新行为、升级／回退方法；明确新功能不需要 Docker。仅记录真实执行结果，不提前写“全部通过”。
- [ ] 复核范围和最终差异。只交付 A 批；说明 B—E 尚未实施。不得自动部署、上传 GitHub或修改虚拟化设置。

## 覆盖检查与交付条件

- A1：任务 2 持久化与任务 4 实际恢复验收。
- A2、A3：任务 3 单一导航、查询参数及空目录／非法页测试。
- A4：任务 2 条件更新、任务 3 图片成功事件及状态测试。
- A5：任务 1 内容版本、任务 2 所有权、任务 3 文件变化提示。
- A6：任务 4 首页空状态与故障隔离；任务 2 失效文件过滤。
- 数据兼容：任务 2 升级及旧备份精确白名单；所有真实数据操作受执行前保护约束。

建议执行方式：主代理在当前会话串行完成四个任务，最后安排一次独立差异审查；任务间共享接口紧密，不让多个实现者同时编辑这些文件。独立审查不可用时明确报告，不冒充已审查。

若用户要求保留计划审批，审阅并选择执行方式后再实施。若用户明确要求跳过剩余审批并直接实施，则保留本计划作为检查清单，进入执行，不再重复询问同一范围。
