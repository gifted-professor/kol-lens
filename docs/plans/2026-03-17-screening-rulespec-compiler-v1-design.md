# 筛号规则 RuleSpec 编译器 V1 设计

> 日期：2026-03-17
> 状态：讨论稿
> 目标：把一段品牌方“筛号/审核规则”需求，稳定地编译成 `RuleSpec + 字段匹配报告`，并把幻觉风险压到最低。

## 一、V1 范围

V1 只覆盖“筛号/审核规则”。

允许进入编译器的需求类型：

- 粉丝量、播放量、互动率、评论量等数值门槛
- 标题 / 文案 / 标签 / 简介等文本规则
- 活跃度、地区、语言、是否恰饭等资格门槛
- 评论相关需求，但仅在当前字段或采集能力允许时标记为可用
- 封面视觉规则，但仅标记为 `needs_vision`
- 最终判定逻辑，如 `步骤 1 && 步骤 2 && !步骤 3`

V1 明确不做：

- 邮件建联
- 回信追问
- 报价分析
- 飞书同步
- 跟进节奏
- 自动生成 Python 代码
- 自动接入现有筛号逻辑

这些动作型流程在 V1 中一律进入 `out_of_scope_actions`，不会参与规则编译。

V1 strict mode 的平台范围也一并固定：

- 支持：`TikTok`、`Instagram`
- 暂不支持：`YouTube`

原因不是业务上不需要 YouTube，而是当前严格白名单模式要求“所有字段必须来自本地机读词典”，而 `config/field_mapping.json` 还没有正式的 `youtube_api` 段。V1 不允许绕过这条约束。

## 二、V1 核心目标

这个系统不是“模板生成器”，也不是“自由写代码的 AI 助手”，而是一个稳定的受限编译器。

它必须满足四个约束：

1. 大模型只能做受限解析，不能自由发明字段、函数、指标。
2. 字段匹配必须严格依赖本地机读词典，不允许猜测近义字段。
3. 一旦信息不足，宁可输出 `unsupported / ambiguous / missing_capabilities`，也不乱匹配。
4. 输出只用于审阅，不直接改变现有 `scripts/data_cleaner.py` 逻辑。

## 三、为什么当前启发式模板生成器不够

当前仓库已有的需求模板生成功能更像“解释器”：

- 它会把文本拆成步骤
- 尝试识别部分规则
- 输出平台模板和支持状态

但它的问题是：

- 解析规则仍然偏启发式
- 结果结构还不够像编译器产物
- 没有严格把“大模型解析”和“字段匹配”隔离
- 还没有显式的 `ambiguous / out_of_scope / machine_unreadable` 失败类型

V1 编译器应该替代这条思路，而不是继续在其上无限追加 if/else。

## 四、目标产物

V1 每次运行只输出四类产物：

- `rule_spec.json`
- `field_match_report.json`
- `missing_capabilities.json`
- `review_notes.md`

### 1. rule_spec.json

这是“需求语义层”的受限中间表示，不包含真实代码，不直接绑定 Python 实现。

示例：

```json
{
  "version": "v1",
  "scope": "screening_rules_only",
  "goal": "判断达人是否符合家庭/宠物/户外合作需求",
  "rules": [
    {
      "id": "rule_001",
      "platforms": ["tiktok", "instagram"],
      "rule_type": "metric_threshold",
      "subject": "recent_posts",
      "window": 50,
      "metric_intent": "view_count_median",
      "operator": ">",
      "threshold": 10000,
      "source_text": "近 50 条视频中位数播放量 > 10000"
    }
  ],
  "final_logic": "(rule_001 && rule_002) && !rule_003"
}
```

### 2. field_match_report.json

这是“字段绑定层”的确定性结果。

示例：

```json
{
  "rule_id": "rule_001",
  "status": "matched",
  "platform_matches": {
    "tiktok": {
      "fields": ["tiktok_api.playCount"],
      "confidence_mode": "deterministic"
    },
    "instagram": {
      "fields": ["instagram_api.latestPosts[].videoViewCount"],
      "confidence_mode": "partial"
    }
  }
}
```

