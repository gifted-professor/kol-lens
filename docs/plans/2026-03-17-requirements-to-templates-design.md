# 审核需求拆解与三平台模板生成设计

> 日期：2026-03-17
> 范围：保守版最小实现
> 目标：把品牌方给的一段自由文本审核 SOP，拆解成 TikTok / Instagram / YouTube 三个平台的可执行模板，并明确哪些规则当前可实现、哪些依赖视觉复核、哪些缺字段或不应自动化。

## 背景

当前仓库已经有三条真实生效的主链路：

- TikTok：`scripts/data_cleaner.py -> check_tiktok_tapo`
- Instagram：`scripts/data_cleaner.py -> check_instagram_custom`
- YouTube：`scripts/data_cleaner.py -> check_youtube`

但系统还没有“根据品牌方自由文本需求自动生成审核模板”的能力。运营现在拿到的往往不是代码规则，而是一段自然语言 SOP，例如：

- 看最近 50 条视频的平均播放量和中位数
- 看最近 10 张封面是否有家庭/宠物/户外场景
- 看前 100 条标题是否美妆占比过高
- 看评论区是否大量 emoji

这类需求里，只有一部分能直接映射到当前字段和链路。保守方案必须优先做到两件事：

1. 不胡编能力。模板必须明确告诉用户哪些规则能直接落地，哪些只能交给视觉模型，哪些当前根本没有数据。
2. 不把敏感属性筛选自动化。例如按种族、年龄等受保护属性做通过/拒绝，不应进入自动模板。

## 方案选择

### 方案 A：直接把自由文本映射成运行时代码规则

优点：

- 一步到位，离“动态审核”最近

缺点：

- 风险最高，解析误差会直接改变业务判断
- 当前字段字典并不完整覆盖 YouTube，评论区也不在主链路
- 无法在第一版里稳妥处理敏感属性和视觉/文本混合规则

结论：不采用。

### 方案 B：先做“模板生成器”，只产出结构化模板，不直接接入主链路

优点：

- 风险可控，不会直接改现有审核结果
- 能先把“可实现/缺口/禁区”三类信息沉淀清楚
- 便于后续按模板逐步接入动态规则引擎

缺点：

- 第一版只生成模板，不自动执行

结论：采用。

### 方案 C：先手工维护模板，不做自由文本拆解

优点：

- 实现最简单

缺点：

- 不能满足“每次品牌需求不同，就自动生成不同模板”的目标

结论：不采用。

## 设计原则

- 保守优先：解析失败时宁可标记为 `needs_manual_review`，也不擅自推断。
- 三层能力分离：
  - `rule_engine`：当前字段可直接支持的数值/文本/元数据规则
  - `vision_review`：需要封面视觉判断的规则
  - `unsupported`：当前缺采集、缺字段或缺主链路支撑
- 明确禁区：种族、年龄等敏感属性筛选标记为 `blocked_sensitive_attribute`
- 不改现有接口：第一版只新增脚本和文档，不直接接到 `backend/app.py`

## 输入与输出

### 输入

输入是一段自由文本 SOP，支持中英混合，典型结构包括：

- 审核目标
- 若干步骤（如“步骤 1：数据审核”）
- 每步下的 bullet 规则
- 最终判定逻辑

第一版接受：

- `--input <txt/md 文件>`
- 或 stdin

### 输出

脚本输出到 `temp/generated_templates/<timestamp>/`，包含：

- `parsed_sop.json`：自由文本拆解后的中间结构
- `tiktok.template.json`
- `instagram.template.json`
- `youtube.template.json`
- `template_summary.md`

其中每个平台模板都包含：

- `goal`
- `source_text`
- `checks[]`
- `final_decision`
- `gaps[]`
- `blocked_rules[]`

## 中间结构

自由文本先被解析为统一的中间 DSL。第一版不追求完整 NLP，只覆盖当前高频模式。

每条规则统一为：

```json
{
  "id": "step1_avg_views",
  "step_title": "步骤 1：数据审核",
  "source_line": "若平均播放量 > 10000 且中位数播放量 > 10000，则通过",
  "check_type": "metric_threshold",
  "subject": "recent_posts",
  "window": 50,
  "metric": "view_count_mean",
  "operator": ">",
  "threshold": 10000,
  "execution_layer": "rule_engine"
}
```

第一版支持的规则类型：

- `metric_threshold`
- `metric_ratio_threshold`
- `keyword_presence`
- `keyword_ratio`
- `region_gate`
- `language_gate`
- `activity_recency`
- `vision_presence`
- `vision_ratio_threshold`
- `comment_quality`
- `final_decision`
- `blocked_sensitive_attribute`

## 平台映射策略

### TikTok

优先从 `config/field_mapping.json` 的 `tiktok_api` 读取字段能力，映射到：

