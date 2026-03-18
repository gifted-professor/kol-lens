# 字段字典

> 此文件由 `scripts/build_field_dictionary.py` 根据 `config/field_mapping.json` 生成。
> 最后同步：2026-03-18

## 说明

- 这份字典是 PRD 和代码之间的字段总览，目的是回答“有哪些字段、来自哪里、当前有没有被初筛读取”。
- `主链路` 表示当前批量初筛真实会读取该字段。
- `备用逻辑` 表示代码里还有备用/旧逻辑会读取该字段，但不是当前主入口。
- `未使用` 表示当前只存档或导出，不参与初筛判断。

## 上传表字段（Upload Metadata）

上传 Excel 经 backend/app.py 归一化后的元数据字段。Phase 2 默认上传合同已固定为 canonical creator workbook，最少需要 `Platform` 与 `@username`。Phase 4 要求 raw/test/prescreen/image/final 导出的字段来源仍能从这里追溯。

内容列候选：`content`, `url`, `profile_url`, `profile_link`, `link`, `URL`

| 字段名 | 类型 | 原始列名 | 说明 | 示例值 | 当前使用 |
| --- | --- | --- | --- | --- | --- |
| `url` | `string` | URL, content, url, profile_url, profile_link, link | 博主主页链接。若上传表未提供 URL，后端会基于 `Platform + @username` 生成稳定主页地址。 | `https://www.instagram.com/nuritheedoll/` | 主链路 |
| `source_filename` | `string` | - | 上传源文件名，用于 raw/test/prescreen/image/final 导出的溯源和 audit handoff 对账。 | `kol_emails_2026-03-16.xlsx` | 未使用 |
| `nickname` | `string` | nickname, name, display_name | 博主昵称 / 展示名。 | `NURI` | 未使用 |
| `description` | `string` | Description, bio | 上传表自带的人设 / 简介文本，现阶段只存档，未参与初筛。 | `PR/social: kiwi@stride-social.com` | 未使用 |
| `handle` | `string` | @username, username, handle | 账号 handle，用于与采集结果匹配。 | `nuritheedoll` | 主链路 |
| `region` | `string` | Region | 地区 / 国家简写，当前 Instagram 主链路优先使用它进行 US/CA 判断。 | `US` | 主链路 |
| `language` | `string` | Language | 语言代码，当前 Instagram 主链路优先用于英语判断。 | `en` | 主链路 |
| `platform` | `string` | Platform | 平台名，用于把行路由到 Instagram / TikTok / YouTube；归一化后会保存为小写内部值。 | `instagram` | 未使用 |
| `followers` | `number` | Followers | 上传表粉丝数，当前主链路未使用。 | `45663` | 未使用 |
| `avg_views` | `number` | Avg. Views | 上传表平均播放量，当前主链路未使用。 | `298264` | 未使用 |
| `avg_likes` | `number` | Avg. Likes | 上传表平均点赞量，当前主链路未使用。 | `5347` | 未使用 |
| `avg_comments` | `number` | Avg. Comments | 上传表平均评论量，当前主链路未使用。 | `47` | 未使用 |
| `avg_collects` | `number` | Avg. Collects | 上传表平均收藏量，当前主链路未使用。 | `0` | 未使用 |
| `tags` | `string` | Tags | 上传表打标字段，当前主链路未使用。 | `` | 未使用 |
| `email` | `string` | Email | 联系邮箱，只用于运营记录 / 导出。 | `kiwi@stride-social.com` | 未使用 |
| `email_send_status` | `string` | Email Send Status | 邮件发送状态，只记录，不参与初筛。 | `` | 未使用 |
| `yt_email_button` | `string` | YT Email Button | YouTube 邮箱按钮状态，只记录，不参与初筛。 | `` | 未使用 |
| `last_post` | `string` | Last Post | 上传表最近发帖日期，当前主链路未使用。 | `2026-03-15` | 未使用 |
| `posts_7d` | `number` | Posts (7d) | 上传表 7 天内发帖数，当前主链路未使用。 | `11` | 未使用 |
| `posts_30d` | `number` | Posts (30d) | 上传表 30 天内发帖数，当前主链路未使用。 | `11` | 未使用 |

