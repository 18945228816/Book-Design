<script setup>
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { chatApi, aiAdminApi } from '../api'
import ChatInput from '../components/ChatInput.vue'
import ChatMessage from '../components/ChatMessage.vue'
import ChatSidebar from '../components/ChatSidebar.vue'

const route = useRoute()
const router = useRouter()

const roles = ref([])
const conversations = ref([])
const currentConversation = ref(null)
const messages = ref([])
const selectedRole = ref(null)
const loading = ref(false)
const pageLoading = ref(false)
const abortController = ref(null)
const messagesRef = ref(null)
const draftText = ref('')
const renaming = ref(false)
const renameTitle = ref('')
const availableModels = ref([])
const selectedModel = ref('')

const selectedConversationId = computed(() => currentConversation.value?.id || '')
const selectedRoleId = computed(() => selectedRole.value?.id || currentConversation.value?.role_id || '')
const currentTitle = computed(() => currentConversation.value?.title || selectedRole.value?.name || '选择一个角色开始对话')

const requireLogin = () => {
  if (!localStorage.getItem('token')) {
    router.push('/login')
    return false
  }
  return true
}

const scrollToBottom = async () => {
  await nextTick()
  if (messagesRef.value) {
    messagesRef.value.scrollTop = messagesRef.value.scrollHeight
  }
}

const loadRoles = async () => {
  roles.value = await chatApi.getRoles()
  if (!selectedRole.value && roles.value.length) {
    selectedRole.value = roles.value[0]
  }
}

const loadConversations = async () => {
  conversations.value = await chatApi.getConversations()
}

const loadModels = async () => {
  try {
    const res = await aiAdminApi.getModels({ type: 'chat', enabled: 1 })
    availableModels.value = Array.isArray(res) ? res : (res.items || [])
  } catch {
    availableModels.value = []
  }
}

const loadConversation = async (id) => {
  if (!id) return
  pageLoading.value = true
  try {
    const data = await chatApi.getConversation(id)
    currentConversation.value = data
    selectedRole.value = data.role || roles.value.find(item => item.id === data.role_id) || selectedRole.value
    messages.value = data.messages || []
    await scrollToBottom()
  } catch (error) {
    ElMessage.error(error.message)
  } finally {
    pageLoading.value = false
  }
}

const bootstrap = async () => {
  if (!requireLogin()) return
  pageLoading.value = true
  try {
    await Promise.all([loadRoles(), loadConversations(), loadModels()])
    if (route.params.conversationId) {
      await loadConversation(route.params.conversationId)
    }
  } catch (error) {
    ElMessage.error(error.message)
  } finally {
    pageLoading.value = false
  }
}

onMounted(bootstrap)

watch(() => route.params.conversationId, async (id) => {
  if (id && id !== currentConversation.value?.id) {
    await loadConversation(id)
  }
})

const selectConversation = (conversation) => {
  router.push(`/chat/${conversation.id}`)
}

const selectRole = (role) => {
  selectedRole.value = role
  currentConversation.value = null
  messages.value = []
  router.push('/chat')
}

const createConversation = async (role = selectedRole.value) => {
  if (!role) {
    ElMessage.warning('请先选择一个角色')
    return null
  }
  const conversation = await chatApi.createConversation({ role_id: role.id })
  await loadConversations()
  currentConversation.value = conversation
  selectedRole.value = conversation.role || role
  messages.value = []
  router.push(`/chat/${conversation.id}`)
  return conversation
}

const ensureConversation = async () => {
  if (currentConversation.value) return currentConversation.value
  return createConversation()
}

