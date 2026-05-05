<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { aiAdminApi } from '../api'

const router = useRouter()
const loading = ref(false)
const providers = ref([])
const models = ref([])
const routes = ref([])
const logs = ref([])

const providerDialogVisible = ref(false)
const modelDialogVisible = ref(false)
const editingProviderId = ref('')
const editingModelId = ref('')

const providerForm = ref({
  provider_key: '',
  display_name: '',
  base_url: '',
  api_key: '',
  enabled: true,
  is_default: false
})

const modelForm = ref({
  provider_id: '',
  model_key: '',
  display_name: '',
  model_type: 'chat',
  endpoint_path: '/chat/completions',
  context_window: null,
  enabled: true,
  priority: 100,
  notes: ''
})

const taskTypes = [
  { value: 'material_analysis', label: '素材理解' },
  { value: 'tag_generation', label: '标签生成' },
  { value: 'feeling_suggestion', label: '感悟候选' },
  { value: 'chapter_summary', label: '章节摘要' },
  { value: 'image_generation', label: '图片生成' },
  { value: 'vision_understanding', label: '图像理解' }
]
const selectedTask = ref('material_analysis')
const routeDraft = ref([])
const testPrompt = ref('请只返回 JSON 数组：["测试"]')
const testingModelId = ref('')
const testResult = ref(null)

const chatModels = computed(() => models.value.filter(model => model.model_type === 'chat'))
const modelsByProvider = computed(() => {
  const map = {}
  for (const model of models.value) {
    if (!map[model.provider_id]) map[model.provider_id] = []
    map[model.provider_id].push(model)
  }
  return map
})

const currentRoutes = computed(() => {
  return routes.value
    .filter(route => route.task_type === selectedTask.value)
    .sort((a, b) => a.route_order - b.route_order)
})

const fetchAll = async () => {
  loading.value = true
  try {
    const [providerRes, modelRes, routeRes, logRes] = await Promise.all([
      aiAdminApi.getProviders(),
      aiAdminApi.getModels(),
      aiAdminApi.getTaskRoutes(),
      aiAdminApi.getCallLogs({ limit: 30 })
    ])
    providers.value = providerRes || []
    models.value = modelRes || []
    routes.value = routeRes || []
    logs.value = logRes || []
    syncRouteDraft()
  } catch (error) {
    ElMessage.error(error.message)
  } finally {
    loading.value = false
  }
}

const syncRouteDraft = () => {
  routeDraft.value = currentRoutes.value.map(route => ({
    provider_id: route.provider_id,
    model_id: route.model_id,
    route_order: route.route_order,
    strategy: route.strategy || 'quality_first',
    timeout_seconds: route.timeout_seconds || 30,
    enabled: route.enabled
  }))
}

onMounted(fetchAll)

const providerName = (providerId) => {
  return providers.value.find(item => item.id === providerId)?.display_name || '未知供应商'
}

const modelName = (modelId) => {
  const model = models.value.find(item => item.id === modelId)
  return model ? `${model.display_name} / ${model.model_key}` : '请选择模型'
}

const openProviderDialog = (provider = null) => {
  editingProviderId.value = provider?.id || ''
  providerForm.value = provider ? {
    provider_key: provider.provider_key,
    display_name: provider.display_name,
    base_url: provider.base_url,
    api_key: '',
    enabled: provider.enabled,
    is_default: provider.is_default
  } : {
    provider_key: '',
    display_name: '',
    base_url: '',
    api_key: '',
    enabled: true,
    is_default: false
  }
  providerDialogVisible.value = true
}

const saveProvider = async () => {
  try {
    const data = { ...providerForm.value }
    if (!data.api_key) delete data.api_key
    if (editingProviderId.value) {
      delete data.provider_key
      await aiAdminApi.updateProvider(editingProviderId.value, data)
    } else {
      await aiAdminApi.createProvider(data)
    }
    ElMessage.success('供应商已保存')
    providerDialogVisible.value = false
    await fetchAll()
  } catch (error) {
    ElMessage.error(error.message)
  }
}

const toggleProvider = async (provider) => {
  try {
    await aiAdminApi.updateProvider(provider.id, { enabled: !provider.enabled })
    ElMessage.success(provider.enabled ? '已禁用供应商' : '已启用供应商')
    await fetchAll()
  } catch (error) {
    ElMessage.error(error.message)
  }
}

const deleteProvider = async (provider) => {
  try {
    await ElMessageBox.confirm(`确定删除 ${provider.display_name} 吗？`, '提示', { type: 'warning' })
    await aiAdminApi.deleteProvider(provider.id)
    ElMessage.success('供应商已删除')
    await fetchAll()
  } catch {}
}