## Instagram API 字段

Apify instagram-profile-scraper 返回的博主对象。

### 主页级字段

| 字段路径 | 类型 | 说明 | 示例值 | 当前使用 |
| --- | --- | --- | --- | --- |
| `inputUrl` | `string` | 采集输入的原始 URL。 | `https://www.instagram.com/nuritheedoll` | 未使用 |
| `id` | `string` | Instagram 账号 ID。 | `12345678901234567` | 未使用 |
| `username` | `string` | 账号 handle，用于合并审核结果与输出展示。 | `nuritheedoll` | 主链路 |
| `url` | `string` | 账号主页 URL，用于与上传元数据合并。 | `https://www.instagram.com/nuritheedoll` | 主链路 |
| `fullName` | `string` | 全名 / 昵称，当前未使用。 | `Nuri Example` | 未使用 |
| `biography` | `string` | 个人简介文本；当前主链路用于地区 / 语言兜底，备用逻辑还会用于禁词检查。 | `Los Angeles, CA. Email for collabs.` | 主链路 |
| `externalUrls[].url` | `array<string>` | 外链 URL 列表，只在备用通用逻辑中用于竞品 / 低价词排雷。 | `["https://example.com/shop"]` | 备用逻辑 |
| `externalUrl` | `string` | 主 externalUrl 字段，当前未被初筛使用。 | `https://example.com` | 未使用 |
| `externalUrlShimmed` | `string` | Instagram shimmed 外链，当前未使用。 | `https://l.instagram.com/?u=https%3A%2F%2Fexample.com` | 未使用 |
| `followersCount` | `number` | 粉丝数，旧版 SOP 用过，当前已移除。 | `234898` | 未使用 |
| `followsCount` | `number` | 关注数，当前未使用。 | `4021` | 未使用 |
| `hasChannel` | `boolean` | 是否有 channel，当前未使用。 | `False` | 未使用 |
| `highlightReelCount` | `number` | 精选集数量，当前未使用。 | `0` | 未使用 |
| `isBusinessAccount` | `boolean` | 是否商业账号，当前未使用。 | `False` | 未使用 |
| `businessCategoryName` | `string` | 商业账号分类，当前未使用。 | `` | 未使用 |
| `joinedRecently` | `boolean` | 是否近期创号，当前未使用。 | `False` | 未使用 |
| `private` | `boolean` | 是否私密账号，当前未使用。 | `False` | 未使用 |
| `verified` | `boolean` | 是否蓝 V，当前未使用。 | `False` | 未使用 |
| `profilePicUrl` | `string` | 头像 URL，当前未使用。 | `https://scontent.example/avatar.jpg` | 未使用 |
| `profilePicUrlHD` | `string` | 高清头像 URL，当前未使用。 | `https://scontent.example/avatar_hd.jpg` | 未使用 |
| `igtvVideoCount` | `number` | IGTV 数量，当前未使用。 | `0` | 未使用 |
| `relatedProfiles` | `array<object>` | 相关账号列表，当前未使用。 | `[]` | 未使用 |
| `latestIgtvVideos` | `array<object>` | 最新 IGTV 列表，当前未使用。 | `[]` | 未使用 |
| `postsCount` | `number` | 总帖子数，当前未使用。 | `3246` | 未使用 |
| `fbid` | `string` | FBID，当前未使用。 | `17841400000000000` | 未使用 |
| `addressStreet` | `string` | 商业地址街道信息，可被地区识别逻辑读取。 | `` | 主链路 |
| `cityName` | `string` | 城市名，可被地区识别逻辑读取。 | `` | 主链路 |
| `location` | `string` | 位置文本，可被地区识别逻辑读取。 | `` | 主链路 |
| `businessAddressJson` | `object` | 商业地址 JSON，会被拆成文本参与地区识别。 | `{}` | 主链路 |

