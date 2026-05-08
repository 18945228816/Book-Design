<script setup>
import { computed } from 'vue'
import { marked } from 'marked'
import DOMPurify from 'dompurify'
import hljs from 'highlight.js'
import 'highlight.js/styles/github.css'

const props = defineProps({
  message: {
    type: Object,
    required: true
  },
  streaming: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['copy', 'edit', 'regenerate'])

marked.setOptions({
  breaks: true,
  highlight(code, lang) {
    if (lang && hljs.getLanguage(lang)) {
      return hljs.highlight(code, { language: lang }).value
    }
    return hljs.highlightAuto(code).value
  }
})

const isAssistant = computed(() => props.message.role === 'assistant')
const rendered = computed(() => {
  const raw = props.message.content || ''
  if (!isAssistant.value) {
    return raw.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/\n/g, '<br>')
  }
  return DOMPurify.sanitize(marked.parse(raw))
})
</script>

<template>
  <div class="message-row" :class="{ user: message.role === 'user', assistant: isAssistant }">
    <div class="avatar">{{ isAssistant ? 'AI' : '你' }}</div>
    <div class="bubble">
      <div v-if="message.image_url" class="image-container">
        <img :src="message.image_url" alt="uploaded image" @click="window.open(message.image_url)" />
      </div>
      <div v-if="message.content" class="content markdown-body" v-html="rendered"></div>
      <span v-if="streaming" class="cursor"></span>
      <div class="message-actions">
        <el-button link size="small" @click="$emit('copy', message)">复制</el-button>
        <el-button v-if="message.role === 'user'" link size="small" @click="$emit('edit', message)">编辑</el-button>
        <el-button v-if="isAssistant && message.content" link size="small" @click="$emit('regenerate', message)">重新生成</el-button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.message-row {
  display: grid;
  grid-template-columns: 36px minmax(0, 1fr);
  gap: 12px;
  padding: 18px 24px;
}

.message-row.user {
  background: rgba(255, 255, 255, 0.56);
}

.avatar {
  width: 36px;
  height: 36px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 13px;
  font-weight: 700;
  color: #fff;
  background: #1f6f78;
  box-shadow: 0 10px 24px rgba(31, 111, 120, 0.18);
}

.user .avatar {
  background: #b85c38;
}

.bubble {
  min-width: 0;
  position: relative;
  color: #24313f;
  line-height: 1.75;
}

.content {
  font-size: 15px;
  word-break: break-word;
}

.image-container {
  margin-bottom: 10px;
}

.image-container img {
  max-width: 300px;
  max-height: 300px;
  border-radius: 10px;
  cursor: pointer;
  border: 1px solid rgba(44, 62, 80, 0.12);
}

.message-actions {
  display: flex;
  gap: 8px;
  margin-top: 8px;
  opacity: 0;
  transition: opacity 0.2s;
}

.message-row:hover .message-actions {
  opacity: 1;
}

.cursor {
  display: inline-block;
  width: 7px;
  height: 18px;
  margin-left: 3px;
  vertical-align: middle;
  background: #1f6f78;
  animation: blink 1s steps(2, start) infinite;
}

.markdown-body :deep(pre) {
  padding: 14px;
  overflow: auto;
  border-radius: 10px;
  background: #f5f7f5;
}

.markdown-body :deep(code) {
  border-radius: 5px;
  padding: 2px 5px;
  background: #f1f4f2;
}

.markdown-body :deep(pre code) {
  padding: 0;
  background: transparent;
}

.markdown-body :deep(p) {
  margin: 0 0 10px;
}

.markdown-body :deep(p:last-child) {
  margin-bottom: 0;
}

@keyframes blink {
  50% {
    opacity: 0;
  }
}

@media (max-width: 720px) {
  .message-row {
    padding: 14px;
  }
}
</style>
