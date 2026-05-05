# AI模型调用管理界面设计方案

最后更新：2026-05-04

## 1. 目标

当前系统已经有多模型调用能力，但模型配置主要写在 `.env` 里，例如：

- `SENSENOVA_API_KEY`
- `DEEPSEEK_API_KEY`
- `AI_TASK_ROUTE_MATERIAL_ANALYSIS`
- `AI_TASK_ROUTE_TAG_GENERATION`

这种方式适合开发阶段，不适合长期使用。后续需要一个“AI 模型管理界面”，让用户或管理员可以在页面上管理模型供应商、模型列表、任务路由、启用状态和调用日志。

这个界面的目标是：

- 可以启用或禁用某个模型供应商。
- 可以新增、编辑、删除模型配置。
- 可以为不同 AI 任务选择不同模型。
- 可以设置模型调用优先级和 fallback 顺序。
- 可以测试某个模型是否可用。
- 可以查看调用日志、失败原因、延迟和成本估算。
- 可以避免把 API Key 明文暴露给前端。

## 2. 当前状态

当前后端已有：

- [backend/app/config.py](c:/Users/admin/Desktop/Book-Design/backend/app/config.py)
- [backend/app/ai_service.py](c:/Users/admin/Desktop/Book-Design/backend/app/ai_service.py)

当前调用链路大致是：

```text
AIService
  -> 读取 settings 中的供应商配置
  -> 根据 AI_TASK_ROUTE_* 选择 Provider
  -> 调用 OpenAI-compatible /chat/completions
```

目前配置来源是 `.env`，不够灵活。

建议下一步从“环境变量配置”升级为“数据库配置 + 管理界面配置”。

## 3. 管理界面入口

建议新增一个后台页面：

```text
/settings/ai-models
```

导航名称：

```text
AI 模型管理
```

入口可以先放在首页或用户菜单里，后续如果有角色系统，再限制为管理员可见。

## 4. 页面结构

建议页面分为 5 个区域：

1. 模型供应商管理
2. 模型列表管理
3. 任务路由配置
4. 模型测试区
5. 调用日志与健康状态

## 5. 模型供应商管理

### 5.1 展示内容

供应商列表展示：

| 字段 | 说明 |
|---|---|
| 供应商名称 | 例如 Sensenova、DeepSeek、Qwen、豆包、OpenAI |
| Provider Key | 系统内部标识，例如 `sensenova` |
| Base URL | 例如 `https://token.sensenova.cn/v1` |
| API Key 状态 | 已配置 / 未配置，不显示明文 |
| 是否启用 | 开关 |
| 默认供应商 | 是否为默认 |
| 最近状态 | 正常 / 失败 / 未测试 |
| 操作 | 编辑、测试、禁用、删除 |

### 5.2 API Key 处理

API Key 不能明文回传给前端。

前端只显示：

```text
sk-****Ydb
```

编辑时：

- 如果用户不填写新 Key，则保持旧 Key。
- 如果用户填写新 Key，则后端替换保存。
- 支持“一键清空 Key”，用于禁用供应商。

## 6. 模型列表管理

一个供应商下面可能有多个模型。

例如 Sensenova：

| 模型名称 | 用途 | 类型 |
|---|---|---|
| `deepseek-v4-flash` | 文本理解、素材分析 | chat |
| `sensenova-u1-fast` | 图片生成 | image_generation |
| `sensenova-6.7-flash-lite` | 图像理解 | vision |

模型字段建议：

| 字段 | 说明 |
|---|---|
| provider_id | 所属供应商 |
| model_key | 模型调用名称 |
| display_name | 页面显示名 |
| model_type | chat / vision / image_generation / embedding |
| capability | JSON，描述能力 |
| context_window | 上下文长度，可选 |
| enabled | 是否启用 |
| priority | 默认优先级 |
| notes | 备注 |

## 7. 任务路由配置

这是这个页面最重要的部分。

不同任务应该可以选择不同模型。

建议第一版支持这些任务：

| 任务类型 | 说明 |
|---|---|
| `tag_generation` | 素材标签生成 |
| `material_analysis` | 素材上下文理解 |
| `feeling_suggestion` | 用户心情和感悟候选 |
| `chapter_summary` | 章节摘要 |
| `book_profile` | 整本书理解 |
| `image_generation` | 图片生成 |
| `vision_understanding` | 图像理解 |

### 7.1 页面交互

每个任务显示一行：

```text
素材理解 material_analysis
[1] sensenova / deepseek-v4-flash
[2] qwen / qwen-plus
[3] openai / gpt-4o-mini
```

