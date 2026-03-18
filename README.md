# 网红筛选项目 README

这个项目的目标很简单：

1. 读取你上传的博主名单
2. 调用 Apify 抓取 TikTok / Instagram / YouTube 数据
3. 用 Python 规则做第一轮初筛
4. 用视觉模型做第二轮复核
5. 导出初筛表、测试表、最终复核表

如果你是第一次接手这个项目，先看这一份 README，再看字段字典和平台 PRD。

## Runtime Configuration

Phase 1 之后，本地运行的凭证来源按下面的规则固定：

- Apify：允许环境变量 `APIFY_TOKEN` / `APIFY_API_TOKEN`，也允许 `~/.apify/auth.json`
- 视觉模型：只允许环境变量，不允许从源码测试脚本或硬编码默认值回退
- 前端 dev helper 不负责注入敏感变量，凭证只由后端进程读取
- 如果同时配置了 `VISION_QUAN2GO_API_KEY`、`VISION_LEMONAPI_API_KEY` 和/或 `OPENAI_API_KEY`，视觉复核会把 `quan2go`、`lemonapi`、`auto-code` 作为 provider 池使用；当前优先 provider 失败时会立刻切到下一套，并把新的优先级记录到 `data/vision_provider_state.json`
- `quan2go` / `auto-code` 走 OpenAI `responses` 兼容路径；`lemonapi` 当前走 `chat/completions` 兼容路径，默认模型可通过 `VISION_LEMONAPI_MODEL` 单独指定

推荐把本地需要的变量放进你自己的 shell 配置或未提交的 `.env` 载入流程，并参考根目录的 `.env.example`。
当前仓库也支持后端在启动时自动读取根目录未提交的 `.env.local`；如果你想要一个固定填写地址，直接编辑根目录 `.env.local` 即可。
如果你有多个 Apify token，可以把主 token 写在 `APIFY_TOKEN`，其余备份 token 用英文逗号写进 `APIFY_BACKUP_TOKENS`。当后端检测到重试/轮换时，会在这个 env token 池里切换，不再被单个环境变量固定住。

本地访问默认值也在 Phase 1 固定下来：

- `BACKEND_ALLOWED_ORIGINS` 默认是 `http://127.0.0.1:5173,http://localhost:5173`
- `BACKEND_BIND_HOST` 默认是 `127.0.0.1`
- `BACKEND_PORT` 默认是 `5001`
- 不使用 wildcard origin，也不默认开放局域网访问
- 需要局域网调试时，再显式设置例如 `BACKEND_BIND_HOST=0.0.0.0`

如果你想单独 smoke test `lemonapi` 图像理解，可用：

- `VISION_SMOKE_API_KEY=...`
- `VISION_SMOKE_BASE_URL=https://new.lemonapi.site/v1`
- `VISION_SMOKE_MODEL=[L]gemini-3.1-pro-preview`
- `VISION_SMOKE_API_STYLE=chat_completions`
- 然后运行 `backend/.venv/bin/python scripts/test_openai_vision.py`

## Local Smoke Start

没有真实 provider 密钥时，也应该能完成基础启动 smoke：

1. 启动前端：`cd frontend && npm run dev -- --host 127.0.0.1 --port 5173`
2. 启动后端：`backend/.venv/bin/python backend/app.py`
3. 用基础接口确认服务可达：`curl http://127.0.0.1:5001/api/health`

业务功能 ready 的标准不同：只有当 Apify 和视觉模型环境变量配置完整后，采集和视觉复核才应被视为可用。

补充：`frontend/dev.mjs` 现在会优先选择能成功导入 `openai` / `pydantic_core` 的 backend Python。
如果你要强制指定解释器，可以显式设置 `BACKEND_PYTHON=/absolute/path/to/python`。

## 先看这 4 个文件

- `backend/app.py`
- `scripts/data_cleaner.py`
- `docs/field_dictionary.md`
- `config/field_mapping.json`

它们分别负责：

- `backend/app.py`：上传、采集任务、视觉复核、导出接口
- `scripts/data_cleaner.py`：第一轮规则初筛
- `docs/field_dictionary.md`：字段总览，告诉你哪些字段存在、哪些正在被用
- `config/field_mapping.json`：机器可读字段字典，文档由它生成

