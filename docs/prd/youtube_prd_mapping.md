# YouTube 数据引擎映射文档 (PRD - YT Module)

## 数据源特征
Apify 返回的 JSON 是一个**视频列表数组 (Array)**。全局频道信息 (Channel Info) 会被重复嵌套在每一个视频节点中。提取全局信息时，直接取数组第一个元素（Index 0）即可。

---

## 🎯 维度一：文本与硬性雷区排查 (Python 物理清洗阶段)

| 检查大类 | JSON 字段路径 | 提取与判定逻辑 |
| :--- | :--- | :--- |
| **品牌合作排雷** | `aboutChannelInfo.channelDescriptionLinks`, `descriptionLinks[].url`, `aboutChannelInfo.channelDescription`, `title`, `text` | 极度致命！遍历全局外链、单条视频外链、频道简介、及视频标题与描述。发现 `temu`, `aliexpress`, `shein`, `wish` $\rightarrow$ **直接 Reject**。|
| **怀孕达人排雷** | `aboutChannelInfo.channelDescription`, `title`, `text` | 扫描频道简介与视频描述，寻找 `pregnancy`, `pregnant`, `baby coming`, `expecting`。命中 $\rightarrow$ **优先 Reject**。 |
| **弱语义文本提示** | `aboutChannelInfo.channelDescription`, `title`, `text` | 若命中 `$1`, `baby`, `momlife`, `motherhood` 这类弱语义词，不直接 Reject，而是记为 **待复核文本提示**，返回给人工/大模型复核。 |
| **账号活跃度** | `[0].date` | 解析最新一条视频的 ISO 时间。若距今超过 3 个月未更新 $\rightarrow$ **绝对 Reject**；若当月无更新 $\rightarrow$ **谨慎提报（标记）**。 |

---

## 👁️ 维度二：大模型视觉与语境判定 (Gemini 视觉清洗阶段)

通过了 Python 脚本硬筛的存活账号，将提取以下视觉素材投喂给大型视觉模型进行深层 SOP 判定。

**提取逻辑**：提取前 9 个视频的统一下载点 `thumbnailUrl` (即 maxresdefault.jpg 高清封面)。

投喂给大模型后，由大模型根据以下 SOP 进行最终裁决：
1. **画面环境是否干净**：排查环境杂乱、光线昏暗、像仓库。要求家居整洁、明亮有生活感。
2. **账号内容是否过度商业化/假感重**：结合 `isPaidContent` 标签，排查是否每条视频都是精修广告，缺乏真实生活场景。
3. **达人形象雷区（纹身与暴露）**：排查大面积纹身、明显花臂、腿部纹身（脱毛仪大忌）；排查满屏过度性感姿势。
4. **宝妈达人细分**：排查是否 90% 内容全在晒娃（满屏晒娃 $\rightarrow$ Reject）；若包含自我护理、健身护肤等悦己行为 $\rightarrow$ 可提报。
5. **垂类专家加分**：识别是否为医疗专业类（Doctor/Dermatologist）、运动达人（Yoga/Pilates）、职场女性（Lawyer/Finance）等优先考虑类型。
6. **避免类型**：排查纯娱乐搞笑、纯美妆测评（无生活场景）。