支持：

- 拖拽调整顺序。
- 添加备用模型。
- 删除备用模型。
- 启用或停用某条路由。
- 设置策略：质量优先 / 成本优先 / 速度优先。
- 设置超时时间。

### 7.2 调用规则

调用时按顺序执行：

```text
第 1 个模型成功 -> 返回结果
第 1 个模型失败 -> 自动 fallback 到第 2 个
第 2 个失败 -> fallback 到第 3 个
全部失败 -> 标记任务 failed，并保存错误信息
```

## 8. 模型测试区

每个供应商和模型都应该支持“测试调用”。

### 8.1 文本模型测试

输入：

```text
请用 JSON 数组返回 3 个中文标签，内容是：人生处境与自我欺骗
```

返回展示：

- 是否成功
- 使用模型
- 响应内容
- 延迟
- 错误信息

### 8.2 图片生成测试

输入：

```text
生成一张安静书房里的阅读插画
```

使用：

```text
sensenova-u1-fast
```

第一版可以只保存配置，不必立刻实现图片生成测试。

### 8.3 图像理解测试

上传图片后，用：

```text
sensenova-6.7-flash-lite
```

让模型回答：

```text
请描述图片内容，并提取可能的读书笔记主题。
```

第一版同样可以先预留。

## 9. 调用日志

建议新增调用日志列表。

展示字段：

| 字段 | 说明 |
|---|---|
| 时间 | 调用时间 |
| 任务类型 | material_analysis / tag_generation |
| 供应商 | sensenova / deepseek / qwen |
| 模型 | deepseek-v4-flash |
| 状态 | success / failed |
| 延迟 | 毫秒 |
| 错误信息 | 失败时展示 |
| 关联素材 | 可跳转素材 |

调用日志的价值：

- 知道哪个模型经常失败。
- 知道哪个模型慢。
- 知道 fallback 是否生效。
- 后续可以估算成本。

## 10. 数据表设计

### 10.1 `ai_providers`

```text
id
provider_key
display_name
base_url
api_key_encrypted
enabled
is_default
last_test_status
last_test_error
last_test_at
created_at
updated_at
```

说明：

- `api_key_encrypted` 应该加密保存。
- 第一版如果暂时不做加密，也不能回传明文给前端。

### 10.2 `ai_models`

```text
id
provider_id
model_key
display_name
model_type
capability_json
context_window
enabled
priority
notes
created_at
updated_at
```

### 10.3 `ai_task_routes`

```text
id
task_type
provider_id
model_id
route_order
strategy
timeout_seconds
enabled
created_at
updated_at
```

### 10.4 `ai_call_logs`

```text
id
user_id
task_type
provider_key
model_key
status
latency_ms
error_message
material_id
created_at
```

后续如果要做成本统计，可以增加：

```text
prompt_tokens
completion_tokens
cost_estimate
```

## 11. 后端接口设计

### 11.1 供应商接口

```http
GET /api/v1/admin/ai/providers
POST /api/v1/admin/ai/providers
PATCH /api/v1/admin/ai/providers/{provider_id}
DELETE /api/v1/admin/ai/providers/{provider_id}
POST /api/v1/admin/ai/providers/{provider_id}/test
```

### 11.2 模型接口

```http
GET /api/v1/admin/ai/models
POST /api/v1/admin/ai/models
PATCH /api/v1/admin/ai/models/{model_id}
DELETE /api/v1/admin/ai/models/{model_id}
POST /api/v1/admin/ai/models/{model_id}/test
```

### 11.3 任务路由接口

```http
GET /api/v1/admin/ai/task-routes
PUT /api/v1/admin/ai/task-routes/{task_type}
```

请求示例：

```json
{
  "task_type": "material_analysis",
  "routes": [
    {
      "provider_key": "sensenova",
      "model_key": "deepseek-v4-flash",
      "route_order": 1,
      "enabled": true
    },
    {
      "provider_key": "qwen",
      "model_key": "qwen-plus",
      "route_order": 2,
      "enabled": true
    }
  ]
}
```

### 11.4 调用日志接口

```http
GET /api/v1/admin/ai/call-logs
```

支持参数：

```text
task_type
provider_key
model_key
status
date_from
date_to
```

## 12. 前端文件设计

建议新增页面：

- `frontend/src/views/AIModelSettings.vue`

新增组件：

- `frontend/src/components/ai/ProviderCard.vue`
- `frontend/src/components/ai/ModelTable.vue`
- `frontend/src/components/ai/TaskRouteEditor.vue`
- `frontend/src/components/ai/ModelTestPanel.vue`
- `frontend/src/components/ai/AICallLogTable.vue`

