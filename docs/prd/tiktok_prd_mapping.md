# TikTok 数据引擎映射文档 (PRD - TikTok Module)

> 最后同步：2026-03-18  
> 当前主链路实际调用：`scripts/data_cleaner.py -> check_tiktok_tapo`  
> 说明：代码中仍保留 `check_tiktok` 通用版逻辑，但当前批量初筛主流程未调用。
> 字段总览入口：[`docs/field_dictionary.md`](../field_dictionary.md)；机器可读配置：`config/field_mapping.json`

## Phase 4 维护提示

- TikTok 当前活跃入口函数只有 `check_tiktok_tapo`；字段追溯以 `config/field_mapping.json -> tiktok_api / upload_metadata` 为准。
- 该链路产出的 `profile_reviews` 与 `covers` 会继续流向 `/api/download/<platform>/prescreen-review`、`/image-review`、`/final-review`。
- `final-review` 导出允许后端回退到已保存 artifact；前端只消费 `saved_final_review_artifacts_available` 这个 readiness 信号，不自行发明新鲜度协议。

## 数据源特征

Apify 返回的 TikTok 结果是视频数组。每条视频记录里带有本条视频信息，同时重复嵌套博主级信息 `authorMeta`。

---

## 当前生效的初筛逻辑

### 入口

当前 TikTok 批量初筛主流程调用的是 `check_tiktok_tapo(items)`，也就是 Tapo 定制版逻辑。

### 判定流程

| 步骤 | JSON 字段路径 | 当前实现 | 结果 |
| :--- | :--- | :--- | :--- |
| 无数据校验 | 根数组 | 数据为空时直接返回 `未抓取到数据` | Reject |
| 播放量门槛 | `playCount`（按最近 50 条） | 最近 50 条视频的平均播放量和中位数都必须 `> 10000` | 任一不达标则 Reject |
| 美妆内容占比 | `text`, `hashtags[].name`（按最近 100 条） | 命中美妆关键词的视频条数占比 `> 50%` 时 | Reject |
| 视觉封面提取 | 最近 10 条 | 普通视频取 `videoMeta.originalCoverUrl` 或 `videoMeta.coverUrl`；图文轮播取 `slideshowImageLinks[0].tiktokLink` | Pass |

### 当前美妆排除关键词

当前代码中用于 Tapo 路径的关键词包括：

`makeup`, `skincare`, `foundation`, `concealer`, `mascara`, `lipstick`, `eyeshadow`, `blush`, `contour`, `highlighter`, `primer`, `serum`, `moisturizer`, `cleanser`, `toner`, `beauty routine`, `grwm`, `get ready with me`, `beauty hack`, `glow up`, `skin care`, `makeup tutorial`, `beauty tip`, `cosmetic`, `nail art`, `lash`, `brow`, `lip gloss`, `beauty review`, `haul`, `swatch`

### 当前主链路未执行的项

当前 Tapo 主链路没有执行下列通用规则：

- 活跃度 30 天校验
- `bioLink` 外链禁词校验
- 简介 / 文案 / 标签的通用禁词排雷

如果 TikTok 业务希望重新启用这些规则，需要切回或合并 `check_tiktok`。

---

## 当前返回结果

### Pass

通过时会保留：

- `covers`：最多 10 张封面
- `latest_post_time`
- `stats.avg_views`
- `stats.median_views`
- `stats.video_count`
- `stats.beauty_ratio`

### Reject

常见拒绝原因包括：

- `未抓取到数据`
- `播放量不达标（均值 X，中位数 Y，门槛 10000）`
- `美妆内容占比过高（XX%），不符合智能家居场景`

### Missing

如果输入名单里有账号，但采集结果里完全没返回该账号，则会在导出层记录为：

- `status = Missing`
- `reason = 采集器未返回该账号数据`

## Phase 4 审计 / 导出交接

- raw 路径：
  - `/api/download/<platform>/json`
  - `/api/download/<platform>/excel`
- review 路径：
  - `/api/download/<platform>/test-info`
  - `/api/download/<platform>/test-info-json`
  - `/api/download/<platform>/prescreen-review`
  - `/api/download/<platform>/image-review`
  - `/api/download/<platform>/final-review`
- 维护者排查导出字段时，先回 `config/field_mapping.json` 和 [`docs/field_dictionary.md`](../field_dictionary.md) 找 `upload_metadata.*`、`tiktok_api.*` 的实际来源，再看 `backend/app.py` 的导出拼装。

---

## 当前未接入主链路的备用通用逻辑

代码中仍保留 `check_tiktok(data)`，但当前批量初筛不走这条链路。该逻辑内容如下：

| 检查项 | JSON 字段路径 | 规则 |
| :--- | :--- | :--- |
| 活跃度 | 最近一条 `createTimeISO` | 最近一条视频距今超过 30 天则 Reject |
| 主页外链硬拒 | `authorMeta.bioLink` | 命中 `temu`, `shein`, `aliexpress`, `$1`, `pregnant`, `baby`, `expecting`, `momlife`, `motherhood` 直接 Reject |
| 文本/标签硬拒 | `authorMeta.signature`, `text`, `hashtags[].name`（前 20 条） | 命中上述同一套禁词直接 Reject |
| 视觉封面 | 最近 9 条 | 普通视频取 `originalCoverUrl/coverUrl`，图文取 `slideshowImageLinks[0].tiktokLink` |

---

## 视觉复核阶段

TikTok 初筛通过后，会把封面交给视觉模型做第二轮判断。当前视觉阶段主要负责：

1. 画面环境是否整洁、明亮、有生活感
2. 是否过度商业化、摆拍感过强
3. 是否存在大面积纹身、过度性感暴露
4. 是否是满屏晒娃型账号
5. 是否属于优先垂类，如医生、皮肤科、瑜伽、普拉提、职场女性等

---

## 维护要求

凡是以下内容发生变化，必须在同一次提交中同步更新本文件：

- `check_tiktok_tapo` 的阈值、字段、关键词或拒绝原因
- 主链路从 `check_tiktok_tapo` 切换到 `check_tiktok`
- TikTok 初筛从 Tapo 定制规则改回通用规则或混合规则