### 3. missing_capabilities.json

记录当前词典或采集链路不足以实现的部分。

示例：

```json
{
  "rule_id": "rule_007",
  "status": "missing_capabilities",
  "required": ["comment_text"],
  "reason": "当前只有 commentsCount，没有评论正文"
}
```

### 4. review_notes.md

给运营或维护者读的简明说明，包括：

- 哪些规则已稳定匹配
- 哪些规则因缺字段被拒绝
- 哪些内容超出 V1 范围
- 哪些需求文本存在歧义

## 五、架构分层

V1 必须拆成四个阶段，每一层都限制能力边界。

### 阶段 A：Scope Filter

先把输入需求切成两类：

- `screening_rules`
- `out_of_scope_actions`

比如：

- “最近 30 条视频播放量中位数” -> `screening_rules`
- “通过多个邮箱群发建联” -> `out_of_scope_actions`
- “品牌方选择不合作则自动婉拒” -> `out_of_scope_actions`

这个阶段的目标不是理解所有业务，而是先把非筛号流程挡在编译器外面。

### 阶段 B：Constrained Parse

大模型只负责把 `screening_rules` 解析成受限 JSON。

这里必须使用严格 schema：

- `rule_type` 只能来自枚举
- `metric_intent` 只能来自枚举
- `subject` 只能来自枚举
- `operator` 只能来自枚举
- `platforms` 只能来自固定平台集

大模型不能直接输出真实字段路径，如：

- 不允许直接写 `tiktok_api.playCount`
- 不允许写 Python 代码
- 不允许发明 `engagement_quality_score` 之类词典外概念

它只能输出“意图”，例如：

- `metric_intent = view_count_median`
- `required_capability = comment_text`
- `required_capability = cover_vision`

### 阶段 C：Deterministic Match

这一层不能依赖大模型。

输入：

- `rule_spec.json`
- `config/field_mapping.json`

输出：

- `matched`
- `partial`
- `unsupported`
- `ambiguous`
- `missing_capabilities`

匹配规则必须写死在本地：

- `view_count_median` -> 允许映射到哪些字段
- `caption_text` -> 允许映射到哪些字段
- `region_signal` -> 允许映射到哪些字段
- `comment_text` -> 当前哪些平台没有

一旦没有唯一确定映射，就不能猜。

### 阶段 D：Validation Gate

最终所有输出还要过一次验证：

- 不允许引用词典外字段
- 不允许输出未声明 capability
- 不允许把 `out_of_scope_actions` 混进可执行规则
- 不允许把敏感属性规则标记为 matched

验证失败就整体标红，不下发结果。

## 六、低幻觉约束

V1 稳定性的关键不在“大模型更聪明”，而在“大模型权限更小”。

必须执行以下约束：

### 1. 禁止自由字段输出

LLM 只能输出字段意图，不能输出真实字段路径。

### 2. 禁止自由算法命名

LLM 不能发明新的指标名。

只允许输出本地定义的 `metric_intent` 枚举，如：

- `follower_count`
- `view_count_mean`
- `view_count_median`
- `engagement_rate`
- `comment_positive_ratio`
- `activity_recency_days`
- `language_gate`
- `region_gate`
- `cover_scene_presence`

### 3. 禁止自由代码输出

V1 不产出 Python，不产出 prompt，不产出 patch。

### 4. 敏感属性一律阻断

种族、年龄等需求一律输出：

- `blocked_sensitive_attribute`

不能参与后续匹配。

### 5. 解释优先于强行成功

如果规则文本过于模糊，例如：

- “流量好”
- “内容有质感”
- “评论不错”

则输出：

- `ambiguous`

而不是尝试替换成某个现有指标。

## 七、RuleSpec Schema 建议

V1 规则 schema 建议至少包含：

