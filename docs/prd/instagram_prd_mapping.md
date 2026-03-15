<!--
 * @Author: gifted-professor 1044396185@qq.com
 * @Date: 2026-03-14 11:51:13
 * @LastEditors: gifted-professor 1044396185@qq.com
 * @LastEditTime: 2026-03-14 15:36:15
 * @FilePath: /wanghong/docs/prd/instagram_prd_mapping.md
 * @Description: 这是默认设置,请设置`customMade`, 打开koroFileHeader查看配置 进行设置: https://github.com/OBKoro1/koro1FileHeader/wiki/%E9%85%8D%E7%BD%AE
-->
# Instagram 数据引擎映射文档 (PRD - IG Module)

## 数据源特征
Apify 返回的 JSON 是一个包含博主主页信息的对象（或单元素数组），全局信息在根节点，而视频/图文数据全部折叠在 `latestPosts` 这个嵌套数组中。

---

## 🎯 维度一：文本与硬性雷区排查 (Python 物理清洗阶段)

| 检查大类 | JSON 字段路径 | 提取与判定逻辑 |
| :--- | :--- | :--- |
| **品牌合作硬排雷** | `externalUrls[].url`, `biography`, `latestPosts[].caption` | 遍历外链数组、主页简介、以及近 20-30 条贴文的文案。寻找 `temu`, `aliexpress`, `shein`, `wish`。尤其是 `externalUrls`，若含竞品链接 $\rightarrow$ **直接 Reject**。文本命中竞品词也直接 Reject。 |
| **怀孕达人硬排雷** | `biography`, `latestPosts[].caption` | 扫描简介与近期文案，寻找 `pregnancy`, `pregnant`, `baby coming`, `expecting`。命中 $\rightarrow$ **直接 Reject**。 |
| **弱语义文本提示** | `biography`, `latestPosts[].caption` | 若命中 `baby`, `momlife`, `motherhood`, `$1` 这类弱语义词，不直接 Reject，而是作为 **待复核文本提示** 保留给人工/大模型复核。 |
| **账号活跃度** | `latestPosts[0].timestamp` | 解析最新帖子的发布时间。若距今超过 3 个月未更新 $\rightarrow$ **绝对 Reject**；若当月无更新 $\rightarrow$ **谨慎提报（标记）**。 |

---

## 👁️ 维度二：大模型视觉与语境判定 (Gemini 视觉清洗阶段)

通过了 Python 脚本硬筛的存活账号，将提取以下视觉素材投喂给大型视觉模型进行深层 SOP 判定。

**提取逻辑**：提取前 9 个帖子的最高清封面 `latestPosts[].displayUrl`。

投喂给大模型后，由大模型根据以下 SOP 进行最终裁决：
1. **画面环境是否干净**：排查环境杂乱、光线昏暗、像仓库。要求家居整洁、明亮有生活感。
2. **账号内容是否过度商业化/假感重**：排查滤镜过重、磨皮严重、每条都是精修广告。
3. **达人形象雷区（纹身与暴露）**：排查大面积纹身、明显花臂、腿部纹身（脱毛仪大忌）；排查满屏比基尼、过度性感。
4. **宝妈达人细分**：排查是否 90% 内容全在晒娃（满屏晒娃 $\rightarrow$ Reject）；若包含自我护理、健身护肤等悦己行为 $\rightarrow$ 可提报。
5. **垂类专家加分**：识别是否为医疗专业类（Doctor/Dermatologist）、运动达人（Yoga/Pilates）、职场女性（Lawyer/Finance）等优先考虑类型。
6. **避免类型**：排查纯娱乐搞笑、纯美妆测评（无生活场景）。