新增 API：

- `frontend/src/api/index.js`

```js
export const aiAdminApi = {
  getProviders: () => api.get('/admin/ai/providers'),
  createProvider: (data) => api.post('/admin/ai/providers', data),
  updateProvider: (id, data) => api.patch(`/admin/ai/providers/${id}`, data),
  testProvider: (id, data) => api.post(`/admin/ai/providers/${id}/test`, data),
  getModels: () => api.get('/admin/ai/models'),
  createModel: (data) => api.post('/admin/ai/models', data),
  updateModel: (id, data) => api.patch(`/admin/ai/models/${id}`, data),
  getTaskRoutes: () => api.get('/admin/ai/task-routes'),
  updateTaskRoute: (taskType, data) => api.put(`/admin/ai/task-routes/${taskType}`, data),
  getCallLogs: (params) => api.get('/admin/ai/call-logs', { params })
}
```

## 13. 当前配置如何迁移

当前 `.env` 里已有：

```text
SENSENOVA_API_KEY
SENSENOVA_BASE_URL
SENSENOVA_TEXT_MODEL
SENSENOVA_IMAGE_MODEL
SENSENOVA_VISION_MODEL
```

迁移时可以在后端启动时做一次初始化：

1. 如果数据库没有 `sensenova` provider，则从 `.env` 创建。
2. 如果数据库没有 `deepseek-v4-flash` 模型，则从 `.env` 创建。
3. 如果数据库没有任务路由，则用 `.env` 中的 `AI_TASK_ROUTE_*` 初始化。
4. 初始化后，优先使用数据库配置。
5. 如果数据库没有配置，则 fallback 到 `.env`。

这样不会破坏当前开发配置，也能平滑升级。

## 14. 权限与安全

第一版至少要做到：

- API Key 不回传明文。
- 前端只显示脱敏 Key。
- 测试模型时后端执行，不让前端直接拿 Key。
- 只有登录用户可以访问。

后续如果有管理员角色：

- 只有管理员可以管理模型。
- 普通用户只能使用模型，不允许查看 Key。

## 15. MVP 实施顺序

### Phase 1：可管理供应商和路由

- 新增 `ai_providers`、`ai_models`、`ai_task_routes` 表。
- 从 `.env` 初始化当前 Sensenova 配置。
- 新增供应商、模型、任务路由接口。
- 后端 `ai_service.py` 改成优先读取数据库路由。
- 新增 `AIModelSettings.vue` 页面。
- 支持启用/禁用供应商。
- 支持调整 `material_analysis` 和 `tag_generation` 路由。

### Phase 2：测试和日志

- 新增模型测试接口。
- 新增 `ai_call_logs` 表。
- 每次模型调用记录日志。
- 页面展示调用成功率、失败原因和延迟。

### Phase 3：图片模型和图像理解

- 接入 `sensenova-u1-fast` 图片生成。
- 接入 `sensenova-6.7-flash-lite` 图像理解。
- 页面支持上传图片测试。
- 后续可把图片能力接入素材库。

## 16. 推荐的第一版页面草图

```text
AI 模型管理

[供应商]
Sensenova     已启用   Base URL: https://token.sensenova.cn/v1   Key: sk-****Ydb   [测试] [编辑] [禁用]
DeepSeek官网  已禁用   Base URL: https://api.deepseek.com        Key: 未配置      [测试] [编辑] [启用]
Qwen          未配置   Base URL: ...                             Key: 未配置      [编辑]

[任务路由]
素材理解 material_analysis
1. Sensenova / deepseek-v4-flash       [启用] [上移] [下移] [删除]
2. Legacy / gpt-3.5-turbo              [启用] [上移] [下移] [删除]
[添加备用模型]

标签生成 tag_generation
1. Sensenova / deepseek-v4-flash       [启用]
2. Legacy / gpt-3.5-turbo              [启用]

[模型测试]
任务类型：[素材理解]
测试文本：[输入一段素材]
[开始测试]

[调用日志]
时间 / 任务 / 供应商 / 模型 / 状态 / 延迟 / 错误
```

## 17. 结论

模型管理界面的核心不是“列几个 API Key”，而是把模型调用变成可控、可观察、可切换的系统能力。

第一版最重要的是：

- 供应商能启用/禁用。
- 任务路由能调整顺序。
- 模型能测试。
- 调用失败能看到原因。

这样以后你想临时禁用 DeepSeek 官网、优先使用 Sensenova、或者切换到 Qwen / 豆包，就不需要改代码和 `.env`，直接在界面里完成。