- `id`
- `source_text`
- `rule_type`
- `platforms`
- `subject`
- `window`
- `metric_intent`
- `operator`
- `threshold`
- `required_capabilities`
- `needs_vision`
- `status_hint`

推荐的 `rule_type` 枚举：

- `metric_threshold`
- `metric_ratio`
- `keyword_presence`
- `keyword_ratio`
- `classification_gate`
- `activity_gate`
- `region_gate`
- `language_gate`
- `vision_gate`
- `final_logic`
- `blocked_sensitive_attribute`
- `ambiguous_rule`
- `out_of_scope_action`

## 八、字段匹配策略

字段匹配不是“字符串模糊搜索”，而是“意图 -> 白名单能力 -> 真实字段”。

例如：

- `view_count_median`
  - TikTok：`tiktok_api.playCount`
  - Instagram：`instagram_api.latestPosts[].videoViewCount`
  - YouTube：只有在机读词典存在时才允许稳定匹配

- `caption_text`
  - TikTok：`tiktok_api.text`
  - Instagram：`instagram_api.latestPosts[].caption`
  - YouTube：需要机读词典支持

- `comment_text`
  - TikTok：当前仅有 `commentsDatasetUrl` 入口，主链路未采正文 -> `missing_capabilities`
  - Instagram：当前无评论正文 -> `missing_capabilities`
  - YouTube：当前无评论正文 -> `missing_capabilities`

## 九、关键限制：YouTube 机读词典缺口

当前 `config/field_mapping.json` 只覆盖：

- `upload_metadata`
- `instagram_api`
- `tiktok_api`

它还没有 `youtube_api` 段。

这意味着如果 V1 要坚持“严格一对一匹配本地字段词典”，那么 YouTube 有两种做法：

### 方案 A：V1 严格模式仅支持 TikTok + Instagram

优点：

- 最符合“低幻觉、强白名单”目标
- 没有词典就不开放平台

缺点：

- YouTube V1 不能进入 stable compiler

### 方案 B：先补齐 `youtube_api` 到 `config/field_mapping.json`

优点：

- 三平台统一

缺点：

- 需要先做字段字典扩展工作

建议：

- 若目标是“先把 skill 做稳”，V1 应先按方案 A 执行
- YouTube 等词典补齐后再进入 strict compiler

本项目当前已确认采用该建议：

- `V1 strict mode = TikTok + Instagram only`
- `YouTube = unsupported until machine-readable dictionary coverage exists`

## 十、推荐实现顺序

V1 实现顺序建议固定为：

1. 定义 `RuleSpec` JSON Schema
2. 定义 `metric_intent` / `required_capabilities` 白名单枚举
3. 编写 `scope_filter`
4. 编写受限 LLM parser，强制输出 schema
5. 编写 deterministic matcher
6. 编写 validator
7. 产出 `rule_spec.json` / `field_match_report.json` / `missing_capabilities.json` / `review_notes.md`
8. 用 10-20 条真实品牌需求做 golden tests

## 十一、V1 成功标准

满足以下条件才算 V1 成功：

1. 用户输入动作型流程时，系统能明确剔除，不误编译成筛号规则。
2. 用户输入筛号需求时，系统只输出词典白名单内可解释的规则。
3. 匹配不上时，系统稳定输出 `unsupported / ambiguous / missing_capabilities`。
4. 系统不直接生成 Python，不改线上规则，不引入隐式执行。
5. 同一输入在同一词典版本下应得到稳定一致的输出。

## 十二、与现有功能关系

现有 `/api/templates/generate` 更适合作为：

- 原型验证工具
- 需求收集器
- 旧版启发式模板生成器

它不应直接等同于未来的 stable compiler。

建议后续新增独立路径，例如：

- `scripts/compile_screening_rulespec.py`
- 或 `backend/app.py -> /api/rulespec/compile`

以免把启发式模板逻辑和严格编译器逻辑混在一起。