const sendMessage = async (content, imageFile = null) => {
  const conversation = await ensureConversation()
  if (!conversation) return

  let imageUrl = null
  let messageType = 'text'

  if (imageFile) {
    const formData = new FormData()
    formData.append('file', imageFile)
    try {
      const token = localStorage.getItem('token')
      const res = await fetch('/api/v1/materials/upload-image', {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
        body: formData
      })
      if (res.ok) {
        const data = await res.json()
        imageUrl = data.url || data.image_url
        messageType = 'image'
      }
    } catch {}
  }

  const tempUserId = `temp-user-${Date.now()}`
  const tempAssistantId = `temp-assistant-${Date.now()}`
  messages.value.push({ id: tempUserId, role: 'user', content, conversation_id: conversation.id, message_type: messageType, image_url: imageUrl })
  messages.value.push({ id: tempAssistantId, role: 'assistant', content: '', conversation_id: conversation.id, message_type: 'text', streaming: true })
  await scrollToBottom()

  loading.value = true
  try {
    const response = await chatApi.sendMessageSync(
      conversation.id,
      { content, message_type: messageType, image_url: imageUrl, preferred_model: selectedModel.value || undefined }
    )
    const userIndex = messages.value.findIndex(item => item.id === tempUserId)
    if (userIndex >= 0 && response.user_message) {
      messages.value[userIndex] = response.user_message
    }
    const assistantIndex = messages.value.findIndex(item => item.id === tempAssistantId)
    if (assistantIndex >= 0 && response.assistant_message) {
      messages.value[assistantIndex] = response.assistant_message
    }
    await scrollToBottom()
    /*
      async (event) => {
        if (event.type === 'start') {
          const userIndex = messages.value.findIndex(item => item.id === tempUserId)
          if (userIndex >= 0 && event.user_message) messages.value[userIndex] = event.user_message
          const assistantIndex = messages.value.findIndex(item => item.id === tempAssistantId)
          if (assistantIndex >= 0) messages.value[assistantIndex].id = event.message_id
        } else if (event.type === 'delta') {
          const assistant = messages.value.find(item => item.id !== tempUserId && item.role === 'assistant' && item.streaming)
          if (assistant) assistant.content += event.content
        } else if (event.type === 'done') {
          const assistant = messages.value.find(item => item.role === 'assistant' && item.streaming)
          if (assistant) {
            assistant.content = event.full_content
            assistant.streaming = false
          }
        } else if (event.type === 'error') {
          const assistant = messages.value.find(item => item.role === 'assistant' && item.streaming)
          if (assistant) {
            assistant.content = event.full_content || event.message
            assistant.streaming = false
          }
          ElMessage.error(event.message || 'AI 回复失败')
        }
        await scrollToBottom()
      },
      abortController.value.signal
    )
    */
    await loadConversation(conversation.id)
    await loadConversations()
  } catch (error) {
    messages.value = messages.value.filter(item => item.id !== tempUserId && item.id !== tempAssistantId)
    if (error.name !== 'AbortError') {
      ElMessage.error(error.message)
    }
  } finally {
    loading.value = false
    abortController.value = null
    messages.value.forEach(item => {
      if (item.streaming) item.streaming = false
    })
  }
}

const stopGeneration = () => {
  abortController.value?.abort()
}

const copyMessage = async (message) => {
  await navigator.clipboard.writeText(message.content || '')
  ElMessage.success('已复制')
}

const editMessage = async (message) => {
  try {
    await ElMessageBox.confirm('将删除这条消息及之后的回复，并把内容放回输入框。继续吗？', '编辑消息', { type: 'warning' })
    await chatApi.deleteFromMessage(message.id)
    messages.value = messages.value.filter(item => new Date(item.created_at) < new Date(message.created_at))
    draftText.value = message.content || ''
    ElMessage.success('已回填到输入框，可以修改后重新发送')
  } catch {}
}

const regenerateMessage = async (message) => {
  const index = messages.value.findIndex(item => item.id === message.id)
  const previousUser = [...messages.value].slice(0, index).reverse().find(item => item.role === 'user')
  if (!previousUser) {
    ElMessage.warning('没有找到可重新发送的用户消息')
    return
  }
  try {
    await chatApi.deleteFromMessage(previousUser.id)
    messages.value = messages.value.slice(0, messages.value.findIndex(item => item.id === previousUser.id))
    await sendMessage(previousUser.content || '')
  } catch (error) {
    ElMessage.error(error.message)
  }
}

const deleteCurrentConversation = async () => {
  if (!currentConversation.value) return
  try {
    await ElMessageBox.confirm('确定删除当前对话吗？', '删除对话', { type: 'warning' })
    await chatApi.deleteConversation(currentConversation.value.id)
    currentConversation.value = null
    messages.value = []
    await loadConversations()
    router.push('/chat')
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error(error.message || '删除对话失败')
    }
  }
}

const startRename = () => {
  if (!currentConversation.value) return
  renameTitle.value = currentConversation.value.title || ''
  renaming.value = true
}

const saveRename = async () => {
  if (!currentConversation.value) return
  const newTitle = renameTitle.value.trim()
  if (!newTitle) {
    renaming.value = false
    return
  }
  try {
    await chatApi.updateConversation(currentConversation.value.id, { title: newTitle })
    currentConversation.value.title = newTitle
    await loadConversations()
    ElMessage.success('已重命名')
  } catch (error) {
    ElMessage.error(error.message)
  } finally {
    renaming.value = false
  }
}