## 项目结构

### 前端

- `frontend/src/App.jsx`

前端负责：

- 上传 Excel
- 选择平台和采集参数
- 轮询采集任务 / 视觉复核任务
- 展示初筛结果、九宫格日志、已完成复核结果
- 触发各种导出按钮

## Phase 04.1 主屏合同

Phase 04.1 之后，主屏不再允许继续按 append-only 方式把所有后续模块往下堆。

- `运行工作台` 只保留 intake / configuration、启动按钮、任务进度，以及结果入口
- `结果工作台` 才承接 post-run 的 review / export surface
- `RuleSpec Compiler` 不再占据默认主流程，而是一个明确的 `secondary tool`

当前主屏的边界固定为：

1. 默认落点是 `运行工作台`
2. 采集配置、上传、启动和任务进度都留在 `运行工作台`
3. 采集一旦有结果，会出现 `进入结果工作台` 的明确入口
4. `结果工作台` 内部再拆成 `概览`、`博主卡片`、`视觉复核`、`导出交接`
5. `RuleSpec Compiler` 只有点击 `打开 RuleSpec 工具` 后才展开，不再和默认 operator flow 并列

## Phase 04.1 验证清单

每次调整主屏信息架构后，至少手动确认下面这些点：

1. 默认打开时停在 `运行工作台`，而不是直接落到 review/export 区。
2. `进入结果工作台` 只在已有结果时出现，并且点击后进入 `结果工作台`。
3. `RuleSpec Compiler` 不会默认展开，必须通过 `打开 RuleSpec 工具` 才能看到。
4. `概览` 只保留摘要指标和一个 Next Action，不再同时混入视觉复核 desk、导出墙和 `Run Snapshot`。
5. `视觉复核` tab 独占 visual review mode、Visual Review Desk、历史队列和启动 CTA。
6. `导出交接` tab 独占导出动作，并在导出动作下面展示 `Run Snapshot`。
7. 提交前执行 `cd frontend && npm run lint`。
8. 提交前执行 `cd frontend && npm run build`。

### 后端

- `backend/app.py`

后端负责：

- 解析上传文件
- 保存上传元数据
- 发起 Apify 采集
- 调用初筛逻辑
- 调用视觉模型
- 生成导出文件

### 初筛规则

- `scripts/data_cleaner.py`

这里是第一轮规则审核的真实入口。

当前主链路：

- TikTok：`check_tiktok_tapo`
- Instagram：`check_instagram_custom`
- YouTube：`check_youtube`

## 端到端链路

### 1. 上传 Excel

前端把文件发到：

- `POST /api/upload`

Phase 2 之后，这一步默认只认一套固定模板，也就是 canonical creator workbook。

最少必填列：

- `Platform`
- `@username`

当前批准的业务列包括：

- `nickname`
- `Description`
- `Region`
- `Language`
- `Followers`
- `Avg. Views`
- `Avg. Likes`
- `Avg. Comments`
- `Avg. Collects`
- `Tags`
- `Email`

同一个 workbook 现在也可以包含多个 sheet，例如 `YouTube` / `TikTok` / `Instagram` 分 tab 填写；后端会把所有非空 sheet 合并后再按同一套固定列校验。每个 sheet 都必须使用这套 canonical 表头，不能有的 tab 用旧模板、有的 tab 用新模板。

后端现在不会再把“猜 URL 列 / 猜平台”当主路径。上传时会直接做固定合同校验：

1. 检查是否存在 `Platform` 和 `@username`
2. 检查 `Platform` 是否是 `Instagram` / `TikTok` / `YouTube`
3. 用 `Platform + @username` 做确定性路由
4. 把上传表里的业务字段归一化保存成平台级 upload metadata

说明：

- `username` / `handle` 会被当作 `@username` 的薄兼容别名
- 如果表里额外带了 `URL`，后端会一起存档；没有也可以上传
- 缺列、平台值不合法、账号标识为空时，会直接返回可读错误，不再静默猜测

保存位置：

- `data/tiktok/tiktok_upload_metadata.json`
- `data/instagram/instagram_upload_metadata.json`
- `data/youtube/youtube_upload_metadata.json`