const openModelDialog = (model = null) => {
  editingModelId.value = model?.id || ''
  modelForm.value = model ? {
    provider_id: model.provider_id,
    model_key: model.model_key,
    display_name: model.display_name,
    model_type: model.model_type,
    endpoint_path: model.endpoint_path || '/chat/completions',
    context_window: model.context_window,
    enabled: model.enabled,
    priority: model.priority,
    notes: model.notes || ''
  } : {
    provider_id: providers.value[0]?.id || '',
    model_key: '',
    display_name: '',
    model_type: 'chat',
    endpoint_path: '/chat/completions',
    context_window: null,
    enabled: true,
    priority: 100,
    notes: ''
  }
  modelDialogVisible.value = true
}

const handleModelTypeChange = () => {
  if (modelForm.value.model_type === 'image_generation') {
    modelForm.value.endpoint_path = '/images/generations'
  } else if (!modelForm.value.endpoint_path || modelForm.value.endpoint_path === '/images/generations') {
    modelForm.value.endpoint_path = '/chat/completions'
  }
}

const saveModel = async () => {
  try {
    if (editingModelId.value) {
      await aiAdminApi.updateModel(editingModelId.value, modelForm.value)
    } else {
      await aiAdminApi.createModel(modelForm.value)
    }
    ElMessage.success('模型已保存')
    modelDialogVisible.value = false
    await fetchAll()
  } catch (error) {
    ElMessage.error(error.message)
  }
}

const toggleModel = async (model) => {
  try {
    await aiAdminApi.updateModel(model.id, { enabled: !model.enabled })
    ElMessage.success(model.enabled ? '已禁用模型' : '已启用模型')
    await fetchAll()
  } catch (error) {
    ElMessage.error(error.message)
  }
}

const addRoute = () => {
  const model = chatModels.value[0]
  if (!model) {
    ElMessage.warning('请先创建可用的 chat 模型')
    return
  }
  routeDraft.value.push({
    provider_id: model.provider_id,
    model_id: model.id,
    route_order: routeDraft.value.length + 1,
    strategy: 'quality_first',
    timeout_seconds: 30,
    enabled: true
  })
}

const removeRoute = (index) => {
  routeDraft.value.splice(index, 1)
  normalizeRouteOrder()
}

const moveRoute = (index, direction) => {
  const target = index + direction
  if (target < 0 || target >= routeDraft.value.length) return
  const temp = routeDraft.value[index]
  routeDraft.value[index] = routeDraft.value[target]
  routeDraft.value[target] = temp
  normalizeRouteOrder()
}

const normalizeRouteOrder = () => {
  routeDraft.value = routeDraft.value.map((route, index) => ({
    ...route,
    route_order: index + 1
  }))
}

const handleRouteProviderChange = (route) => {
  const firstModel = (modelsByProvider.value[route.provider_id] || []).find(model => model.model_type === 'chat')
  route.model_id = firstModel?.id || ''
}

const saveRoute = async () => {
  try {
    normalizeRouteOrder()
    await aiAdminApi.updateTaskRoute(selectedTask.value, { routes: routeDraft.value })
    ElMessage.success('任务路由已保存')
    await fetchAll()
  } catch (error) {
    ElMessage.error(error.message)
  }
}

const testModel = async (model) => {
  testingModelId.value = model.id
  testResult.value = null
  try {
    const res = await aiAdminApi.testModel(model.id, {
      prompt: testPrompt.value,
      task_type: selectedTask.value
    })
    testResult.value = res
    if (res.ok) {
      ElMessage.success('测试成功')
    } else {
      ElMessage.error(res.error || '测试失败')
    }
    await fetchAll()
  } catch (error) {
    ElMessage.error(error.message)
  } finally {
    testingModelId.value = ''
  }
}

const formatDate = (dateStr) => {
  if (!dateStr) return ''
  return new Date(dateStr).toLocaleString('zh-CN')
}
</script>

