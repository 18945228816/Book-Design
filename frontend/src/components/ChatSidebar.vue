<script setup>
import { computed, ref } from 'vue'

const props = defineProps({
  roles: {
    type: Array,
    default: () => []
  },
  conversations: {
    type: Array,
    default: () => []
  },
  selectedConversationId: {
    type: String,
    default: ''
  },
  selectedRoleId: {
    type: String,
    default: ''
  }
})

const emit = defineEmits(['new-chat', 'select-conversation', 'select-role', 'open-roles'])

const pinnedIds = ref(JSON.parse(localStorage.getItem('pinnedRoleIds') || '[]'))

const pinnedRoles = computed(() => props.roles.filter(r => pinnedIds.value.includes(r.id)))
const unpinnedRoles = computed(() => props.roles.filter(r => !pinnedIds.value.includes(r.id)))

const togglePin = (roleId) => {
  const idx = pinnedIds.value.indexOf(roleId)
  if (idx >= 0) {
    pinnedIds.value.splice(idx, 1)
  } else {
    pinnedIds.value.push(roleId)
  }
  localStorage.setItem('pinnedRoleIds', JSON.stringify(pinnedIds.value))
}

const formatDate = (value) => {
  if (!value) return ''
  const date = new Date(value)
  return date.toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit' })
}
</script>

<template>
  <aside class="chat-sidebar">
    <div class="brand">
      <div>
        <strong>AI 角色对话</strong>
        <span>和不同身份的助手持续交流</span>
      </div>
    </div>

    <el-button class="new-button" type="primary" @click="$emit('new-chat')">+ 新对话</el-button>

    <section v-if="pinnedRoles.length > 0">
      <div class="section-title">
        <span>📌 置顶角色</span>
      </div>
      <div class="role-list">
        <button
          v-for="role in pinnedRoles"
          :key="role.id"
          class="role-item"
          :class="{ active: selectedRoleId === role.id }"
          @click="$emit('select-role', role)"
        >
          <span class="role-avatar">{{ role.avatar || '🤖' }}</span>
          <span class="role-info">
            <strong>{{ role.name }}</strong>
            <small>{{ role.description }}</small>
          </span>
          <span class="pin-btn" @click.stop="togglePin(role.id)" title="取消置顶">📌</span>
        </button>
      </div>
    </section>

    <section>
      <div class="section-title">
        <span>角色</span>
        <el-button link size="small" @click="$emit('open-roles')">管理</el-button>
      </div>
      <div class="role-list">
        <button
          v-for="role in unpinnedRoles"
          :key="role.id"
          class="role-item"
          :class="{ active: selectedRoleId === role.id }"
          @click="$emit('select-role', role)"
        >
          <span class="role-avatar">{{ role.avatar || '🤖' }}</span>
          <span class="role-info">
            <strong>{{ role.name }}</strong>
            <small>{{ role.description }}</small>
          </span>
          <span class="pin-btn" @click.stop="togglePin(role.id)" title="置顶">📌</span>
        </button>
      </div>
    </section>

    <section>
      <div class="section-title">最近对话</div>
      <div class="conversation-list">
        <button
          v-for="item in conversations"
          :key="item.id"
          class="conversation-item"
          :class="{ active: selectedConversationId === item.id }"
          @click="$emit('select-conversation', item)"
        >
          <strong>{{ item.title || '未命名对话' }}</strong>
          <small>
            <el-tag v-if="item.category" size="small" type="info" effect="plain">{{ item.category }}</el-tag>
            {{ item.role?.name || '角色' }} · {{ formatDate(item.updated_at || item.created_at) }}
          </small>
        </button>
      </div>
      <el-empty v-if="conversations.length === 0" description="暂无对话" :image-size="54" />
    </section>
  </aside>
</template>

<style scoped>
.chat-sidebar {
  width: 300px;
  min-height: 100%;
  padding: 18px;
  background: linear-gradient(180deg, #fffaf0 0%, #f4efe4 100%);
  border-right: 1px solid rgba(60, 48, 32, 0.08);
  overflow-y: auto;
}

.brand {
  display: flex;
  justify-content: space-between;
  margin-bottom: 18px;
}

.brand strong {
  display: block;
  font-size: 19px;
  color: #24313f;
}

.brand span {
  display: block;
  margin-top: 4px;
  font-size: 12px;
  color: #7c6f60;
}

.new-button {
  width: 100%;
  margin-bottom: 18px;
}

section {
  margin-bottom: 22px;
}

.section-title {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
  color: #7c6f60;
  font-size: 13px;
  font-weight: 700;
}

.role-list,
.conversation-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.role-item,
.conversation-item {
  width: 100%;
  border: 0;
  border-radius: 14px;
  padding: 10px;
  text-align: left;
  cursor: pointer;
  background: rgba(255, 255, 255, 0.72);
  color: #24313f;
  transition: transform 0.18s, background 0.18s, box-shadow 0.18s;
}

.role-item {
  display: grid;
  grid-template-columns: 34px minmax(0, 1fr) 24px;
  gap: 9px;
  align-items: center;
}

.role-info {
  min-width: 0;
}

.pin-btn {
  opacity: 0;
  cursor: pointer;
  font-size: 14px;
  transition: opacity 0.2s;
}

.role-item:hover .pin-btn {
  opacity: 0.6;
}

.pin-btn:hover {
  opacity: 1 !important;
}

.role-item:hover,
.conversation-item:hover,
.role-item.active,
.conversation-item.active {
  transform: translateY(-1px);
  background: #fff;
  box-shadow: 0 10px 22px rgba(95, 72, 45, 0.12);
}

.role-avatar {
  width: 34px;
  height: 34px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 12px;
  background: #efe4d1;
}

.role-item strong,
.conversation-item strong {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 14px;
}

.role-item small,
.conversation-item small {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  margin-top: 3px;
  color: #8a8175;
  font-size: 12px;
}

@media (max-width: 900px) {
  .chat-sidebar {
    width: 100%;
    min-height: auto;
    border-right: 0;
    border-bottom: 1px solid rgba(60, 48, 32, 0.08);
  }
}
</style>