### 帖子级字段（latestPosts[]）

| 字段路径 | 类型 | 说明 | 示例值 | 当前使用 |
| --- | --- | --- | --- | --- |
| `latestPosts[].id` | `string` | 帖子 ID，当前未使用。 | `3846237907589569843` | 未使用 |
| `latestPosts[].timestamp` | `string` | 帖子发布时间，用于 30 天活跃度判断。 | `2026-03-05T16:15:00.000Z` | 主链路 |
| `latestPosts[].caption` | `string` | 帖子文案，当前主链路用于 relationship 词检测，备用逻辑用于禁词检测。 | `Welcome back to Bali...` | 主链路 |
| `latestPosts[].displayUrl` | `string` | 封面图 URL，交给视觉复核。 | `https://scontent.example/post.jpg` | 主链路 |
| `latestPosts[].likesCount` | `number` | 点赞数，当前未使用。 | `279` | 未使用 |
| `latestPosts[].commentsCount` | `number` | 评论数，当前未使用。 | `114` | 未使用 |
| `latestPosts[].videoViewCount` | `number` | 视频播放数，当前未使用。 | `3303` | 未使用 |
| `latestPosts[].type` | `string` | 帖子类型（Video/Image/Sidecar），当前未使用。 | `Video` | 未使用 |
| `latestPosts[].hashtags` | `array<object>` | 话题标签列表，当前未使用。 | `[]` | 未使用 |
| `latestPosts[].mentions` | `array<string>` | @ 提及列表，当前未使用。 | `["level8_official"]` | 未使用 |
| `latestPosts[].childPosts` | `array<object>` | 多张贴文子项，当前未使用。 | `[]` | 未使用 |
| `latestPosts[].images` | `array<object>` | 多张图列表，当前未使用。 | `[]` | 未使用 |
| `latestPosts[].alt` | `string` | 替代文本，当前未使用。 | `` | 未使用 |
| `latestPosts[].url` | `string` | 帖子详情 URL，当前未使用。 | `https://www.instagram.com/p/ABC123` | 未使用 |
| `latestPosts[].videoUrl` | `string` | 视频 URL，当前未使用。 | `https://instagram.fvideo.example/video.mp4` | 未使用 |
| `latestPosts[].ownerId` | `string` | 帖子 owner id，当前未使用。 | `1234567890` | 未使用 |
| `latestPosts[].ownerUsername` | `string` | 帖子 owner username，当前未使用。 | `nuritheedoll` | 未使用 |
| `latestPosts[].productType` | `string` | 帖子 productType，当前未使用。 | `clips` | 未使用 |
| `latestPosts[].shortCode` | `string` | Instagram shortcode，当前未使用。 | `ABC123` | 未使用 |
| `latestPosts[].dimensionsHeight` | `number` | 图像高度，当前未使用。 | `1350` | 未使用 |
| `latestPosts[].dimensionsWidth` | `number` | 图像宽度，当前未使用。 | `1080` | 未使用 |
| `latestPosts[].isCommentsDisabled` | `boolean` | 是否关闭评论，当前未使用。 | `False` | 未使用 |

### 当前代码中的 Instagram 流程

| 流程 ID | 函数 | 状态 | 说明 | 当前读取字段 |
| --- | --- | --- | --- | --- |
| `instagram_custom` | `check_instagram_custom` | `active` | 当前批量主链路，核心是上传 Region/Language + API 资料兜底 + 近 100 条 caption 关系词拦截；输出的 profile_reviews + covers 会继续流向 prescreen/image/final-review 导出。 | `upload_metadata.url`, `upload_metadata.handle`, `upload_metadata.region`, `upload_metadata.language`, `instagram_api.username`, `instagram_api.url`, `instagram_api.biography`, `instagram_api.addressStreet`, `instagram_api.cityName`, `instagram_api.location`, `instagram_api.businessAddressJson`, `instagram_api.latestPosts[].timestamp`, `instagram_api.latestPosts[].caption`, `instagram_api.latestPosts[].displayUrl` |
| `instagram_generic` | `check_instagram` | `standby` | 备用通用逻辑，包含 externalUrls 、biography 、caption 的竞品 / 弱语义词检查。 | `instagram_api.externalUrls[].url`, `instagram_api.biography`, `instagram_api.latestPosts[].timestamp`, `instagram_api.latestPosts[].caption`, `instagram_api.latestPosts[].displayUrl` |

