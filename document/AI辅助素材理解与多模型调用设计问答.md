# AI辅助素材理解与多模型调用设计问答

最后更新：2026-05-02

## 1. 这个需求到底是什么？

**问：我真正想做的是一个什么功能？**

答：你想做的不是简单的“AI 打标签”，而是一个“AI 阅读理解型素材库”。

当用户保存一条素材时，系统应该同时理解：

- 这本书大概讲什么。
- 当前章节发生了什么。
- 被选中文字前后有什么上下文。
- 这段文字为什么值得保存。
- 用户可能被什么情绪、观点或人生经验触动。
- 这条素材以后可以怎么用于写作、读书笔记、评论或复盘。

也就是说，系统要帮用户把“我觉得这段有意思，但我说不出来为什么”转化成可保存、可修改、可复用的阅读理解卡片。

## 2. 为什么不能只保存原文和标签？

**问：现在已经能保存素材、章节、原文位置和标签，为什么还不够？**

答：因为普通素材库只保存“内容”，但用户真正需要保存的是“阅读现场”。

一段话本身可能很短，但它的价值通常来自：

- 它在整本书中的位置。
- 它前后的人物关系和情节冲突。
- 它对应的主题，比如婚姻、权力、孤独、讽刺、成长。
- 用户当时的情绪，比如震动、难过、共鸣、困惑、愤怒。
- 未来可以用它表达什么观点。

如果只保存一句话，过几天再看，用户很可能忘记自己为什么保存它。AI 的价值就是帮助用户把这些隐性的理解一起保存下来。

## 3. AI 在保存素材时应该做什么？

**问：用户点击“保存素材”后，AI 应该生成哪些内容？**

答：第一版建议生成以下内容：

- `上下文摘要`：概括这段话前后发生了什么。
- `素材解读`：解释这段话本身表达了什么。
- `主题关联`：指出它和本书主题、章节主题的关系。
- `情绪判断`：判断这段文字可能带来的情绪感受。
- `感悟候选`：生成几条“用户可能想表达但还没说出口”的感悟。
- `写作用途`：说明这条素材以后适合用于什么主题。
- `推荐标签`：生成主题标签、情绪标签、写作用途标签。

第一版不要追求 AI 完全替用户写最终感悟，而是先给用户几个可选方向，让用户点选、修改或重新生成。

## 4. 这个系统应该用 GPT 吗？

**问：模型是不是只能用 GPT？**

答：不应该。这个功能不应该绑定某一个模型，也不应该绑定某一个厂商。

系统应该支持多模型调用。OpenAI、DeepSeek、Qwen、豆包、智谱、Moonshot、Claude 等，只要文字理解能力强、接口稳定、成本合适，都可以接入。

关键设计不是“选哪一个模型”，而是设计一个统一的模型调用层，让业务功能只关心“我要完成什么任务”，不关心“具体由哪个厂商完成”。

## 5. 为什么需要多模型？

**问：多模型调用比单模型调用有什么好处？**

答：多模型有几个明显优势：

- `效果弹性`：不同模型擅长的事情不同。有的适合长文本理解，有的适合中文表达，有的适合结构化 JSON 输出。
- `成本控制`：简单任务用便宜模型，复杂任务用强模型。
- `可用性保障`：某个厂商接口失败时，可以自动切换到备用模型。
- `避免供应商锁定`：未来换模型不需要大改业务代码。
- `个性化选择`：用户或管理员可以选择“便宜优先”“质量优先”“速度优先”。

## 6. 多模型调用的核心架构是什么？

**问：系统应该怎么设计才能支持多模型？**

答：建议新增一层“AI 模型网关”。

业务代码不要直接调用 OpenAI、DeepSeek、Qwen 或豆包，而是调用统一的内部服务：

```text
素材保存功能
  -> AIService.analyzeMaterial()
    -> ModelRouter 选择模型
      -> ProviderAdapter 调用具体厂商
        -> OpenAI / DeepSeek / Qwen / 豆包 / 其他模型
```

每一层职责如下：

- `AIService`：面向业务，提供“分析素材”“生成标签”“总结章节”等能力。
- `ModelRouter`：根据任务类型、成本、速度、失败情况选择模型。
- `ProviderAdapter`：屏蔽不同厂商接口差异，把请求统一成同一种格式。
- `ModelConfig`：管理模型配置、API Key、Base URL、超时、重试和优先级。

