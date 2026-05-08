<script setup>
defineProps({
  role: {
    type: Object,
    required: true
  }
})

defineEmits(['edit', 'delete', 'chat'])
</script>

<template>
  <article class="role-card">
    <div class="role-head">
      <span class="avatar">{{ role.avatar || '🤖' }}</span>
      <div>
        <h3>{{ role.name }}</h3>
        <el-tag size="small" :type="role.role_type === 'preset' ? 'success' : 'warning'" effect="plain">
          {{ role.role_type === 'preset' ? '系统预置' : '自定义' }}
        </el-tag>
      </div>
    </div>
    <p>{{ role.description || '暂无简介' }}</p>
    <div class="actions">
      <el-button type="primary" link @click="$emit('chat', role)">开始对话</el-button>
      <el-button v-if="role.role_type === 'custom'" link @click="$emit('edit', role)">编辑</el-button>
      <el-button v-if="role.role_type === 'custom'" type="danger" link @click="$emit('delete', role)">删除</el-button>
    </div>
  </article>
</template>

<style scoped>
.role-card {
  padding: 18px;
  border: 1px solid rgba(36, 49, 63, 0.08);
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.84);
  box-shadow: 0 12px 30px rgba(36, 49, 63, 0.06);
}

.role-head {
  display: flex;
  gap: 12px;
  align-items: center;
}

.avatar {
  width: 46px;
  height: 46px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 16px;
  background: #efe4d1;
  font-size: 22px;
}

h3 {
  margin: 0 0 6px;
  color: #24313f;
}

p {
  min-height: 44px;
  margin: 14px 0;
  color: #6b7280;
  line-height: 1.6;
}

.actions {
  display: flex;
  gap: 10px;
}
</style>