<template>
  <div class="ai-settings-page" v-loading="loading">
    <div class="page-header">
      <div>
        <el-button @click="router.push('/')" icon="ArrowLeft">返回首页</el-button>
        <h2>AI 模型管理</h2>
        <p>管理供应商、模型、任务路由和调用日志。API Key 只在后端保存，页面不展示明文。</p>
      </div>
      <el-button type="primary" @click="openProviderDialog()">新增供应商</el-button>
    </div>

    <el-card class="section-card">
      <template #header>
        <div class="section-title">
          <span>供应商</span>
          <el-tag type="info" effect="plain">{{ providers.length }} 个</el-tag>
        </div>
      </template>
      <div class="provider-grid">
        <div v-for="provider in providers" :key="provider.id" class="provider-card">
          <div class="provider-top">
            <div>
              <h3>{{ provider.display_name }}</h3>
              <p>{{ provider.provider_key }}</p>
            </div>
            <el-switch :model-value="provider.enabled" @change="toggleProvider(provider)" />
          </div>
          <div class="provider-meta">
            <div>Base URL：{{ provider.base_url }}</div>
            <div>API Key：{{ provider.api_key_masked || '未配置' }}</div>
            <div>
              状态：
              <el-tag size="small" :type="provider.last_test_status === 'success' ? 'success' : provider.last_test_status === 'failed' ? 'danger' : 'info'">
                {{ provider.last_test_status || '未测试' }}
              </el-tag>
              <el-tag v-if="provider.is_default" size="small" type="warning">默认</el-tag>
            </div>
          </div>
          <div class="provider-actions">
            <el-button link type="primary" @click="openProviderDialog(provider)">编辑</el-button>
            <el-button link type="danger" @click="deleteProvider(provider)">删除</el-button>
          </div>
        </div>
      </div>
    </el-card>

    <el-card class="section-card">
      <template #header>
        <div class="section-title">
          <span>模型列表</span>
          <el-button type="primary" size="small" @click="openModelDialog()">新增模型</el-button>
        </div>
      </template>
      <el-table :data="models" stripe>
        <el-table-column prop="provider_name" label="供应商" width="130" />
        <el-table-column prop="display_name" label="显示名" width="130" />
        <el-table-column prop="model_key" label="模型名" min-width="180" />
        <el-table-column prop="model_type" label="类型" width="140" />
        <el-table-column prop="endpoint_path" label="调用路径" min-width="190" />
        <el-table-column label="启用" width="90">
          <template #default="{ row }">
            <el-switch :model-value="row.enabled" @change="toggleModel(row)" />
          </template>
        </el-table-column>
        <el-table-column label="操作" width="210">
          <template #default="{ row }">
            <el-button link type="primary" @click="openModelDialog(row)">编辑</el-button>
            <el-button link type="success" :loading="testingModelId === row.id" @click="testModel(row)">测试</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-card class="section-card route-card">
      <template #header>
        <div class="section-title">
          <span>任务路由</span>
          <el-select v-model="selectedTask" style="width: 180px" @change="syncRouteDraft">
            <el-option v-for="task in taskTypes" :key="task.value" :label="task.label" :value="task.value" />
          </el-select>
        </div>
      </template>
      <div class="route-list">
        <div v-for="(route, index) in routeDraft" :key="index" class="route-row">
          <span class="route-order">{{ index + 1 }}</span>
          <el-select v-model="route.provider_id" style="width: 180px" @change="handleRouteProviderChange(route)">
            <el-option v-for="provider in providers" :key="provider.id" :label="provider.display_name" :value="provider.id" />
          </el-select>
          <el-select v-model="route.model_id" style="width: 260px">
            <el-option
              v-for="model in (modelsByProvider[route.provider_id] || [])"
              :key="model.id"
              :label="`${model.display_name} / ${model.model_key}`"
              :value="model.id"
            />
          </el-select>
          <el-input-number v-model="route.timeout_seconds" :min="5" :max="180" />
          <el-switch v-model="route.enabled" />
          <el-button link @click="moveRoute(index, -1)">上移</el-button>
          <el-button link @click="moveRoute(index, 1)">下移</el-button>
          <el-button link type="danger" @click="removeRoute(index)">删除</el-button>
        </div>
      </div>
      <div class="route-actions">
        <el-button @click="addRoute">添加备用模型</el-button>
        <el-button type="primary" @click="saveRoute">保存路由</el-button>
      </div>
    </el-card>

    <el-card class="section-card">
      <template #header>
        <div class="section-title">
          <span>模型测试</span>
          <span class="hint">点击模型列表里的“测试”会使用下面的提示词</span>
        </div>
      </template>
      <el-input v-model="testPrompt" type="textarea" :rows="3" />
      <div v-if="testResult" class="test-result" :class="{ failed: !testResult.ok }">
        <strong>{{ testResult.ok ? '测试成功' : '测试失败' }}</strong>
        <span>{{ testResult.provider_key }} / {{ testResult.model_key }} / {{ testResult.latency_ms || 0 }}ms</span>
        <pre>{{ testResult.response || testResult.error }}</pre>
      </div>
    </el-card>

    <el-card class="section-card">
      <template #header>
        <div class="section-title">
          <span>最近调用日志</span>
          <el-button size="small" @click="fetchAll">刷新</el-button>
        </div>
      </template>
      <el-table :data="logs" stripe>
        <el-table-column prop="created_at" label="时间" width="180">
          <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
        </el-table-column>
        <el-table-column prop="task_type" label="任务" width="150" />
        <el-table-column prop="provider_key" label="供应商" width="130" />
        <el-table-column prop="model_key" label="模型" min-width="180" />
        <el-table-column prop="status" label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="row.status === 'success' ? 'success' : 'danger'" size="small">{{ row.status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="latency_ms" label="延迟" width="90" />
        <el-table-column prop="error_message" label="错误" min-width="220" show-overflow-tooltip />
      </el-table>
    </el-card>

    <el-dialog v-model="providerDialogVisible" :title="editingProviderId ? '编辑供应商' : '新增供应商'" width="620px">
      <el-form :model="providerForm" label-width="110px">
        <el-form-item label="Provider Key">
          <el-input v-model="providerForm.provider_key" :disabled="!!editingProviderId" placeholder="sensenova" />
        </el-form-item>
        <el-form-item label="显示名">
          <el-input v-model="providerForm.display_name" />
        </el-form-item>
        <el-form-item label="Base URL">
          <el-input v-model="providerForm.base_url" />
        </el-form-item>
        <el-form-item label="API Key">
          <el-input v-model="providerForm.api_key" type="password" show-password placeholder="留空则不修改已有 Key" />
        </el-form-item>
        <el-form-item label="开关">
          <el-switch v-model="providerForm.enabled" active-text="启用" inactive-text="禁用" />
        </el-form-item>
        <el-form-item label="默认供应商">
          <el-switch v-model="providerForm.is_default" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="providerDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="saveProvider">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="modelDialogVisible" :title="editingModelId ? '编辑模型' : '新增模型'" width="620px">
      <el-form :model="modelForm" label-width="100px">
        <el-form-item label="供应商">
          <el-select v-model="modelForm.provider_id" style="width: 100%">
            <el-option v-for="provider in providers" :key="provider.id" :label="provider.display_name" :value="provider.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="模型名">
          <el-input v-model="modelForm.model_key" placeholder="deepseek-v4-flash" />
        </el-form-item>
        <el-form-item label="显示名">
          <el-input v-model="modelForm.display_name" />
        </el-form-item>
        <el-form-item label="类型">
          <el-select v-model="modelForm.model_type" style="width: 100%" @change="handleModelTypeChange">
            <el-option label="文本对话" value="chat" />
            <el-option label="图片生成" value="image_generation" />
            <el-option label="图像理解" value="vision" />
            <el-option label="向量" value="embedding" />
          </el-select>
        </el-form-item>
        <el-form-item label="调用路径">
          <el-input v-model="modelForm.endpoint_path" placeholder="/chat/completions 或 /images/generations" />
          <div class="form-tip">
            SenseNova U1 Fast 图片生成必须使用 /images/generations，不走 Chat Completions。
          </div>
        </el-form-item>
        <el-form-item label="优先级">
          <el-input-number v-model="modelForm.priority" :min="1" />
        </el-form-item>
        <el-form-item label="启用">
          <el-switch v-model="modelForm.enabled" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="modelForm.notes" type="textarea" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="modelDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="saveModel">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.ai-settings-page {
  max-width: 1180px;
  margin: 0 auto;
  padding: 24px;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 18px;
}

.page-header h2 {
  margin: 14px 0 6px;
}

.page-header p,
.hint {
  color: #909399;
  font-size: 13px;
}

.section-card {
  margin-bottom: 18px;
}

.section-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  font-weight: 600;
}

