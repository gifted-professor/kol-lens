# 标准化筛号需求模板 Contract

- 模板版本：`v1-sectioned`
- Excel 路径：`docs/templates/标准化筛号需求模板-v1.xlsx`
- 新版分区式需求主表是唯一默认入口。
- source of truth 只来自主表固定区块和固定单元格。
- `compiler_preview` 只作为输出预览，不作为输入来源。
- 旧版行式模板只保留兼容读取，不再继续扩展功能。

## Sheet 结构

| Sheet | 角色 | 输入 / 输出 | 说明 |
| --- | --- | --- | --- |
| 需求主表 | 主表 | 输入 | 品牌方 / 内部统一填写入口。 |
| compiler_preview | 预览表 | 输出 | 编译后系统生成的内部规则预览。 |
| 系统下拉选项 | 隐藏选项 | 系统 | 下拉选项源。 |

## A. 基本信息

- 区块标题位置：`A4:C4`

| 字段 | value cell | note cell | 必填 | 类型 | 默认值 | 编译规则 | 校验失败时错误 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 项目名称 | `B5` | `C5` | 是 | string | - | metadata only | 项目名称不能为空 |
| 品牌 / 产品 | `B6` | `C6` | 是 | string | - | metadata only | 品牌 / 产品不能为空 |
| 适用平台 | `B7` | `C7` | 是 | choice | 两者 | controls per-rule platform intersection | 适用平台 只能填写 TikTok、Instagram 或 两者 |
| 审核目标 | `B8` | `C8` | 是 | string | - | metadata only | 审核目标不能为空 |
| 参考账号 | `B9` | `C9` | 否 | list | - | metadata only | 参考账号格式无效 |
| 反例账号 | `B10` | `C10` | 否 | list | - | metadata only | 反例账号格式无效 |
| 备注 | `B11` | `C11` | 否 | string | - | metadata only | - |

## B. 步骤1：基础资质审核

- 区块标题位置：`A14:C14`

| 字段 | value cell | note cell | 必填 | 类型 | 默认值 | 编译规则 | 校验失败时错误 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 地区要求 | `B15` | `C15` | 否 | list | - | compile to Instagram-only region_gate rule | 地区要求格式无效 |
| 语言要求 | `B16` | `C16` | 否 | list | - | compile to Instagram-only language_gate rule | 语言要求格式无效 |
| 检查位置 | `B17` | `C17` | 否 | choice | 主页资料 | metadata for qualification rules | 检查位置 只能填写 主页资料 或 内容整体 |
| 不符合时处理 | `B18` | `C18` | 否 | choice | 直接不通过 | qualification fail action | 不符合时处理 只能填写 直接不通过 或 转人工 |
| 补充说明 | `B19` | `C19` | 否 | string | - | metadata only | - |

## C. 步骤2：数据审核

- 区块标题位置：`A22:C22`

| 字段 | value cell | note cell | 必填 | 类型 | 默认值 | 编译规则 | 校验失败时错误 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 取样视频数 | `B23` | `C23` | 否 | int | 50 | shared window size for view metrics | 取样视频数 必须是整数 |
| 平均播放量阈值 | `B24` | `C24` | 否 | int | - | compile to TikTok-only view_count_mean rule | 平均播放量阈值 必须是整数 |
| 中位数播放量阈值 | `B25` | `C25` | 否 | int | - | compile to TikTok-only view_count_median rule | 中位数播放量阈值 必须是整数 |
| 粉丝数阈值（可选） | `B26` | `C26` | 否 | int | - | compile to follower_count rule | 粉丝数阈值 必须是整数 |
| 最近活跃要求（天，可选） | `B27` | `C27` | 否 | int | - | compile to activity_recency_days rule | 最近活跃要求 必须是整数 |
| 判定关系 | `B28` | `C28` | 否 | choice | 同时满足 | data step aggregation logic | 判定关系 只能填写 同时满足 或 任一满足 |
| 不符合时处理 | `B29` | `C29` | 否 | choice | 直接不通过 | data step fail action | 不符合时处理 只能填写 直接不通过 或 转人工 |
| 补充说明 | `B30` | `C30` | 否 | string | - | metadata only | - |

## D. 步骤3：内容 / 视觉审核

- 区块标题位置：`A33:C33`

| 字段 | value cell | note cell | 必填 | 类型 | 默认值 | 编译规则 | 校验失败时错误 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 查看封面数量 | `B34` | `C34` | 否 | int | 18 | shared visual cover count | 查看封面数量 必须是整数 |
| 至少命中几类特征 | `B35` | `C35` | 否 | int | 1 | visual step group threshold | 至少命中几类特征 必须是整数 |
| 补充说明 | `B36` | `C36` | 否 | string | - | metadata only | - |

### 自动化特征固定行

| 特征 | value cell | note cell | 编译规则 |
| --- | --- | --- | --- |
| 多人互动 | `B38` | `C38` | 编译为 `visual_feature_group.features[]` 成员 |
| Speaking-led | `B39` | `C39` | 编译为 `visual_feature_group.features[]` 成员 |
| 真实生活场景 | `B40` | `C40` | 编译为 `visual_feature_group.features[]` 成员 |
| 孩子互动 | `B41` | `C41` | 编译为 `visual_feature_group.features[]` 成员 |
| 产品展示 | `B42` | `C42` | 编译为 `visual_feature_group.features[]` 成员 |
| 户外庭院 | `B43` | `C43` | 编译为 `visual_feature_group.features[]` 成员 |
| 宠物互动 | `B44` | `C44` | 编译为 `visual_feature_group.features[]` 成员 |

