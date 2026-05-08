<script setup>
import { ref } from 'vue'
import { ElMessage } from 'element-plus'

const props = defineProps({
  loading: {
    type: Boolean,
    default: false
  },
  disabled: {
    type: Boolean,
    default: false
  },
  placeholder: {
    type: String,
    default: '输入消息，Enter 发送，Shift + Enter 换行'
  }
})

const emit = defineEmits(['send', 'stop'])
const text = defineModel({ default: '' })
const imageFile = ref(null)
const imagePreview = ref('')
const fileInput = ref(null)

const send = () => {
  const content = text.value.trim()
  if ((!content && !imageFile.value) || props.loading || props.disabled) return
  if (imageFile.value) {
    emit('send', content, imageFile.value)
    imageFile.value = null
    imagePreview.value = ''
  } else {
    emit('send', content)
  }
  text.value = ''
}

const handleKeydown = (event) => {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault()
    send()
  }
}

const handleFileSelect = (e) => {
  const file = e.target.files?.[0]
  if (!file) return
  if (!file.type.startsWith('image/')) {
    ElMessage.warning('请选择图片文件')
    return
  }
  if (file.size > 10 * 1024 * 1024) {
    ElMessage.warning('图片大小不能超过10MB')
    return
  }
  imageFile.value = file
  imagePreview.value = URL.createObjectURL(file)
  if (fileInput.value) fileInput.value.value = ''
}

const removeImage = () => {
  if (imagePreview.value) URL.revokeObjectURL(imagePreview.value)
  imageFile.value = null
  imagePreview.value = ''
}

const handlePaste = (e) => {
  const items = e.clipboardData?.items
  if (!items) return
  for (const item of items) {
    if (item.type.startsWith('image/')) {
      e.preventDefault()
      const file = item.getAsFile()
      if (file) {
        imageFile.value = file
        imagePreview.value = URL.createObjectURL(file)
      }
      return
    }
  }
}

const handleDrop = (e) => {
  e.preventDefault()
  const file = e.dataTransfer?.files?.[0]
  if (file && file.type.startsWith('image/')) {
    imageFile.value = file
    imagePreview.value = URL.createObjectURL(file)
  }
}
</script>

<template>
  <div class="chat-input" @drop.prevent="handleDrop" @dragover.prevent>
    <div v-if="imagePreview" class="image-preview">
      <img :src="imagePreview" alt="preview" />
      <el-button class="remove-btn" link @click="removeImage">✕</el-button>
    </div>
    <el-input
      v-model="text"
      type="textarea"
      :autosize="{ minRows: 2, maxRows: 8 }"
      :placeholder="placeholder"
      :disabled="disabled"
      resize="none"
      @keydown="handleKeydown"
      @paste="handlePaste"
    />
    <div class="input-actions">
      <div class="left-actions">
        <input ref="fileInput" type="file" accept="image/*" style="display:none" @change="handleFileSelect" />
        <el-button link @click="fileInput?.click()">📎 图片</el-button>
        <span class="hint">支持 Markdown · 可粘贴/拖拽图片</span>
      </div>
      <div class="buttons">
        <el-button v-if="loading" plain @click="$emit('stop')">停止生成</el-button>
        <el-button type="primary" :loading="loading" :disabled="disabled || (!text.trim() && !imageFile)" @click="send">
          发送
        </el-button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.chat-input {
  padding: 16px;
  border-top: 1px solid rgba(44, 62, 80, 0.08);
  background: rgba(255, 255, 255, 0.86);
  backdrop-filter: blur(16px);
}

.image-preview {
  position: relative;
  display: inline-block;
  margin-bottom: 10px;
}

.image-preview img {
  max-width: 200px;
  max-height: 150px;
  border-radius: 10px;
  border: 1px solid rgba(44, 62, 80, 0.12);
}

.image-preview .remove-btn {
  position: absolute;
  top: -8px;
  right: -8px;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: rgba(0, 0, 0, 0.5);
  color: #fff;
  font-size: 12px;
}

.input-actions {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  margin-top: 10px;
}

.left-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.hint {
  font-size: 12px;
  color: #8a94a6;
}

.buttons {
  display: flex;
  gap: 8px;
}

@media (max-width: 720px) {
  .input-actions {
    align-items: flex-end;
  }

  .hint {
    display: none;
  }
}
</style>
