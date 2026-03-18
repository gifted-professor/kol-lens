# 三平台筛号适配说明（Upload Metadata + API Evidence）

> 日期：2026-03-18
> 目的：把 `标准化筛号需求模板-v1` 落到 TikTok / Instagram / YouTube 三个平台的现有上传表与 API 返回字段上，形成可直接进入适配阶段的实现基线。

## 1. 范围与目标

本说明只回答一个问题：

在当前仓库已经存在的两类数据源基础上，三个平台分别能用哪些字段完成初筛与视觉复核适配，哪些项可以稳定自动化，哪些项只能部分支持，哪些项暂时不能作为标准化自动门槛。

本说明默认使用两类输入：

- 上传表归一化后的 `upload_metadata`
- Apify / 平台 API 返回的原始结构化数据

本说明不引入新的外部数据源，不假设评论正文、画像、地域库或视频内容级 OCR/ASR 已接入。

## 2. 统一数据源优先级

为了让三平台进入同一套适配合同，建议统一采用以下优先级：

1. `upload_metadata` 中由运营上传并确认的字段
2. 平台 API 中稳定、字段语义明确、样本覆盖稳定的字段
3. 平台 API 中启发式、覆盖不完整或语义不稳定的字段
4. 如果规则被填写，但当前证据不足以稳定判断，则输出 `manual_review` 或 `unresolved`，不要伪造 Pass / Reject

推荐落地原则：

- `Region`：上传表优先
- `Language`：上传表优先
- 播放量、活跃度、内容文本、外链、付费内容占比：优先使用 API 运行时值
- 导出时必须保留“上传值”和“运行时值”的区分，不能混写

## 3. 模板字段的统一解释

### 3.1 基础资质类

- `地区要求`
  目标是判断该账号是否属于指定区域。
  在三平台统一适配里，默认把上传表 `Region` 作为主证据。

- `语言要求`
  目标是判断账号内容是否以目标语言为主。
  在三平台统一适配里，默认把上传表 `Language` 作为主证据，API 字段只做回退。

### 3.2 数据审核类

- `粉丝数阈值`
  只要平台存在稳定博主级粉丝字段，就可以自动化。

- `平均播放量阈值`
  只有当平台返回的内容级播放量覆盖稳定，且采样规则明确时，才能作为自动化门槛。

- `播放量中位数阈值`
  与平均播放量同理，对原始样本覆盖要求更高。

- `最近活跃要求`
  只要有稳定的最近内容发布时间字段，就可以自动化。

### 3.3 文本 / 排雷类

- `文本关键词排除`
  依赖标题、caption、description、bio 等文本字段。

- `关系词排除`
  依赖 caption / title / description / bio 等文本字段，平台字段越少，可靠性越弱。

- `内容关键词占比`
  依赖最近 N 条内容文本，可自动化，但不同平台文本密度不同。

### 3.4 内容 / 视觉类

以下项不应强行放进“纯 API 字段规则”里，而应明确归到视觉复核阶段：

- 多人互动
- Speaking-led
- 真实生活场景
- 孩子互动
- 产品展示
- 户外庭院
- 宠物互动
- 绿幕
- 自拍 / 情侣占比
- 多人跳舞占比

它们的输入不是结构化 profile 字段，而是 API 返回的封面图 / 缩略图。

## 4. 三平台适配总览

### 4.1 TikTok

#### 当前稳定可用的上传表证据

- `upload_metadata.region`
- `upload_metadata.language`
- `upload_metadata.followers`
- `upload_metadata.avg_views`
- 其他上传业务字段

#### 当前稳定可用的 API 证据

- `authorMeta.fans`
- `createTimeISO`
- `playCount`
- `text`
- `hashtags[].name`
- `authorMeta.signature`
- `authorMeta.bioLink`
- `textLanguage`
- `videoMeta.originalCoverUrl` / `videoMeta.coverUrl`
- `slideshowImageLinks[].tiktokLink`

#### 当前不稳定或不建议作为主门槛的 API 证据

- `locationMeta`
  这是内容级地点，不是稳定的博主地区。
  同一博主不同视频可能出现不同地点。
  样本覆盖也不完整。

#### TikTok 对模板项的支持判断

- `地区要求`
  状态：部分支持
  可行合同：只用上传表 `Region` 做主判断
  不建议：直接把 `locationMeta` 当博主地区

- `语言要求`
  状态：部分支持
  可行合同：上传表 `Language` 优先；若为空，可用 `textLanguage` + 最近内容文本做启发式回退

- `粉丝数阈值`
  状态：支持
  可用字段：`authorMeta.fans`

- `平均播放量阈值`
  状态：支持
  可用字段：最近 N 条 `playCount`

- `播放量中位数阈值`
  状态：支持
  可用字段：最近 N 条 `playCount`

