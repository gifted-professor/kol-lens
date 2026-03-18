# Instagram 数据引擎映射文档 (PRD - IG Module)

> 最后同步：2026-03-18  
> 当前主链路实际调用：`scripts/data_cleaner.py -> check_instagram_custom`  
> 说明：代码中仍保留 `check_instagram` 通用版逻辑，但当前批量初筛主流程未调用。
> 字段总览入口：[`docs/field_dictionary.md`](../field_dictionary.md)；机器可读配置：`config/field_mapping.json`

## Phase 4 维护提示

- Instagram 当前活跃入口函数只有 `check_instagram_custom`；字段追溯以 `config/field_mapping.json -> instagram_api / upload_metadata` 为准。
- 该链路产出的 `profile_reviews` 与 `covers` 会继续流向 `/api/download/<platform>/prescreen-review`、`/image-review`、`/final-review`。
- `final-review` 导出允许后端回退到已保存 artifact；前端只消费 `saved_final_review_artifacts_available` 这个 readiness 信号，不自行发明新鲜度协议。

## 数据源特征

Apify 返回的 Instagram 结果通常是单个博主对象，或仅包含一个对象的数组。主页级字段在根节点，帖子列表集中在 `latestPosts`。

---

## 当前生效的初筛逻辑

### 入口

当前后端在初筛阶段对 Instagram 调用的是 `check_instagram_custom(profile)`，不是旧版通用逻辑。

### 判定流程

| 步骤 | JSON 字段路径 | 当前实现 | 结果 |
| :--- | :--- | :--- | :--- |
| 无数据校验 | 根对象 / 数组 | 数据为空时直接返回 `未抓取到数据` | Reject |
| 地区线索 | 上传表 `Region`；若缺失则回退 `biography`, `addressStreet`, `cityName`, `location`, `businessAddressJson` | 优先读取上传表 `Region`；命中 `US/CA` 或对应英文全称即通过。若上传表无值，再将 API 资料字段合并后统一小写匹配美国/加拿大国家、州、省、主要城市关键词与正则 | 未命中则 Reject |
| 语言检测 | 上传表 `Language`；若缺失则回退 `biography` | 优先读取上传表 `Language`；命中 `en/eng/english` 视为英语。若上传表无值，再基于简介做简单英文检测：字母中 ASCII 占比 `< 0.6` 视为“非英语为主” | Reject |
| 帖子可用性 | `latestPosts` | 无可用帖子 | Reject |
| 活跃度 | `latestPosts[].timestamp` | 按最近一条帖子时间判断；距今超过 30 天 | Reject |
| 关系类排除 | `latestPosts[].caption`（前 100 条） | 命中任一关键词：`partner`, `boyfriend`, `girlfriend`, `husband`, `wife` | Reject |
| 视觉封面提取 | `latestPosts[].displayUrl`（前 10 条） | 提取封面交给视觉复核 | Pass |

### 地区判定补充说明

当前“美国/加拿大地区”是规则匹配，不是大模型判断。匹配来源包括：

- 上传表 `Region`：优先级最高，支持 `US`、`CA` 及对应英文全称
- 国家级关键词：`usa`, `united states`, `canada`, `canadian`
- 美国州名、加拿大省名
- 常见北美城市/区域名，如 `nyc`, `los angeles`, `toronto`, `vancouver`
- 正则兜底：`U.S.A.`、`United States` 的带点/带空格写法

这意味着如果上传表已明确提供 `Region`，即使 API 资料里没有地区字段，也能直接参与初筛；反之，如果上传表和 API 资料都缺地区线索，仍会被地区层挡掉。

---

## 当前返回结果

### Pass

通过时会保留：

- `covers`：最多 10 张 `displayUrl`
- `latest_post_time`
- `reason`：形如“地区与语言符合（已融合上传表与 API 数据）；未命中情侣关系词；已提取 X 张封面供视觉复核”

### Reject

常见拒绝原因包括：

- `未抓取到数据`
- `上传表 Region 未命中美国/加拿大`
- `简介或资料字段未识别到美国/加拿大地区线索`
- `上传表 Language 未命中英语`
- `内容语言可能非英语为主`
- `账号没有可用帖子`
- `近 30 天无更新`
- `文案命中情侣关系词 "<keyword>"`

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
- 维护者排查导出字段时，先回 `config/field_mapping.json` 和 [`docs/field_dictionary.md`](../field_dictionary.md) 找 `upload_metadata.*`、`instagram_api.*` 的实际来源，再看 `backend/app.py` 的导出拼装。

---

## 当前未接入主链路的备用通用逻辑

代码中仍保留 `check_instagram(data)`，但当前批量初筛不走这条链路。该逻辑内容如下：

| 检查项 | JSON 字段路径 | 规则 |
| :--- | :--- | :--- |
| 外链硬拒 | `externalUrls[].url` | 命中 `temu`, `shein`, `aliexpress`, `wish` 直接 Reject |
| 简介/文案硬拒 | `biography`, `latestPosts[].caption`（前 20 条） | 命中 `temu`, `shein`, `aliexpress`, `wish`, `pregnancy`, `pregnant`, `baby coming`, `expecting` 直接 Reject |
| 弱语义提示 | `biography`, `latestPosts[].caption` | 命中 `$1`, `baby`, `momlife`, `motherhood` 时不直接拒绝，而是写入 `soft_flags` |
| 活跃度 | `latestPosts[].timestamp` | 最近一条帖子距今超过 30 天则 Reject |
| 视觉封面 | `latestPosts[].displayUrl`（前 9 条） | 交给视觉复核 |

如果未来切回通用版，需要同步修改主链路与本 PRD。

---

## 视觉复核阶段

初筛通过后，Instagram 会把封面图交给视觉模型做第二轮判断。当前视觉阶段主要负责：

1. 画面环境是否整洁、明亮、有生活感
2. 是否过度商业化、摆拍感过强
3. 是否存在大面积纹身、过度性感暴露
4. 是否是满屏晒娃型账号
5. 是否属于优先垂类，如医生、皮肤科、瑜伽、普拉提、职场女性等

---

## 维护要求

凡是以下内容发生变化，必须在同一次提交中同步更新本文件：

- `check_instagram_custom` 的阈值、字段、关键词或拒绝原因
- 主链路从 `check_instagram_custom` 切换到 `check_instagram`
- 地区判定从规则改为大模型或规则 + 大模型双层判断