## 7. 任务应该怎么拆分？

**问：所有 AI 任务都用同一个模型完成吗？**

答：不建议。应该按任务拆分，让不同模型负责不同类型的任务。

建议第一版把 AI 任务分为：

| 任务类型 | 说明 | 模型选择策略 |
|---|---|---|
| `tag_generation` | 生成标签 | 便宜、速度快、JSON 稳定 |
| `material_analysis` | 分析素材和上下文 | 中文理解强、表达好 |
| `feeling_suggestion` | 推测用户感受和感悟 | 中文表达自然、共情能力强 |
| `chapter_summary` | 章节摘要 | 长文本能力较好 |
| `book_profile` | 整本书概况 | 长上下文能力强 |
| `writing_usage` | 写作用途和观点提炼 | 逻辑表达强 |

这样系统就可以做到：

- 标签生成用低成本模型。
- 复杂素材解读用更强模型。
- 长章节总结用长上下文模型。
- 模型失败时降级到备用模型。

## 8. 保存素材时 AI 需要哪些输入？

**问：AI 分析素材时，后端应该给模型传什么？**

答：不要只传选中的文字。至少要传以下结构：

```json
{
  "book": {
    "title": "围城",
    "author": "钱锺书",
    "book_summary": "可选，系统预先生成的整本书摘要"
  },
  "chapter": {
    "chapter_order": 12,
    "title": "某章节标题",
    "chapter_summary": "可选，系统预先生成的章节摘要"
  },
  "material": {
    "selected_text": "用户选中的原文",
    "context_before": "选中文字前面的原文",
    "context_after": "选中文字后面的原文",
    "locator_text": "第12章 / 某段附近"
  },
  "user_input": {
    "note": "用户自己写的备注，可为空",
    "mood": "用户选择的心情，可为空"
  }
}
```

如果暂时没有整本书摘要和章节摘要，第一版也可以只传：

- 书名
- 作者
- 章节标题
- 选中文字
- 前后上下文
- 用户备注
- 用户心情

## 9. AI 应该返回什么格式？

**问：模型返回自由文本还是 JSON？**

答：建议要求模型返回结构化 JSON。这样前端可以稳定展示，后端也方便保存。

建议返回格式：

```json
{
  "context_summary": "这段话前后主要发生了什么",
  "interpretation": "这段素材的核心含义",
  "theme_analysis": "它和本书主题或章节主题的关系",
  "possible_feelings": [
    "你可能被这段话里的讽刺感打动",
    "你可能想到现实中类似的人际关系"
  ],
  "personal_insight_candidates": [
    "人有时并不是不知道答案，而是不愿承认自己的处境。",
    "越是体面的表达，背后可能越藏着难堪。"
  ],
  "writing_topics": [
    "人性",
    "婚姻",
    "体面与虚荣"
  ],
  "tags": [
    "讽刺",
    "人情世故",
    "人物心理"
  ],
  "questions": [
    "你保存这段时，是更被人物处境打动，还是被作者的讽刺表达打动？"
  ]
}
```

## 10. 用户的“心情”和“感悟”怎么设计？

**问：用户表达不出来时，产品应该怎么帮他？**

答：不要让用户从空白输入框开始。可以设计成“AI 先猜，用户再确认”。

保存素材弹窗可以增加：

- `我的感觉`：用户可选，也可不选。
- `AI 猜测我的感受`：模型生成 3 到 5 个候选。
- `一键写成我的感悟`：把选中的感受改写成第一人称读书笔记。
- `不准确，换一批`：重新生成候选感悟。

心情选项可以先做这些：

- 共鸣
- 震动
- 难过
- 讽刺
- 愤怒
- 困惑
- 温暖
- 荒凉
- 喜欢
- 想反驳

## 11. 多模型配置应该怎么存？

**问：后端如何配置 DeepSeek、Qwen、豆包等模型？**

答：建议不要把模型写死在代码里，而是用配置文件或数据库配置。

第一版可以先用环境变量：

```env
AI_DEFAULT_PROVIDER=deepseek
AI_DEFAULT_MODEL=deepseek-chat

AI_PROVIDERS=openai,deepseek,qwen,doubao

OPENAI_API_KEY=xxx
OPENAI_BASE_URL=https://api.openai.com/v1

DEEPSEEK_API_KEY=xxx
DEEPSEEK_BASE_URL=https://api.deepseek.com

QWEN_API_KEY=xxx
QWEN_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1

DOUBAO_API_KEY=xxx
DOUBAO_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
```

