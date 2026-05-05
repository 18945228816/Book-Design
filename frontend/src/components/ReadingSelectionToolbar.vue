<script setup>
import { ref, onMounted, onBeforeUnmount, nextTick } from 'vue'

const props = defineProps({
  visible: Boolean,
  position: { type: Object, default: () => ({ x: 0, y: 0 }) }
})

const emit = defineEmits(['record', 'close'])

const toolbarRef = ref(null)

// 确保工具条不超出视口
const adjustPosition = () => {
  if (!toolbarRef.value) return
  const rect = toolbarRef.value.getBoundingClientRect()
  const vw = window.innerWidth
  const vh = window.innerHeight

  let x = props.position.x
  let y = props.position.y

  if (x + rect.width > vw - 10) x = vw - rect.width - 10
  if (x < 10) x = 10
  if (y + rect.height > vh - 10) y = y - rect.height - 10
  if (y < 10) y = 10

  toolbarRef.value.style.left = x + 'px'
  toolbarRef.value.style.top = y + 'px'
}

nextTick(adjustPosition)

const handleClickOutside = (e) => {
  if (toolbarRef.value && !toolbarRef.value.contains(e.target)) {
    emit('close')
  }
}

onMounted(() => {
  document.addEventListener('mousedown', handleClickOutside)
})

onBeforeUnmount(() => {
  document.removeEventListener('mousedown', handleClickOutside)
})
</script>

<template>
  <Teleport to="body">
    <div
      v-if="visible"
      ref="toolbarRef"
      class="selection-toolbar"
      :style="{ left: position.x + 'px', top: position.y + 'px' }"
    >
      <button class="toolbar-btn" @click.stop="emit('record')">
        <el-icon><EditPen /></el-icon>
        记录素材
      </button>
    </div>
  </Teleport>
</template>

<style scoped>
.selection-toolbar {
  position: fixed;
  z-index: 9999;
  background: #1a1a2e;
  border-radius: 8px;
  padding: 4px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.25);
  display: flex;
  gap: 2px;
  animation: fadeInUp 0.15s ease-out;
}

@keyframes fadeInUp {
  from {
    opacity: 0;
    transform: translateY(4px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.toolbar-btn {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 6px 12px;
  border: none;
  background: transparent;
  color: #fff;
  font-size: 13px;
  cursor: pointer;
  border-radius: 6px;
  white-space: nowrap;
  transition: background 0.15s;
}

.toolbar-btn:hover {
  background: rgba(255, 255, 255, 0.15);
}
</style>