.provider-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
  gap: 14px;
}

.provider-card {
  border: 1px solid #ebeef5;
  border-radius: 12px;
  padding: 14px;
  background: #fbfcf8;
}

.provider-top {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
}

.provider-top h3 {
  margin: 0 0 4px;
}

.provider-top p,
.provider-meta {
  color: #606266;
  font-size: 13px;
}

.provider-meta {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-top: 10px;
  word-break: break-all;
}

.provider-actions {
  margin-top: 10px;
}

.route-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.route-row {
  display: flex;
  gap: 10px;
  align-items: center;
  flex-wrap: wrap;
  padding: 10px;
  border-radius: 8px;
  background: #f7f9fb;
}

.route-order {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: #303133;
  color: white;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 13px;
}

.route-actions {
  margin-top: 12px;
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}

.test-result {
  margin-top: 12px;
  padding: 12px;
  border-radius: 8px;
  background: #f0f9eb;
  border: 1px solid #d9f0df;
}

.test-result.failed {
  background: #fef0f0;
  border-color: #fbc4c4;
}

.test-result span {
  margin-left: 10px;
  color: #606266;
  font-size: 13px;
}

.test-result pre {
  white-space: pre-wrap;
  word-break: break-word;
  margin-bottom: 0;
}

.form-tip {
  margin-top: 6px;
  color: #909399;
  font-size: 12px;
  line-height: 1.5;
}
</style>