后续可以做成管理后台：

- 添加模型供应商。
- 设置模型名称。
- 设置任务优先级。
- 设置单次最大 token。
- 设置超时时间。
- 设置是否启用。
- 查看调用成本和失败率。

## 12. 模型路由规则怎么设计？

**问：系统怎么决定某次任务用哪个模型？**

答：建议按“任务类型 + 策略”选择模型。

示例规则：

```json
{
  "tag_generation": {
    "strategy": "cost_first",
    "primary": "qwen-lite",
    "fallback": ["deepseek-chat", "gpt-4o-mini"]
  },
  "material_analysis": {
    "strategy": "quality_first",
    "primary": "deepseek-chat",
    "fallback": ["qwen-plus", "doubao-pro", "gpt-4o-mini"]
  },
  "chapter_summary": {
    "strategy": "long_context_first",
    "primary": "qwen-long",
    "fallback": ["deepseek-chat", "doubao-pro"]
  }
}
```

第一版不需要做得太复杂，只要支持：

- 默认模型。
- 每类任务指定模型。
- 失败后 fallback 到备用模型。

## 13. 不同厂商接口不一样怎么办？

**问：OpenAI、DeepSeek、Qwen、豆包接口格式不同，怎么统一？**

答：新增 `ProviderAdapter`。

内部统一使用一种请求格式：

```python
class AIChatRequest:
    task_type: str
    messages: list
    response_format: str = "json"
    temperature: float = 0.3
    max_tokens: int = 1500
```

每个适配器负责转换：

- `OpenAIAdapter`
- `DeepSeekAdapter`
- `QwenAdapter`
- `DoubaoAdapter`

业务层永远不直接拼厂商请求。这样以后增加新模型，只需要新增一个 Adapter。

## 14. AI 分析结果应该保存在哪里？

**问：这些 AI 生成的内容应该放在 `materials` 表里，还是新建表？**

答：第一版可以先扩展 `materials` 表，后续再拆表。

第一版建议在 `materials` 增加：

| 字段 | 说明 |
|---|---|
| `context_before` | 选中文字前文 |
| `context_after` | 选中文字后文 |
| `user_mood` | 用户选择的心情 |
| `ai_context_summary` | AI 上下文摘要 |
| `ai_interpretation` | AI 素材解读 |
| `ai_possible_feelings` | AI 猜测感受，JSON |
| `ai_insight_candidates` | AI 感悟候选，JSON |
| `ai_writing_topics` | 写作主题，JSON |
| `ai_analysis_model` | 本次分析使用的模型 |
| `ai_analysis_status` | pending / completed / failed |

后续如果 AI 内容越来越多，可以拆成：

```text
material_ai_analyses
- id
- material_id
- provider
- model
- task_type
- input_snapshot
- output_json
- status
- error_message
- created_at
```

拆表的好处是可以保留多次分析记录，也能比较不同模型的结果。

## 15. 素材保存流程应该怎么变？

**问：用户选中文字保存素材时，完整流程是什么？**

答：建议流程如下：

1. 用户在阅读页选中文字。
2. 点击“快速记录素材”。
3. 前端带上 `selected_text`、`anchor_start`、`anchor_end`。
4. 后端根据位置截取 `context_before` 和 `context_after`。
5. 先保存素材，状态为 `ai_analysis_status = pending`。
6. 后端后台任务调用 `AIService.analyzeMaterial()`。
7. `ModelRouter` 根据任务类型选择模型。
8. 模型返回结构化 JSON。
9. 后端保存 AI 解读结果。
10. 前端轮询或刷新后展示 AI 分析卡片。

这样做的好处是：保存素材不被 AI 请求阻塞。即使模型慢或失败，用户的素材也不会丢。

## 16. 前端界面应该怎么展示？

**问：素材弹窗和素材详情页怎么设计？**

答：建议分两个阶段。

### 保存弹窗

保存时展示：

- 选中的原文。
- 书名、章节、位置。
- 用户备注。
- 用户心情选择。
- “保存后自动 AI 分析”的提示。

如果希望交互更即时，可以保存后弹出：

- AI 正在理解这段内容。
- 分析完成后显示候选感悟。

### 素材详情页

详情页展示：