const exportConversation = async (format) => {
  if (!currentConversation.value) return
  try {
    const token = localStorage.getItem('token')
    const res = await fetch(`/api/v1/chat/conversations/${currentConversation.value.id}/export?format=${format}`, {
      headers: { Authorization: `Bearer ${token}` }
    })
    if (!res.ok) throw new Error('导出失败')
    const blob = await res.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${currentConversation.value.title || '对话'}.${format}`
    a.click()
    URL.revokeObjectURL(url)
  } catch (error) {
    ElMessage.error(error.message)
  }
}
</script>

<template>
  <div class="chat-shell" v-loading="pageLoading">
    <ChatSidebar
      :roles="roles"
      :conversations="conversations"
      :selected-conversation-id="selectedConversationId"
      :selected-role-id="selectedRoleId"
      @new-chat="createConversation()"
      @select-role="selectRole"
      @select-conversation="selectConversation"
      @open-roles="router.push('/chat/roles')"
    />

    <main class="chat-main">
      <header class="chat-header">
        <div>
          <el-button link @click="router.push('/')">首页</el-button>
          <el-button link @click="router.push('/books')">书籍</el-button>
          <el-button link @click="router.push('/materials')">素材</el-button>
          <el-button link type="primary" @click="router.push('/chat')">AI 对话</el-button>
          <el-button link @click="router.push('/chat/roles')">角色管理</el-button>
        </div>
        <div class="title-block">
          <span class="role-avatar">{{ selectedRole?.avatar || currentConversation?.role?.avatar || '🤖' }}</span>
          <div>
            <div v-if="renaming" class="rename-input">
              <el-input
                v-model="renameTitle"
                size="small"
                @keyup.enter="saveRename"
                @keyup.escape="renaming = false"
                @blur="saveRename"
                autofocus
              />
            </div>
            <h1 v-else @dblclick="startRename" :title="currentConversation ? '双击重命名' : ''">{{ currentTitle }}</h1>
            <p>{{ selectedRole?.description || currentConversation?.role?.description || '选择角色后发送第一条消息。' }}</p>
          </div>
        </div>
        <div class="header-actions">
          <el-dropdown :disabled="!currentConversation" @command="exportConversation">
            <el-button :disabled="!currentConversation">导出</el-button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="md">导出为 Markdown</el-dropdown-item>
                <el-dropdown-item command="txt">导出为 TXT</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
          <el-button :disabled="!currentConversation" @click="deleteCurrentConversation">删除</el-button>
        </div>
      </header>

      <section ref="messagesRef" class="messages">
        <div v-if="messages.length === 0" class="empty-state">
          <div class="orb">{{ selectedRole?.avatar || '✨' }}</div>
          <h2>和 {{ selectedRole?.name || 'AI 角色' }} 开始一段对话</h2>
          <p>试着让它解释一本书、帮你拆解问题，或者陪你把想法揉成更清楚的形状。</p>
        </div>
        <ChatMessage
          v-for="message in messages"
          :key="message.id"
          :message="message"
          :streaming="Boolean(message.streaming)"
          @copy="copyMessage"
          @edit="editMessage"
          @regenerate="regenerateMessage"
        />
      </section>

      <div class="model-selector" v-if="availableModels.length > 0">
        <span class="model-label">模型:</span>
        <el-select
          v-model="selectedModel"
          size="small"
          placeholder="默认模型"
          clearable
          style="width: 200px"
        >
          <el-option
            v-for="model in availableModels"
            :key="model.id"
            :label="`${model.provider_name} - ${model.model_key}`"
            :value="model.model_key"
          />
        </el-select>
      </div>

      <ChatInput
        v-model="draftText"
        :loading="loading"
        :disabled="!selectedRole && !currentConversation"
        @send="sendMessage"
        @stop="stopGeneration"
      />
    </main>
  </div>
</template>

<style scoped>
.chat-shell {
  min-height: 100vh;
  display: flex;
  background:
    radial-gradient(circle at top right, rgba(232, 123, 82, 0.2), transparent 32%),
    linear-gradient(135deg, #f7efe4 0%, #eef4ed 48%, #f8fbff 100%);
}

.chat-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  height: 100vh;
}

.chat-header {
  display: grid;
  grid-template-columns: minmax(220px, 1fr) auto minmax(120px, 1fr);
  gap: 18px;
  align-items: center;
  padding: 16px 24px;
  border-bottom: 1px solid rgba(44, 62, 80, 0.08);
  background: rgba(255, 255, 255, 0.78);
  backdrop-filter: blur(16px);
}

.title-block {
  display: flex;
  align-items: center;
  gap: 12px;
  text-align: left;
}

.role-avatar {
  width: 44px;
  height: 44px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 16px;
  background: #efe4d1;
  font-size: 22px;
}

h1 {
  margin: 0;
  font-size: 18px;
  color: #24313f;
  cursor: default;
}

h1:hover {
  opacity: 0.7;
}

.rename-input {
  margin: 0;
}

.rename-input .el-input {
  font-size: 18px;
  font-weight: 600;
}

p {
  margin: 4px 0 0;
  color: #7b8491;
  font-size: 13px;
}

.header-actions {
  text-align: right;
}

.messages {
  flex: 1;
  overflow-y: auto;
}

.model-selector {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 16px;
  background: rgba(255, 255, 255, 0.86);
  border-top: 1px solid rgba(44, 62, 80, 0.08);
}

.model-label {
  font-size: 13px;
  color: #8a94a6;
  white-space: nowrap;
}

.empty-state {
  max-width: 520px;
  margin: 12vh auto 0;
  padding: 32px;
  text-align: center;
  color: #24313f;
}

.orb {
  width: 82px;
  height: 82px;
  margin: 0 auto 18px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 28px;
  background: linear-gradient(135deg, #fff7df, #d9f0e5);
  box-shadow: 0 18px 48px rgba(31, 111, 120, 0.18);
  font-size: 38px;
}

.empty-state h2 {
  margin: 0 0 10px;
  font-size: 24px;
}

@media (max-width: 900px) {
  .chat-shell {
    display: block;
  }

  .chat-main {
    height: auto;
    min-height: 70vh;
  }

  .chat-header {
    grid-template-columns: 1fr;
  }

  .header-actions {
    text-align: left;
  }
}
</style>