这些上传元数据不是摆设，后面初筛会真正使用。

例如 Instagram 当前主链路会优先读上传表里的：

- `Region`
- `Language`

### upload metadata 的 source of truth

- canonical source of truth 是各平台的 `data/<platform>/<platform>_upload_metadata.json`
- `profile_reviews` 落盘前会把对应 identifier 的 upload metadata merge 进去，但这份 merge 后的 review JSON 仍然不是新的 truth source
- 后端在读取 review、生成 `test-info`、生成 `prescreen-review` / `image-review` / `final-review` 导出时，都会再次按 identifier 从 `*_upload_metadata.json` 重新 merge，避免前端缓存或旧 review 文件里的 metadata 漂移
- 如果 review 里缺少 `profile_url`，后端允许用 canonical upload metadata 里的 `url` 做确定性回填
- 结论：下游路径可以消费 `profile_reviews.upload_metadata`，但不能把它当成可以独立演化的一份副本

## 2. 发起采集任务

前端点击“开始采集”后，走：

- `POST /api/jobs/scrape`

后端根据平台进入不同采集链路：

- TikTok：Apify REST 分批采集
- Instagram：Apify REST 分批采集
- YouTube：少量账号走 REST，数量大时走批次模式

采集前会先查缓存历史：

- 如果没勾选 `forceRefresh`
- 且该账号最近已抓过
- 就会跳过重新抓取，直接复用最近结果
- 如果当前原始结果文件为空，但平台目录下仍有最近一次非空快照，系统会回退到那份最近可用结果，而不是直接把页面打成空白

`forceRefresh` 的语义也固定下来：

- 勾选后，会忽略 `data/scrape_history.json` 的命中判断，重新向 Apify 发起抓取
- 但如果这次重跑过程中出现整批失败或当前原始文件为空，系统不会静默覆盖掉上一次可用结果
- 在这种情况下，后端会明确返回“已保留最近一次可用结果 / 最近一次非空快照”，并同时带上失败批次摘要

缓存历史文件：

- `data/scrape_history.json`

## 3. Apify 原始结果落盘

采集结果先保存到：

- `data/<platform>/<platform>_data.json`

例如：

- `data/tiktok/tiktok_data.json`
- `data/instagram/instagram_data.json`

同时系统会保存一份“最近一次非空原始快照”：

- `data/<platform>/<platform>_data_last_non_empty.json`

这个文件很重要，因为主数据文件后面会被初筛覆盖，不能把它理解成永远的“原始全量数据”。

## 4. 第一轮规则初筛

采集完成后，后端会立刻调用：

- `scripts/data_cleaner.py -> filter_and_save_dataset`

这一步会把原始采集结果按“账号维度”整理成 `profile_reviews`。

`profile_reviews` 是项目里最重要的一份审核中间结果。

它包含：

- `username`
- `profile_url`
- `status`
- `reason`
- `covers`
- `latest_post_time`
- `soft_flags`
- `stats`
- `upload_metadata`

Phase 3 之后，这份文件也被视为稳定的 prescreen review contract。TikTok / Instagram / YouTube 都应该输出同一批核心字段；后面的视觉复核、测试导出、最终导出都默认基于它，而不是各自重新猜字段。

落盘位置：

- `data/<platform>/<platform>_profile_reviews.json`

例如：

- `data/tiktok/tiktok_profile_reviews.json`
- `data/instagram/instagram_profile_reviews.json`

### 当前各平台真实初筛逻辑

#### TikTok

当前主链路是 `check_tiktok_tapo`：

1. 取最近 50 条视频
2. 看 `playCount` 的平均值和中位数是否都大于 10000
3. 取最近 100 条内容，检查 `text + hashtags[].name` 的美妆占比是否超过 50%
4. 通过后提取前 10 张封面做视觉复核

#### Instagram

当前主链路是 `check_instagram_custom`：

1. 优先读上传表 `Region`
2. 若上传表没有，再回退 API 的 `biography/addressStreet/cityName/location/businessAddressJson`
3. 优先读上传表 `Language`
4. 若上传表没有，再回退 `biography` 做英语判断
5. 检查最近帖子是否超过 30 天未更新
6. 检查最近 100 条 `caption` 是否命中关系词
7. 通过后提取前 10 张 `displayUrl` 做视觉复核