- 原文素材。
- 查看原文位置。
- 前后上下文。
- 我的备注。
- 我的心情。
- AI 解读。
- AI 猜测我的感受。
- AI 感悟候选。
- 写作用途。
- 推荐标签。
- 使用模型。
- 重新分析按钮。

## 17. 如果 AI 分析错了怎么办？

**问：模型可能理解错书、理解错人物、猜错用户心情，怎么办？**

答：产品上要承认 AI 是辅助，不是最终答案。

建议设计：

- AI 解读旁边显示“可编辑”。
- 用户可以选择“这条不准确”。
- 支持“重新分析”。
- 支持切换模型重新分析。
- 保存用户最终采用的版本。

更好的体验是：

```text
AI 猜测你的感受：
1. 你可能被这里的讽刺感打动。
2. 你可能想到现实中类似的关系。
3. 你可能对人物的无力感产生共鸣。

[采用] [改写] [换一批]
```

## 18. 如何避免成本失控？

**问：如果每条素材都调用强模型，会不会很贵？**

答：需要成本控制。

建议：

- 保存素材时只分析一次。
- 标签生成用低成本模型。
- 复杂解读才用强模型。
- 同一本书的摘要缓存起来，不要每次重复生成。
- 同一章节摘要缓存起来。
- 设置每日调用上限。
- 设置失败重试次数。
- 保存模型调用日志，方便统计成本。

可以增加调用日志表：

```text
ai_call_logs
- id
- user_id
- task_type
- provider
- model
- prompt_tokens
- completion_tokens
- cost_estimate
- status
- latency_ms
- created_at
```

## 19. 第一版 MVP 应该做哪些？

**问：不要一下做太大，第一版最小可用功能是什么？**

答：第一版建议做这些：

- 保存素材时截取前后上下文。
- 新增用户心情字段。
- 新增 AI 素材分析后台任务。
- 支持至少两个模型供应商配置。
- 支持默认模型和备用模型。
- AI 返回结构化 JSON。
- 素材详情页展示 AI 解读、感受候选、写作主题。
- 支持“重新分析”。

第一版暂时可以不做：

- 整本书知识图谱。
- 用户长期画像。
- 多模型结果对比。
- 复杂成本看板。
- 首页最近 AI 阅读洞察。

## 20. 具体需要改哪些文件？

**问：如果后续开始实现，预计需要改哪些文件？**

答：建议按下面文件拆分。

### 后端

- `backend/app/config.py`
  增加多模型供应商配置、默认模型、任务路由配置。

- `backend/app/models.py`
  扩展 `Material` 字段，或新增 `MaterialAIAnalysis`、`AICallLog`。

- `backend/app/main.py`
  在创建素材、获取素材详情、重新分析素材的接口中接入 AI 分析任务。

- `backend/app/ai_service.py`
  新增业务级 AI 能力，比如 `analyze_material`、`generate_tags`、`summarize_chapter`。

- `backend/app/model_router.py`
  新增模型路由，根据任务类型选择模型和 fallback。

- `backend/app/ai_providers/`
  新增各厂商适配器：
  `openai_adapter.py`、`deepseek_adapter.py`、`qwen_adapter.py`、`doubao_adapter.py`。

### 前端

- `frontend/src/api/index.js`
  增加重新分析素材、获取 AI 分析结果的 API。

- `frontend/src/components/MaterialQuickCreateDialog.vue`
  增加心情选择、AI 分析提示。

- `frontend/src/views/Materials.vue`
  展示 AI 解读、候选感悟、写作主题。

- `frontend/src/views/BookDetail.vue`
  保存素材时传递上下文定位信息，必要时展示 AI 分析入口。

## 21. 最终产品形态是什么？

**问：这个功能做好后，用户会感受到什么变化？**

答：用户会感觉这个系统不是冷冰冰地“帮我存一句话”，而是在和我一起读书。

理想体验是：

```text
我选中一句话。
系统知道这句话来自哪本书、哪一章、前后发生了什么。
AI 帮我解释它为什么重要。
AI 猜到我可能为什么被它触动。
AI 给我几个感悟候选。
我选择一个，稍微改一下，保存。
以后我写读后感、文章、评论时，这条素材已经是有上下文、有理解、有情绪、有用途的。
```

一句话总结：

**这个功能的核心不是让 AI 替用户读书，而是让 AI 帮用户把模糊的阅读感受变成清晰、可保存、可复用的思想素材。**