- `鲜明人设 / 垂直 niche` 不在此区块，统一放到 `F. 人工判断项 / 合规提醒`。

## E. 步骤4：排除项审核

- 区块标题位置：`A47:C47`

| 字段 | value cell | note cell | 必填 | 类型 | 默认值 | 编译规则 | 校验失败时错误 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 文本关键词排除 | `B48` | `C48` | 否 | list | - | compile to content keyword blocklist | 文本关键词排除 格式无效 |
| 关系词排除 | `B49` | `C49` | 否 | list | - | compile to relationship keyword blocklist | 关系词排除 格式无效 |
| 美妆内容占比阈值（%） | `B50` | `C50` | 否 | int | - | compile to content_keyword_ratio threshold | 美妆内容占比阈值 必须是整数 |
| 多人跳舞占比阈值（%） | `B51` | `C51` | 否 | int | - | compile to visual risk ratio | 多人跳舞占比阈值 必须是整数 |
| 自拍 / 情侣出镜占比阈值（%） | `B52` | `C52` | 否 | int | - | compile to selfie_or_couple_ratio rule | 自拍 / 情侣出镜占比阈值 必须是整数 |
| 绿幕是否直接排除 | `B53` | `C53` | 否 | choice | 否 | compile to green_screen must_not_appear rule | 绿幕是否直接排除 只能填写 是 或 否 |
| 其他排除项 | `B54` | `C54` | 否 | string | - | manual note only | - |
| 补充说明 | `B55` | `C55` | 否 | string | - | metadata only | - |

## F. 人工判断项 / 合规提醒

- 区块标题位置：`A58:C58`

| 字段 | value cell | note cell | 必填 | 类型 | 默认值 | 编译规则 | 校验失败时错误 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 评论区 emoji 异常 | `B59` | `C59` | 否 | choice | 否 | manual review item only | 评论区 emoji 异常 只能填写 是 或 否 |
| 鲜明人设 / 垂直 niche | `B60` | `C60` | 否 | choice | 否 | manual review item only | 鲜明人设 / 垂直 niche 只能填写 是 或 否 |
| 完整视频内容判断 | `B61` | `C61` | 否 | choice | 否 | manual review item only | 完整视频内容判断 只能填写 是 或 否 |
| 其他主观判断项 | `B62` | `C62` | 否 | string | - | manual review item only | - |
| 受保护属性相关判断 | `B63` | `C63` | 否 | string | - | compliance note only; never compile | - |
| 补充说明 | `B64` | `C64` | 否 | string | - | metadata only | - |

## G. 最终判定逻辑

- 区块标题位置：`A67:C67`

| 字段 | value cell | note cell | 必填 | 类型 | 默认值 | 编译规则 | 校验失败时错误 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 必须满足哪些步骤 | `B68` | `C68` | 是 | step_list | 步骤1：基础资质审核,步骤2：数据审核,步骤3：内容 / 视觉审核 | final_logic.must_pass_steps | 必须满足哪些步骤 只能填写固定步骤名称，并使用逗号分隔 |
| 任一触发即不通过的项 | `B69` | `C69` | 是 | step_list | 步骤4：排除项审核 | final_logic.reject_if_any_steps | 任一触发即不通过的项 只能填写固定步骤名称，并使用逗号分隔 |
| 人工判断项命中时如何处理 | `B70` | `C70` | 是 | choice | 转人工 | final_logic.manual_hit_action | 人工判断项命中时如何处理 只能填写 转人工 或 仅提醒 |
| 满足条件时输出 | `B71` | `C71` | 是 | choice | 通过 | final_logic.success_output | 满足条件时输出 只能填写 通过 / 不通过 / 转人工 |
| 不满足时输出 | `B72` | `C72` | 是 | choice | 不通过 | final_logic.failure_output | 不满足时输出 只能填写 通过 / 不通过 / 转人工 |
| 补充说明 | `B73` | `C73` | 否 | string | - | metadata only | - |

## 编译约束

- `内容 / 视觉审核` 只保留封面能稳定看出来的自动化项。
- 受保护属性相关内容永远不进入 `rulespec.json`，只保留为 `structured_requirement.json` 的合规提醒。
- 自由文本的 `其他排除项` 与 `其他主观判断项` 不自动编译为 RuleSpec，只保留为人工项 / 备注。
- `compiler_preview` 由主表编译生成，不反向参与解析。

## 编译输出

| 文件 / 产物 | 内容 |
| --- | --- |
| `structured_requirement.json` | 主表固定单元格解析后的结构化需求。 |
| `rulespec.json` | 仅包含稳定可自动化项的 RuleSpec。 |
| `compiled_requirement_workbook.xlsx` | 附带 `compiler_preview` 预览 sheet 的编译结果工作簿。 |

## 兼容策略

- 旧版行式模板仍可通过 `parse` 读取，但不再作为默认生成模板。
- 新功能只围绕分区式主表扩展。