## TikTok API 字段

Apify TikTok 爬虫返回的视频数组，博主级信息重复嵌在 authorMeta 里。

### 作者级字段（authorMeta）

| 字段路径 | 类型 | 说明 | 示例值 | 当前使用 |
| --- | --- | --- | --- | --- |
| `authorMeta.id` | `string` | 作者 ID。 | `6896321602818278405` | 未使用 |
| `authorMeta.name` | `string` | 账号 handle，用于按博主分组。 | `trutech` | 主链路 |
| `authorMeta.profileUrl` | `string` | 主页 URL，用于与上传元数据合并。 | `https://www.tiktok.com/@trutech` | 主链路 |
| `authorMeta.nickName` | `string` | 昵称，当前未使用。 | `Trutech | Technology Reviews` | 未使用 |
| `authorMeta.verified` | `boolean` | 是否认证，当前未使用。 | `False` | 未使用 |
| `authorMeta.signature` | `string` | 个人简介，只在备用通用 TikTok 逻辑中作为禁词检查来源。 | `We make tech videos. Shop feed below.` | 备用逻辑 |
| `authorMeta.bioLink` | `string` | 简介外链，只在备用通用 TikTok 逻辑中作为竞品 / 弱语义词检查来源。 | `Linktr.ee/trutechco` | 备用逻辑 |
| `authorMeta.avatar` | `string` | 头像 URL，当前未使用。 | `https://p16-common-sign.tiktokcdn-us.com/avatar.jpeg` | 未使用 |
| `authorMeta.originalAvatarUrl` | `string` | 原始头像 URL，当前未使用。 | `https://p16-common-sign.tiktokcdn-us.com/avatar.jpeg` | 未使用 |
| `authorMeta.createTime` | `number` | 创号时间戳，当前未使用。 | `1605675126` | 未使用 |
| `authorMeta.following` | `number` | 关注数，当前未使用。 | `555` | 未使用 |
| `authorMeta.friends` | `number` | 好友数，当前未使用。 | `43` | 未使用 |
| `authorMeta.fans` | `number` | 粉丝数，旧版 SOP 可能用过，当前未使用。 | `480200` | 未使用 |
| `authorMeta.heart` | `number` | 总获赞数，当前未使用。 | `18500000` | 未使用 |
| `authorMeta.video` | `number` | 总视频数，当前未使用。 | `736` | 未使用 |
| `authorMeta.digg` | `number` | 点赞 / digg 数，当前未使用。 | `0` | 未使用 |
| `authorMeta.privateAccount` | `boolean` | 是否私密账号，当前未使用。 | `False` | 未使用 |
| `authorMeta.ttSeller` | `boolean` | 是否 TikTok seller，当前未使用。 | `False` | 未使用 |
| `authorMeta.roomId` | `string` | 直播 room id，当前未使用。 | `` | 未使用 |
| `authorMeta.commerceUserInfo` | `object` | 商业账号信息，当前未使用。 | `{"commerceUser": false}` | 未使用 |

### 视频级字段

