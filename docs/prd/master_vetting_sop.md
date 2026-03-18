# Ulike 达人初筛核心逻辑规范 (Master Vetting SOP)

> 最后同步：2026-03-18  
> 本文档用于描述“当前代码里真实生效”的初筛与视觉复核规则。  
> 对应实现文件：`scripts/data_cleaner.py`、`backend/app.py`
> 字段总览入口：[`docs/field_dictionary.md`](../field_dictionary.md)（当前 v1 覆盖上传表、Instagram、TikTok）
> 机器可读源：`config/field_mapping.json`

---

## 维护入口

- 维护者追字段先看 `config/field_mapping.json`，再看生成文档 [`docs/field_dictionary.md`](../field_dictionary.md)。
- 平台规则入口以 `scripts/data_cleaner.py` 的当前主链路函数为准，不要从旧 PRD 反推。
- Phase 4 起，导出交接只在现有 raw / test-info / prescreen-review / image-review / final-review 路径上加可追溯性，不新增单独审计 UI。

## 一、状态定义

当前系统在初筛导出和前端结果中，主要使用以下状态：

| 状态 | 含义 |
| :--- | :--- |
| `Pass` | 通过初筛，进入视觉复核 |
| `Reject` | 在规则层被筛掉 |
| `Missing` | 输入名单中存在，但采集器未返回该账号数据 |

---

## 二、通用拒绝原因

不同平台口径略有差异，但当前代码里常见的通用拒绝原因包括：

- `未抓取到数据`
- `采集器未返回该账号数据`
- `账号没有可用帖子`
- `近 30 天无更新`

说明：

- 当前代码中的活跃度硬门槛是“最近内容距今超过 30 天直接 Reject”
- 旧文档里提到的“3 个月无更新”口径，当前实现已不再使用

---

## 三、当前主链路

| 平台 | 当前主链路函数 | 说明 |
| :--- | :--- | :--- |
| TikTok | `check_tiktok_tapo` | 当前走 Tapo 定制版，不是旧版通用禁词逻辑 |
| Instagram | `check_instagram_custom` | 当前优先读取上传表的地区字段，再回退 API 资料字段进行美国地区判断，并叠加 30 天活跃度 |
| YouTube | `check_youtube` | 当前走通用版文本 / 外链 / 恰饭浓度逻辑 |

这三条规则才是当前批量初筛真正生效的逻辑，PRD 必须以它们为准。

---

## 四、Phase 4 导出交接约束

- raw 导出保持 raw 语义：
  - `/api/download/<platform>/json`
  - `/api/download/<platform>/excel`
- 审核交接导出保持 review 语义：
  - `/api/download/<platform>/test-info`
  - `/api/download/<platform>/test-info-json`
  - `/api/download/<platform>/prescreen-review`
  - `/api/download/<platform>/image-review`
  - `/api/download/<platform>/final-review`
- `final-review` 是否可继续导出，不再只看当前前端内存；后端保存的初筛/视觉复核 artifact 通过 `saved_final_review_artifacts_available` 暴露给前端。
- `source_filename`、`identifier`、`profile_url`、上传表回填字段仍是导出对账时的主溯源锚点。

## 四点一、Phase 04.1 主屏 ownership split

Phase 04.1 之后，主屏的维护边界固定如下，后续 Phase 5 模块化必须按这个边界拆，而不是再按旧的纵向滚动顺序拆：

- `运行工作台` 负责 intake / configuration、启动采集、任务进度，以及进入 post-run 区域的结果入口
- `结果工作台` 负责所有 post-run surface，并且内部必须继续分区，不允许重新退化成一个长滚动页
- `视觉复核` 负责 visual review mode、Visual Review Desk、实时对象、历史队列和复核 CTA
- `导出交接` 负责所有 export actions，并在同一 tab 内承接 `Run Snapshot`

额外约束：

- `Run Snapshot` 是 `secondary audit context`，不是主 CTA，也不应该和概览的 Next Action 抢同一块区域
- `RuleSpec Compiler` 属于 secondary tool，不再占据 operator 默认主流程
- 维护者如果想新增 review/export 信息，必须先判断它属于 `视觉复核` 还是 `导出交接`，不能直接继续往概览里塞

## 五、平台级初筛规则摘要

### TikTok

当前主链路重点看两件事：

1. 最近 50 条视频的平均播放量和中位数是否都大于 10000
2. 最近 100 条内容里，美妆关键词命中占比是否超过 50%

通过后提取最近 10 张封面进入视觉复核。

### Instagram

当前主链路重点看四件事：

1. 简介和资料字段里是否能识别出美国 / 加拿大地区线索
2. 上传表 `Language` 或简介是否显示英语为主
3. 最近是否有帖子，且最近一条是否在 30 天内
4. 最近 100 条帖子文案里是否命中 `partner`, `boyfriend`, `girlfriend`, `husband`, `wife`

通过后提取最近 10 张封面进入视觉复核。

### YouTube

当前主链路重点看五件事：

1. 最近一条视频是否在 30 天内
2. 频道外链和视频描述外链是否命中竞品词
3. 最近 10 条视频里 `isPaidContent=true` 是否达到 8 条及以上
4. 频道简介、标题、描述是否命中硬拒关键词
5. 是否命中弱语义提示词并写入 `soft_flags`

通过后提取最近 9 张封面进入视觉复核。

---

## 六、视觉复核负责的内容

当前系统把以下判断放在视觉复核阶段，而不是初筛规则层：

1. 画面环境是否整洁、明亮、有生活感
2. 是否过度商业化、摆拍感或精修感过强
3. 是否存在大面积纹身
4. 是否过度性感或暴露
5. 是否是满屏晒娃型账号
6. 是否属于优先垂类，如医生、皮肤科、瑜伽、普拉提、职场女性等

也就是说，PRD 中如果提到这些项，需要明确它们属于“视觉复核”，不是“Python 初筛硬规则”。

---

## 七、文档与代码同步要求

后续凡是出现以下变化，必须在同一次提交里同步更新 `docs/prd`：

1. 初筛入口函数切换
2. 关键词库变化
3. 活跃度阈值变化
4. 封面提取数量变化
5. 地区、语言、恰饭浓度、播放量等阈值变化
6. 新增大模型二判逻辑
7. 导出交接路径、artifact 回退语义、或 `saved_final_review_artifacts_available` 这类前后端契约变化

如果 PRD 与代码冲突，视为文档失效，需要立即补齐。