#### YouTube

当前主链路是 `check_youtube`：

1. 检查最近一条内容时间
2. 检查频道外链和视频描述外链
3. 检查近期 `isPaidContent`
4. 检查标题 / 描述 / 频道简介关键词
5. 通过后提取封面进入视觉复核

## 5. 页面显示的“结果”来自哪里

前端展示初筛结果时，核心依赖的是：

- `result.profile_reviews`

表格原始数据接口：

- `GET /api/results/<platform>`

但真正给运营看“这个账号为什么通过/失败”的，不是原始采集 JSON，而是 `profile_reviews`。

所以后续你要改审核逻辑，优先看：

- `scripts/data_cleaner.py`
- `data/<platform>/<platform>_profile_reviews.json`

## 6. 第二轮视觉复核

当前只有第一轮 `Pass` 且带封面的账号，才会进入视觉复核。

前端发起：

- `POST /api/jobs/visual-review`

后端入口：

- `perform_visual_review`

每个账号的流程是：

1. 收集封面候选
2. 优先尝试本地缓存 / 本地封面路径
3. 再尝试远程 URL
4. 下载封面并拼成 3x3 九宫格
5. 实时把“第几张成功 / 第几张失败 / 当前处理步骤”回传前端
6. 把九宫格交给视觉模型判定

### 当前视觉阶段的几个关键点

- 目标九宫格最多 9 张
- 至少需要 `MIN_VISUAL_REVIEW_COVER_COUNT=3` 张可用图才能继续
- 不足 3 张时，该账号会记为视觉失败，不会再进入模型判断

### 视觉复核模式和降级语义

- `simple`：只取首张九宫格，最多送审 9 张封面
- `enhanced`：最多生成 2 张九宫格，最多送审 18 张封面
- `auto`：先按封面候选数决定是否尝试双九宫格；如果最终成功下载的可用封面低于 `AUTO_ENHANCED_MIN_SUCCESS_COVERS`，会明确降级为 `simple`
- 候选封面顺序现在固定为：本地缓存 / `cover_paths` -> review record 里的 `covers` / `cover_urls` -> 平台补充候选；不再按 CDN host 重新打乱
- 当 `auto` 发生降级时，前端会继续展示已成功生成的全部九宫格预览，但会明确标注“实际送审张数”和“仅保留预览”的拼图，避免 operator 误以为模型看过更多图片
- `partial_result.live_review` 现在是一份稳定 contract，前端主要依赖：
  - `current_collage_urls`
  - `collage_count`
  - `reviewed_collage_count`
  - `requested_mode`
  - `applied_mode`
  - `downgrade_reason`
  - `collage_error_count`

### 视觉模型调用方式

当前是双源自动降级：

1. 先试 `quan2go`
2. 失败再试 `auto-code`

模型返回统一结构：

- `decision`
- `reason`
- `signals`
- `provider`

## 7. 为什么前端能实时看到九宫格日志

因为视觉复核是 job 模式，前端会持续轮询：

- `GET /api/jobs/<job_id>`

后端在视觉复核过程中会不断推送：

- 当前账号
- 当前拼图预览图
- 当前步骤
- 每一张封面加载成功 / 失败日志
- 最终判定结果

前端因此可以显示：

- 当前实时复核对象
- 九宫格推理日志
- 已完成复核历史

## 8. 导出链路

### 原始 JSON / Excel

按钮用途：

- `JSON`：下载“测试合并 JSON”
- `Excel`：下载当前 `*_data.json` 展平结果

注意：

- `JSON` 现在不是单纯原始 Apify JSON
- 它是融合了上传表、初筛结果、原始抓取数据的调试导出

### 初筛结果表

- `GET /api/download/<platform>/prescreen-review`

内容包括：

- 初筛通过 / 失败 / 缺失
- 初筛原因
- 封面数量
- 上传表字段

### 带封面初筛表

- `GET /api/download/<platform>/image-review`

内容包括：

- 初筛状态
- 初筛原因
- 9 张封面链接
- 上传表字段

### 测试信息表

- `GET /api/download/<platform>/test-info`