| 字段路径 | 类型 | 说明 | 示例值 | 当前使用 |
| --- | --- | --- | --- | --- |
| `id` | `string` | 视频 ID，当前未使用。 | `7614410220470635807` | 未使用 |
| `input` | `string` | 采集输入值，当前未使用。 | `https://www.tiktok.com/@trutech` | 未使用 |
| `text` | `string` | 视频文案；当前 Tapo 主链路用于美妆比例判断，备用逻辑用于禁词检查。 | `This mount has 200lbs pull force...` | 主链路 |
| `textLanguage` | `string` | 文案语言，当前未使用。 | `en` | 未使用 |
| `createTime` | `number` | 发布时间戳，当前未使用。 | `1772868047` | 未使用 |
| `createTimeISO` | `string` | 视频发布时间，只在备用通用 TikTok 逻辑中做 30 天活跃度检查。 | `2026-03-07T07:20:47.000Z` | 备用逻辑 |
| `diggCount` | `number` | 点赞数，当前未使用。 | `1173` | 未使用 |
| `shareCount` | `number` | 分享数，当前未使用。 | `41` | 未使用 |
| `repostCount` | `number` | 转发数，当前未使用。 | `0` | 未使用 |
| `playCount` | `number` | 播放数，当前 Tapo 主链路用于最近 50 条的均值 + 中位数门槛。 | `13600` | 主链路 |
| `collectCount` | `number` | 收藏数，当前未使用。 | `126` | 未使用 |
| `commentCount` | `number` | 评论数，当前未使用。 | `9` | 未使用 |
| `hashtags[].name` | `array<string>` | 话题标签，当前 Tapo 主链路用于美妆比例判断，备用逻辑用于禁词检测。 | `["parts4star"]` | 主链路 |
| `isAd` | `boolean` | 是否广告，当前未使用。 | `False` | 未使用 |
| `isPinned` | `boolean` | 是否置顶，当前未使用。 | `False` | 未使用 |
| `isSponsored` | `boolean` | 是否 sponsored，当前未使用。 | `False` | 未使用 |
| `isSlideshow` | `boolean` | 是否图文轮播，当前主链路用于选择 slideshow 封面来源。 | `False` | 主链路 |
| `fromProfileSection` | `string` | 抓取来源 section，当前未使用。 | `posts` | 未使用 |
| `commentsDatasetUrl` | `string` | 评论 dataset URL，当前未使用。 | `https://api.apify.com/v2/datasets/xxx/items` | 未使用 |
| `webVideoUrl` | `string` | 视频页 URL，当前未使用。 | `https://www.tiktok.com/@trutech/video/7614410220470635807` | 未使用 |
| `mentions` | `array<object>` | @ 提及列表，当前未使用。 | `[]` | 未使用 |
| `detailedMentions` | `array<object>` | 详细 mentions 列表，当前未使用。 | `[]` | 未使用 |
| `mediaUrls` | `array<string>` | 媒体 URL 列表，当前未使用。 | `[]` | 未使用 |
| `effectStickers` | `array<object>` | 特效贴纸列表，当前未使用。 | `[]` | 未使用 |
| `musicMeta.musicName` | `string` | 背景音乐名称，当前未使用。 | `original sound` | 未使用 |
| `musicMeta.musicAuthor` | `string` | 音乐作者，当前未使用。 | `Trutech | Technology Reviews` | 未使用 |
| `musicMeta.musicOriginal` | `boolean` | 是否 original sound，当前未使用。 | `True` | 未使用 |
| `musicMeta.playUrl` | `string` | 音乐 play url，当前未使用。 | `https://v16m.tiktokcdn-us.com/audio.mp3` | 未使用 |
| `musicMeta.coverMediumUrl` | `string` | 音乐 cover url，当前未使用。 | `https://p16-common-sign.tiktokcdn-us.com/cover.jpeg` | 未使用 |
| `musicMeta.originalCoverMediumUrl` | `string` | 音乐 original cover url，当前未使用。 | `https://p16-common-sign.tiktokcdn-us.com/cover.jpeg` | 未使用 |
| `musicMeta.musicId` | `string` | 音乐 ID，当前未使用。 | `7614410142720756510` | 未使用 |
| `videoMeta.height` | `number` | 视频高度，当前未使用。 | `1280` | 未使用 |
| `videoMeta.width` | `number` | 视频宽度，当前未使用。 | `720` | 未使用 |
| `videoMeta.duration` | `number` | 视频时长，当前未使用。 | `43` | 未使用 |
| `videoMeta.coverUrl` | `string` | 普通封面 URL，当前主链路可作为视觉复核封面来源。 | `https://p19-common-sign.tiktokcdn-us.com/cover.image` | 主链路 |
| `videoMeta.originalCoverUrl` | `string` | 原始封面 URL，当前主链路优先使用它做视觉复核封面。 | `https://p19-common-sign.tiktokcdn-us.com/original-cover.image` | 主链路 |
| `videoMeta.definition` | `string` | 分辨率标记，当前未使用。 | `720p` | 未使用 |
| `videoMeta.format` | `string` | 媒体格式，当前未使用。 | `mp4` | 未使用 |
| `videoMeta.subtitleLinks[].language` | `array<string>` | 字幕语言列表，当前未使用。 | `["eng-US"]` | 未使用 |
| `videoMeta.subtitleLinks[].downloadLink` | `array<string>` | 字幕下载链接，当前未使用。 | `["https://v16m-webapp.tiktokcdn-us.com/subtitle.mp4"]` | 未使用 |
| `videoMeta.subtitleLinks[].source` | `array<string>` | 字幕来源类型，当前未使用。 | `["ASR"]` | 未使用 |
| `videoMeta.subtitleLinks[].sourceUnabbreviated` | `array<string>` | 字幕来源全称，当前未使用。 | `["automatic speech recognition"]` | 未使用 |
| `videoMeta.subtitleLinks[].version` | `array<string>` | 字幕版本，当前未使用。 | `["1:big_caption"]` | 未使用 |
| `videoMeta.subtitleLinks[].tiktokLink` | `array<string>` | 字幕 / 视频资源链接，当前未使用。 | `["https://v16m-webapp.tiktokcdn-us.com/video.mp4"]` | 未使用 |
| `videoMeta.transcriptionLink` | `string` | 转录文本链接，当前未使用。 | `null` | 未使用 |
| `slideshowImageLinks[].tiktokLink` | `array<string>` | 图文轮播的首张图链接，当前主链路在 isSlideshow=true 时会当作封面输出。 | `["https://p16-sign.tiktokcdn-us.com/slideshow.image"]` | 主链路 |