- 播放量：`playCount`
- 标题/文案：`text`
- 标签：`hashtags[].name`
- 评论数：`commentCount` 仅数量，不含评论正文
- 评论数据集入口：`commentsDatasetUrl` 存在，但当前主链路未使用
- 封面：`slideshowImageLinks[].tiktokLink` / `videoMeta.originalCoverUrl` / `videoMeta.coverUrl`
- 主页信息：`authorMeta.*`

结论：

- 数值阈值、标题/文案关键词、美妆占比、封面视觉规则可映射
- 评论正文类规则只能标记为“需要新增评论采集链路”

### Instagram

优先从 `config/field_mapping.json` 的 `instagram_api` 读取字段能力，映射到：

- 地区/语言：上传表 `region` / `language`，以及 `biography`、地址字段
- 活跃度：`latestPosts[].timestamp`
- 标题/文案：`latestPosts[].caption`
- 评论数：`latestPosts[].commentsCount` 只有数量，没有评论正文
- 封面：`latestPosts[].displayUrl`

结论：

- 地区、语言、活跃度、caption 关键词、封面视觉规则可映射
- 评论正文类规则和“看视频内容而不只是封面”的规则当前不能直接实现

### YouTube

当前机读字段字典尚未覆盖 YouTube，因此第一版以 `scripts/data_cleaner.py` 和
`docs/prd/youtube_prd_mapping.md` 为保守事实来源，映射到：

- 活跃度：`date`
- 标题：`title`
- 描述：`text`
- 外链：`aboutChannelInfo.channelDescriptionLinks[].url`、`descriptionLinks[].url`
- 恰饭：`isPaidContent`
- 封面：`thumbnailUrl`
- 频道简介：`aboutChannelInfo.channelDescription`

结论：

- YouTube 模板可以生成，但必须在摘要里明确标注：“当前为代码推断映射，尚未纳入 `config/field_mapping.json`”

## 缺口与禁区判定

### 可支持

满足以下条件时，模板标记为 `supported`：

- 当前字段存在
- 规则语义能明确映射到字段
- 不涉及敏感属性
- 当前主链路或独立脚本可执行

### 部分支持

满足以下任一条件时，标记为 `partial`：

- 字段存在，但当前主链路未启用
- 当前只能看封面，无法看完整视频内容
- 需要新增字段组合或额外提示文案才能执行

### 不支持

满足以下任一条件时，标记为 `unsupported`：

- 当前没有字段
- 当前没有评论正文采集
- 当前没有视频帧/视频内容分析链路

### 禁止自动化

以下规则不进入自动模板执行：

- 按种族/民族筛选
- 按年龄段直接拒绝或通过
- 其他明显依赖受保护属性的自动化判断

这类规则会保留在 `blocked_rules[]`，并附带原因说明，提醒人工改写需求。

## 模板结构

每个平台模板统一为：

```json
{
  "platform": "tiktok",
  "goal": "判断该达人是否符合 Tapo 家庭/宠物/户外生活场景类内容合作标准。",
  "template_version": "2026-03-17",
  "mapping_basis": [
    "config/field_mapping.json",
    "scripts/data_cleaner.py"
  ],
  "checks": [
    {
      "id": "step1_view_mean",
      "status": "supported",
      "execution_layer": "rule_engine",
      "check_type": "metric_threshold",
      "window": 50,
      "fields": ["playCount"],
      "metric": "mean",
      "operator": ">",
      "threshold": 10000,
      "notes": "对应最近 50 条视频播放量均值"
    }
  ],
  "final_decision": {
    "logic": "(step1 && step2) && !step3"
  },
  "gaps": [],
  "blocked_rules": []
}
```

## 最小实现范围

第一版脚本必须做到：

1. 识别步骤、bullet、最终结果
2. 识别高频规则模式：
   - 平均值 / 中位数 / 占比 / 关键词 / 地区 / 语言 / 活跃度
   - 封面场景出现
   - 封面场景占比阈值
   - 评论区 emoji 类规则
3. 为 TikTok / Instagram / YouTube 生成模板
4. 清楚标出：
   - `supported`
   - `partial`
   - `unsupported`
   - `blocked_sensitive_attribute`

第一版明确不做：

- 直接把模板接到线上审核执行
- 引入 LLM 解析
- 修改现有 prescreen / visual review 接口

## 验证

使用两段真实风格样例做验证：

1. Tapo 家庭/宠物/户外场景类 SOP
2. 美国/加拿大英语博主 + 互动风格类 SOP

验证标准：

- 能拆出步骤与最终判定
- TikTok / Instagram / YouTube 三份模板都生成成功
- 评论区、视频内容、受保护属性规则被正确标记
- Markdown 摘要能让运营一眼看出哪些规则当前能做、哪些不能做

## 后续演进

后续如果要从“模板生成”走向“模板执行”，建议顺序是：

1. 先把 YouTube 纳入 `config/field_mapping.json`
2. 再把评论采集能力做成可选链路
3. 最后才考虑把模板 DSL 接入 `scripts/data_cleaner.py` 或新增规则引擎
