# TikTok 数据引擎映射文档 (PRD - TikTok Module)

## 数据源特征
Apify 返回的 JSON 是一个 Array，包含该博主最新发布的 N 条视频记录。每一条记录代表一个视频，但其中嵌套了全局的博主信息（`authorMeta`）。

---

## 🎯 维度一：文本与硬性雷区排查 (Python 物理清洗阶段)

| 检查大类 | JSON 字段路径 | 提取与判定逻辑 |
| :--- | :--- | :--- |
| **品牌合作排雷** | `authorMeta.signature`, `text`, `hashtags[].name`, `authorMeta.bioLink` | 提取简介、主页外链、以及近 20-30 条视频的标题/描述/标签。统一转小写后寻找 `temu`, `aliexpress`, `shein`, `wish`, `$1` 等竞品或低价词汇。命中 $\rightarrow$ **直接 Reject**。 |
| **怀孕达人排雷** | `authorMeta.signature`, `text`, `hashtags[].name` | 扫描简介与近期视频文案，寻找 `pregnancy`, `pregnant`, `baby coming`, `expecting`。命中 $\rightarrow$ **优先 Reject**。 |
| **账号活跃度** | `[0].createTimeISO` | 解析最新一条视频的发布时间。若距今超过 3 个月未更新 $\rightarrow$ **绝对 Reject**；若当月无更新 $\rightarrow$ **谨慎提报（标记）**。 |

---

## 👁️ 维度二：大模型视觉与语境判定 (Gemini 视觉清洗阶段)

通过了 Python 脚本硬筛的存活账号，将提取以下视觉素材投喂给大型视觉模型进行深层 SOP 判定。

**提取逻辑**：获取前 9 条视频的高清封面。
- **普通视频**：`videoMeta.originalCoverUrl` 或 `videoMeta.coverUrl`
- **图文轮播 (isSlideshow=True)**：`slideshowImageLinks[0].tiktokLink`

投喂给大模型后，由大模型根据以下 SOP 进行最终裁决：
1. **画面环境是否干净**：排查环境杂乱、光线昏暗、像仓库。要求家居整洁、明亮有生活感。
2. **账号内容是否过度商业化/假感重**：排查滤镜过重、磨皮严重、每条都是精修广告。
3. **达人形象雷区（纹身与暴露）**：排查大面积纹身、明显花臂、腿部纹身（脱毛仪大忌）；排查满屏比基尼、过度性感。
4. **宝妈达人细分**：排查是否 90% 内容全在晒娃（满屏晒娃 $\rightarrow$ Reject）；若包含自我护理、健身护肤等悦己行为 $\rightarrow$ 可提报。
5. **垂类专家加分**：识别是否为医疗专业类（Doctor/Dermatologist）、运动达人（Yoga/Pilates）、职场女性（Lawyer/Finance）等优先考虑类型。
6. **避免类型**：排查纯娱乐搞笑、纯美妆测评（无生活场景）。
