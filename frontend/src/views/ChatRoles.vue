<script setup>
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { chatApi } from '../api'
import RoleCard from '../components/RoleCard.vue'

const router = useRouter()
const roles = ref([])
const loading = ref(false)
const dialogVisible = ref(false)
const saving = ref(false)
const editingRoleId = ref('')
const form = ref({
  name: '',
  avatar: '🤖',
  description: '',
  system_prompt: '',
  model_preference: '',
  is_public: false
})

const resetForm = () => {
  editingRoleId.value = ''
  form.value = {
    name: '',
    avatar: '🤖',
    description: '',
    system_prompt: '',
    model_preference: '',
    is_public: false
  }
}

const loadRoles = async () => {
  loading.value = true
  try {
    roles.value = await chatApi.getRoles()
  } catch (error) {
    ElMessage.error(error.message)
  } finally {
    loading.value = false
  }
}

onMounted(loadRoles)

const openCreate = () => {
  resetForm()
  dialogVisible.value = true
}

const openEdit = (role) => {
  editingRoleId.value = role.id
  form.value = {
    name: role.name,
    avatar: role.avatar || '🤖',
    description: role.description || '',
    system_prompt: role.system_prompt,
    model_preference: role.model_preference || '',
    is_public: Boolean(role.is_public)
  }
  dialogVisible.value = true
}

const saveRole = async () => {
  if (!form.value.name.trim() || !form.value.system_prompt.trim()) {
    ElMessage.warning('角色名称和系统提示词不能为空')
    return
  }
  saving.value = true
  try {
    const payload = { ...form.value, model_preference: form.value.model_preference || null }
    if (editingRoleId.value) {
      await chatApi.updateRole(editingRoleId.value, payload)
      ElMessage.success('角色已更新')
    } else {
      await chatApi.createRole(payload)
      ElMessage.success('角色已创建')
    }
    dialogVisible.value = false
    await loadRoles()
  } catch (error) {
    ElMessage.error(error.message)
  } finally {
    saving.value = false
  }
}

const deleteRole = async (role) => {
  try {
    await ElMessageBox.confirm(`确定删除「${role.name}」吗？`, '删除角色', { type: 'warning' })
    await chatApi.deleteRole(role.id)
    ElMessage.success('角色已删除')
    await loadRoles()
  } catch {}
}

const startChat = async (role) => {
  try {
    const conversation = await chatApi.createConversation({ role_id: role.id })
    router.push(`/chat/${conversation.id}`)
  } catch (error) {
    ElMessage.error(error.message)
  }
}
</script>

<template>
  <div class="roles-page">
    <header class="page-header">
      <div>
        <el-button link @click="router.push('/chat')">返回聊天</el-button>
        <h1>角色管理</h1>
        <p>预置角色负责快速开聊，自定义角色负责你的特殊场景和长期偏好。</p>
      </div>
      <el-button type="primary" @click="openCreate">新建角色</el-button>
    </header>

    <main v-loading="loading" class="role-grid">
      <RoleCard
        v-for="role in roles"
        :key="role.id"
        :role="role"
        @chat="startChat"
        @edit="openEdit"
        @delete="deleteRole"
      />
    </main>

    <el-dialog v-model="dialogVisible" :title="editingRoleId ? '编辑角色' : '新建角色'" width="680px">
      <el-form :model="form" label-width="96px">
        <el-form-item label="名称">
          <el-input v-model="form.name" placeholder="例如：论文导师" />
        </el-form-item>
        <el-form-item label="头像">
          <el-input v-model="form.avatar" placeholder="emoji 或图片 URL" />
        </el-form-item>
        <el-form-item label="简介">
          <el-input v-model="form.description" placeholder="一句话说明这个角色擅长什么" />
        </el-form-item>
        <el-form-item label="系统提示词">
          <el-input
            v-model="form.system_prompt"
            type="textarea"
            :autosize="{ minRows: 6, maxRows: 12 }"
            placeholder="定义角色身份、回答风格、边界和工作方式"
          />
        </el-form-item>
        <el-form-item label="偏好模型">
          <el-input v-model="form.model_preference" placeholder="可选：填写模型 key，不填走 chat_completion 路由" />
        </el-form-item>
        <el-form-item label="公开">
          <el-switch v-model="form.is_public" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveRole">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.roles-page {
  min-height: 100vh;
  padding: 28px;
  background:
    radial-gradient(circle at top left, rgba(31, 111, 120, 0.16), transparent 36%),
    linear-gradient(135deg, #f7efe4 0%, #eef4ed 100%);
}

.page-header {
  max-width: 1120px;
  margin: 0 auto 22px;
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  gap: 18px;
}

h1 {
  margin: 8px 0 6px;
  color: #24313f;
}

p {
  margin: 0;
  color: #6b7280;
}

.role-grid {
  max-width: 1120px;
  margin: 0 auto;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 16px;
}

@media (max-width: 720px) {
  .page-header {
    display: block;
  }

  .page-header .el-button {
    margin-top: 14px;
  }
}
</style>