- `最近活跃要求`
  状态：支持
  可用字段：最近一条 `createTimeISO`

- `文本关键词排除`
  状态：支持
  可用字段：`text`、`hashtags[].name`、`authorMeta.signature`

- `关系词排除`
  状态：部分支持
  可用字段：`text`、`hashtags[].name`
  说明：可以做文本命中，但 TikTok 文案密度和关系暴露度不如 Instagram 稳

- `主页外链禁词`
  状态：支持
  可用字段：`authorMeta.bioLink`

- `内容关键词占比`
  状态：支持
  可用字段：最近 N 条 `text` + `hashtags[].name`

- `视觉 / 内容场景类`
  状态：支持，但属于视觉复核，不属于纯结构化初筛
  可用字段：封面图

- `评论区 emoji 异常 / 评论倾向 / 水军`
  状态：不支持
  原因：当前没有评论正文主链路

#### TikTok 结论

TikTok 适配后的主问题不是播放量和活跃度，而是：

- 地区不能靠 API 稳定判断，必须以上传表 `Region` 为主
- 语言只能部分回退到 `textLanguage`
- 评论类与主观语义类不能自动化

### 4.2 Instagram

#### 当前稳定可用的上传表证据

- `upload_metadata.region`
- `upload_metadata.language`
- `upload_metadata.followers`
- `upload_metadata.avg_views`
- 其他上传业务字段

#### 当前稳定可用的 API 证据

- `followersCount`
- `biography`
- `externalUrls[].url`
- `latestPosts[].timestamp`
- `latestPosts[].caption`
- `latestPosts[].displayUrl`

#### 当前不稳定或覆盖不完整的 API 证据

- `latestPosts[].videoViewCount`
  并非所有帖子都有，且图文、图片帖并不统一携带

- 地区相关 profile 字段
  虽然 `addressStreet` / `cityName` / `location` / `businessAddressJson` 可作为回退，但覆盖与格式不完全稳定

#### Instagram 对模板项的支持判断

- `地区要求`
  状态：支持
  合同：上传表 `Region` 优先；若为空，再回退 `biography` / `addressStreet` / `cityName` / `location` / `businessAddressJson`

- `语言要求`
  状态：部分支持到支持之间
  合同：上传表 `Language` 优先；若为空，可回退 `biography` 与最近 caption 的启发式判断

- `粉丝数阈值`
  状态：支持
  可用字段：`followersCount`

- `平均播放量阈值`
  状态：部分支持
  原因：`videoViewCount` 覆盖不完整
  建议：不要把它当 Instagram 的强制标准化硬门槛，除非额外定义覆盖率要求

- `播放量中位数阈值`
  状态：部分支持
  原因同上

- `最近活跃要求`
  状态：支持
  可用字段：`latestPosts[].timestamp`

- `文本关键词排除`
  状态：支持
  可用字段：`biography` + `latestPosts[].caption`

- `关系词排除`
  状态：支持
  可用字段：`latestPosts[].caption`

- `主页外链禁词`
  状态：支持
  可用字段：`externalUrls[].url`

- `内容关键词占比`
  状态：支持
  可用字段：最近 N 条 `caption`

- `视觉 / 内容场景类`
  状态：支持，但属于视觉复核
  可用字段：`latestPosts[].displayUrl`

- `评论区 emoji 异常 / 评论倾向 / 水军`
  状态：不支持
  原因：当前没有评论正文主链路

#### Instagram 结论

Instagram 是三平台里最接近“模板可落地”的，但仍有一个明显短板：

- 播放量均值 / 中位数不能像 TikTok 那样稳定作为统一硬门槛

### 4.3 YouTube

#### 当前稳定可用的上传表证据

- `upload_metadata.region`
- `upload_metadata.language`
- `upload_metadata.followers`
- `upload_metadata.avg_views`
- 其他上传业务字段

#### 当前稳定可用的 API 证据

- `date`
- `title`
- `text`
- `aboutChannelInfo.channelDescription`
- `aboutChannelInfo.channelDescriptionLinks[].url`
- `descriptionLinks[].url`
- `isPaidContent`
- `thumbnailUrl`

#### 当前部分支持或未纳入主合同的 API 证据

- `viewCount`
  字段存在，但当前主链路未作为标准化门槛落地

- `channelLocation`
  有机会作为地区回退，但当前未形成稳定、已审计的统一规则

- 语言判断
  可以从 `title` / `text` 做启发式判断，但未形成稳定主链路

#### YouTube 对模板项的支持判断

- `地区要求`
  状态：部分支持
  合同建议：上传表 `Region` 优先；API `channelLocation` 只能做弱回退

- `语言要求`
  状态：部分支持
  合同建议：上传表 `Language` 优先；若为空，再对 `title` / `text` 做启发式判断

