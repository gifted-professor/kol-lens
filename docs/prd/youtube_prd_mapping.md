# YouTube 数据引擎映射文档 (PRD - YT Module)

> 最后同步：2026-03-16  
> 当前主链路实际调用：`scripts/data_cleaner.py -> check_youtube`

## 数据源特征

Apify 返回的是视频数组。频道级信息通常重复出现在每条视频的 `aboutChannelInfo` 中，因此频道信息默认以第一条视频为准。

---

## 当前生效的初筛逻辑

| 步骤 | JSON 字段路径 | 当前实现 | 结果 |
| :--- | :--- | :--- | :--- |
| 无数据校验 | 根数组 | 数据为空时直接返回 `未抓取到数据` | Reject |
| 活跃度 | 最近一条 `date` | 最近一条视频距今超过 30 天 | Reject |
| 频道外链硬拒 | `aboutChannelInfo.channelDescriptionLinks[].url` | 命中 `temu`, `shein`, `aliexpress`, `wish` | Reject |
| 视频描述外链硬拒 | `descriptionLinks[].url`（前 20 条视频） | 命中 `temu`, `shein`, `aliexpress`, `wish` | Reject |
| 恰饭浓度阻断 | `isPaidContent`（最近 10 条） | 当样本数 `>= 10` 且最近 10 条中 `isPaidContent = true` 的数量 `>= 8` | Reject |
| 标题/描述/频道简介硬拒 | `aboutChannelInfo.channelDescription`, `title`, `text`（前 20 条） | 命中 `temu`, `shein`, `aliexpress`, `wish`, `pregnancy`, `pregnant`, `baby coming`, `expecting` | Reject |
| 弱语义提示 | `aboutChannelInfo.channelDescription`, `title`, `text` | 命中 `$1`, `baby`, `momlife`, `motherhood` 时不直接拒绝，而是记录到 `soft_flags` | 继续 |
| 视觉封面提取 | `thumbnailUrl`（前 9 条） | 提取封面交给视觉复核 | Pass |

---

## 当前返回结果

### Pass

通过时会保留：

- `covers`：最多 9 张 `thumbnailUrl`
- `latest_post_time`
- `soft_flags`
- `reason`：形如“未命中硬性排雷规则；存在 X 项待复核文本提示；账号近期有更新；已提取 X 张封面供视觉复核”

### Reject

常见拒绝原因包括：

- `未抓取到数据`
- `近 30 天无更新`
- `频道外链命中禁词 "<keyword>"`
- `视频描述外链命中禁词 "<keyword>"`
- `近期付费内容占比过高`
- `标题/描述/频道信息命中禁词 "<keyword>"`

### Missing

如果输入名单里有频道，但采集结果里完全没返回该频道，则会在导出层记录为：

- `status = Missing`
- `reason = 采集器未返回该账号数据`

---

## 视觉复核阶段

YouTube 初筛通过后，会把封面交给视觉模型做第二轮判断。当前视觉阶段主要负责：

1. 画面环境是否整洁、明亮、有生活感
2. 是否过度商业化、广告感过强
3. 是否存在大面积纹身、过度性感暴露
4. 是否是满屏晒娃型账号
5. 是否属于优先垂类，如医生、皮肤科、瑜伽、普拉提、职场女性等

---

## 维护要求

凡是以下内容发生变化，必须在同一次提交中同步更新本文件：

- `check_youtube` 的阈值、字段、关键词或拒绝原因
- `isPaidContent` 的判定口径
- 视觉封面提取数量或字段