这是 PRD 调试专用导出：

- Sheet 1：账号维度审核表
- Sheet 2：Raw Apify Data 展平表

### 测试信息 JSON

- `GET /api/download/<platform>/test-info-json`

这是当前最完整的一键导出，适合后续改 PRD。

它同时包含：

- 上传表字段
- `profile_reviews`
- 原始 Apify 数据
- 原始数据来源说明

### 最终复核表

- `POST /api/download/<platform>/final-review`

它会把两份数据合并：

1. 第一轮 `profile_reviews`
2. 第二轮 `visual_results`

输出字段包括：

- `prescreen_status`
- `prescreen_reason`
- `visual_status`
- `visual_reason`
- `visual_signals`
- `final_status`
- `final_reason`

## 当前最关键的 5 份数据文件

### 1. 上传元数据

- `data/<platform>/<platform>_upload_metadata.json`

来源：你的 Excel 表

用途：把上传表里的 `Region/Language/Followers/...` 融到审核链路里

### 2. 当前数据文件

- `data/<platform>/<platform>_data.json`

来源：当前采集结果

注意：会被初筛链路覆盖，不要把它当永久原始数据仓库

### 3. 原始快照兜底

- `data/<platform>/<platform>_data_last_non_empty.json`

来源：采集成功时自动保存

用途：当前数据文件为空时，导出测试信息仍能拿到最近一次原始数据

### 4. 初筛主结果

- `data/<platform>/<platform>_profile_reviews.json`

来源：`scripts/data_cleaner.py`

用途：前端显示、导出、视觉复核入口，全都依赖它

### 5. 视觉复核结果

当前主要存在于：

- job 返回值
- 前端内存状态

注意：

- 它目前不是单独长期落盘的正式文件
- 所以“最终复核表”是在导出瞬间，用前端持有的 `visual_results` 和后端的 `profile_reviews` 合并生成的

## 新人最容易踩的坑

### 1. 不要把 `*_data.json` 当最终审核结果

真正的审核主结果是：

- `*_profile_reviews.json`

### 2. Instagram 已经不是只靠 Apify 字段初筛

当前 Instagram 主链路已经融合了上传表的：

- `Region`
- `Language`

### 3. JSON 按钮现在下载的是“测试合并 JSON”

不是纯原始 Apify 返回。

### 4. 视觉失败不一定是模型失败

很多视觉失败其实发生在模型之前，比如：

- 九宫格封面下载失败
- 可用封面不足 3 张

### 5. 视觉结果目前偏“任务态”

刷新页面后，如果前端状态丢了，就不能直接凭后端永久文件恢复完整最终复核结果。

## 关键代码入口

### 上传

- `backend/app.py -> /api/upload`

### 采集任务

- `backend/app.py -> /api/jobs/scrape`
- `backend/app.py -> perform_scrape`

### 初筛

- `backend/app.py -> finalize_apify_output`
- `scripts/data_cleaner.py -> filter_and_save_dataset`

### 视觉复核

- `backend/app.py -> /api/jobs/visual-review`
- `backend/app.py -> perform_visual_review`
- `backend/app.py -> evaluate_cover_collage`

### 导出

- `backend/app.py -> /api/download/<platform>/prescreen-review`
- `backend/app.py -> /api/download/<platform>/image-review`
- `backend/app.py -> /api/download/<platform>/test-info`
- `backend/app.py -> /api/download/<platform>/test-info-json`
- `backend/app.py -> /api/download/<platform>/final-review`

## 推荐阅读顺序

如果你要快速上手，按这个顺序看：

1. 本 README
2. `docs/field_dictionary.md`
3. `docs/prd/instagram_prd_mapping.md`
4. `docs/prd/tiktok_prd_mapping.md`
5. `scripts/data_cleaner.py`
6. `backend/app.py`

## 一句话总结

这个项目的本质不是“爬虫项目”，而是“名单驱动的两阶段审核系统”：

- 第一阶段：规则初筛
- 第二阶段：视觉模型复核

真正的业务主数据是：

- 上传表元数据
- `profile_reviews`
- 视觉复核结果

后面无论改 PRD、改字段、改平台逻辑，都应该围绕这三层去改。