- `粉丝数阈值`
  状态：当前合同下不建议承诺
  原因：现有审计文档和主链路没有把 YouTube 订阅数固定为标准化规则输入

- `平均播放量阈值`
  状态：部分支持
  原因：虽然 `viewCount` 存在，但当前没有审计后的运行时门槛合同

- `播放量中位数阈值`
  状态：部分支持
  原因同上

- `最近活跃要求`
  状态：支持
  可用字段：最近视频 `date`

- `文本关键词排除`
  状态：支持
  可用字段：`title`、`text`、`aboutChannelInfo.channelDescription`

- `关系词排除`
  状态：部分支持
  可用字段：`title`、`text`
  说明：可以做文本命中，但频道文本密度和表达样式不如 Instagram 稳

- `主页外链禁词`
  状态：支持
  可用字段：`aboutChannelInfo.channelDescriptionLinks[].url`

- `视频描述外链禁词`
  状态：支持
  可用字段：`descriptionLinks[].url`

- `内容关键词占比`
  状态：部分支持
  可用字段：`title` + `text`

- `付费内容占比`
  状态：支持
  可用字段：最近 N 条 `isPaidContent`

- `视觉 / 内容场景类`
  状态：支持，但属于视觉复核
  可用字段：`thumbnailUrl`

- `评论区 emoji 异常 / 评论倾向 / 水军`
  状态：不支持
  原因：当前没有评论正文主链路

#### YouTube 结论

YouTube 是三平台里缺口最大的。
它不是完全不能适配，而是：

- 需要强依赖上传表 `Region` / `Language`
- API 在地区、语言、均值 / 中位数播放量这几项上只能部分支持
- 当前主链路虽然能做活跃度、文本排雷、外链排雷、付费内容占比，但还不能承诺完整覆盖模板的所有数据门槛项

## 5. 三平台能力排序

如果以“上传表 + API + 视觉复核”作为整体流程能力来排：

1. Instagram
2. TikTok
3. YouTube

如果以“纯结构化初筛、不依赖视觉模型”来排：

1. Instagram
2. TikTok
3. YouTube

如果以“能否完整覆盖完整版模板”来判断：

- 当前没有任何一个平台可以 100% 完整覆盖所有模板项
- 缺口最小的是 Instagram
- 缺口最大的是 YouTube

## 6. 进入适配阶段前的推荐实现合同

为了避免适配阶段再次卡在语义歧义上，建议直接采用以下合同：

### 6.1 统一字段优先级

- `region`: `upload_metadata.region` > API 回退 > unresolved
- `language`: `upload_metadata.language` > API 回退 > unresolved
- `followers`: API 运行时值优先；上传值仅作对账
- `avg_views` / `median_views`: API 运行时值优先；上传值仅作对账

### 6.2 三平台地区规则

- TikTok：只承诺上传表 `Region`
- Instagram：上传表 `Region` + API 资料字段回退
- YouTube：上传表 `Region` 主判，API `channelLocation` 仅弱回退

### 6.3 三平台语言规则

- TikTok：上传表 `Language` 主判，`textLanguage` 弱回退
- Instagram：上传表 `Language` 主判，`biography` / caption 弱回退
- YouTube：上传表 `Language` 主判，`title` / `text` 弱回退

### 6.4 缺证据时的默认处理

当模板里某项已填写，但平台当前没有足够稳定证据时：

- 推荐默认输出：`manual_review`
- 不推荐默认输出：直接 `Reject`

原因：

- 这是数据能力不足，不是明确不符合
- 直接 Reject 会把“抓不到证据”和“明确不符合”混成一类

### 6.5 视觉项边界

以下项一律归到视觉复核，不进入“纯结构化初筛”：

- 多人互动
- Speaking-led
- 真实生活场景
- 孩子互动
- 产品展示
- 户外庭院
- 宠物互动
- 绿幕
- 自拍 / 情侣占比
- 多人跳舞占比

## 7. 适配阶段的直接实现目标

基于本说明，下一阶段应实现的不是“继续讨论”，而是：

1. 把 `upload_metadata.region` 和 `upload_metadata.language` 升级为三平台统一资格门槛输入
2. 把三平台的 API 字段能力映射成统一规则执行层
3. 明确输出 `pass / reject / manual_review / unresolved`
4. 在导出中保留每项关键判断的 evidence source
5. 保持上传值与运行时值分列导出，不允许混写

## 8. 最终判断

这份说明已经足够作为“三平台标准化筛号适配”的实施基线。

不需要再额外讨论“地区到底看上传还是看 API”这个问题，推荐结论已经固定：

- 三平台地区统一先看上传表 `Region`
- Instagram 可以做 API 回退
- TikTok 不承诺 API 地区
- YouTube 只做弱 API 回退

在这个前提下，适配阶段可以直接开始。