### 当前代码中的 TikTok 流程

| 流程 ID | 函数 | 状态 | 说明 | 当前读取字段 |
| --- | --- | --- | --- | --- |
| `tiktok_tapo` | `check_tiktok_tapo` | `active` | 当前 TikTok 批量主链路，核心是播放量门槛 + 美妆内容占比 + 封面提取；输出的 profile_reviews + covers 会继续流向 prescreen/image/final-review 导出。 | `tiktok_api.authorMeta.name`, `tiktok_api.authorMeta.profileUrl`, `tiktok_api.playCount`, `tiktok_api.text`, `tiktok_api.hashtags[].name`, `tiktok_api.isSlideshow`, `tiktok_api.slideshowImageLinks[].tiktokLink`, `tiktok_api.videoMeta.originalCoverUrl`, `tiktok_api.videoMeta.coverUrl` |
| `tiktok_generic` | `check_tiktok` | `standby` | 备用通用逻辑，包含 createTimeISO 活跃度、bioLink 外链禁词、signature/text/hashtags 禁词检查。 | `tiktok_api.authorMeta.name`, `tiktok_api.authorMeta.bioLink`, `tiktok_api.authorMeta.signature`, `tiktok_api.createTimeISO`, `tiktok_api.text`, `tiktok_api.hashtags[].name`, `tiktok_api.isSlideshow`, `tiktok_api.slideshowImageLinks[].tiktokLink`, `tiktok_api.videoMeta.originalCoverUrl`, `tiktok_api.videoMeta.coverUrl` |

## 维护规则

- 改 `backend/app.py` 的上传字段归一化逻辑时，要同步更新 `config/field_mapping.json` 并重新生成本文件。
- 改 `scripts/data_cleaner.py` 的主链路字段读取、关键词、阈值或入口函数时，要同步更新本文件和对应平台 PRD。
- 新增平台或新增大模型前置判断时，先在字典里补字段，再改规则。

