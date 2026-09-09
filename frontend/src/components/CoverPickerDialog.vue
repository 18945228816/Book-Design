<script setup>
import { ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { bookApi } from '../api'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  bookId: { type: String, default: '' },
  currentCoverUrl: { type: String, default: '' }
})
const emit = defineEmits(['update:modelValue', 'applied'])

const methods = [
  { key: 'real', name: '真实封面', icon: '📚', desc: '从微信读书匹配出版社真封面，免费、快' },
  { key: 'ai', name: 'AI 生成', icon: '🎨', desc: 'SenseNova 按书名作者生成，较慢' },
  { key: 'local', name: '本地排版', icon: '🖋️', desc: '用书名作者生成卡片，免费、离线' }
]

const loading = ref({})          // {real: true}
const previews = ref({})          // {real: {url, available, message}}
const selected = ref('')

const close = () => emit('update:modelValue', false)

// 每次打开重置
watch(() => props.modelValue, (open) => {
  if (open) {
    loading.value = {}
    previews.value = {}
    selected.value = ''
  }
})

const fetchOne = async (key) => {
  loading.value[key] = true
  try {
    const res = await bookApi.coverPreview(props.bookId, key)
    if (res.available && res.preview_url) {
      previews.value[key] = { url: res.preview_url, available: true }
      if (!selected.value) selected.value = key
    } else {
      previews.value[key] = { available: false, message: res.message || '该方式暂不可用' }
      ElMessage.warning(res.message || `${key} 不可用`)
    }
  } catch (error) {
    previews.value[key] = { available: false, message: error.message }
    ElMessage.error(error.message)
  } finally {
    loading.value[key] = false
  }
}

const fetchAll = async () => {
  // 逐个获取（AI 较慢，避免并发打爆图片渠道）
  for (const m of methods) {
    if (!previews.value[m.key]?.available) {
      await fetchOne(m.key)
    }
  }
}

const applying = ref(false)
const applyCover = async () => {
  if (!selected.value) {
    ElMessage.warning('请先选择一个封面')
    return
  }
  applying.value = true
  try {
    const updated = await bookApi.setCover(props.bookId, selected.value)
    ElMessage.success('封面已更换')
    emit('applied', updated)
    close()
  } catch (error) {
    ElMessage.error(error.message)
  } finally {
    applying.value = false
  }
}

const imgOnError = (key, e) => {
  previews.value[key] = { available: false, message: '图片加载失败' }
  e.target.style.display = 'none'
}
</script>

<template>
  <el-dialog
    :model-value="modelValue"
    title="更换封面"
    width="760px"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <div class="cover-picker">
      <div class="current">
        <span class="current-label">当前封面</span>
        <img v-if="currentCoverUrl" :src="currentCoverUrl" alt="当前封面" class="current-img" />
        <div v-else class="current-placeholder">无</div>
        <el-button type="primary" plain :loading="Object.values(loading).some(Boolean)" @click="fetchAll">
          一键获取全部
        </el-button>
      </div>

      <div class="options">
        <div
          v-for="m in methods"
          :key="m.key"
          :class="['option-card', { selected: selected === m.key }]"
          @click="previews[m.key]?.available && (selected = m.key)"
        >
          <div class="option-head">
            <span class="option-icon">{{ m.icon }}</span>
            <span class="option-name">{{ m.name }}</span>
            <el-radio
              :model-value="selected"
              :value="m.key"
              :disabled="!previews[m.key]?.available"
              @change="selected = m.key"
              @click.stop
            />
          </div>
          <p class="option-desc">{{ m.desc }}</p>

          <div class="option-preview">
            <div v-if="loading[m.key]" class="preview-state">
              <el-icon class="is-loading"><span class="spinner">⏳</span></el-icon>
              <span>生成中…</span>
            </div>
            <template v-else-if="previews[m.key]?.available">
              <img :src="previews[m.key].url" :alt="m.name" @error="imgOnError(m.key, $event)" />
            </template>
            <div v-else-if="previews[m.key] && !previews[m.key].available" class="preview-state unavailable">
              {{ previews[m.key].message }}
            </div>
            <div v-else class="preview-state placeholder-text">尚未获取</div>
          </div>

          <el-button
            size="small"
            class="fetch-btn"
            :loading="loading[m.key]"
            @click.stop="fetchOne(m.key)"
          >
            {{ previews[m.key]?.available ? '重新获取' : '获取封面' }}
          </el-button>
        </div>
      </div>
    </div>

    <template #footer>
      <el-button @click="close">取消</el-button>
      <el-button type="primary" :disabled="!selected" :loading="applying" @click="applyCover">
        应用选中封面
      </el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.cover-picker {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.current {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 12px;
  background: #f7f9fb;
  border-radius: 10px;
}

.current-label {
  color: #909399;
  font-size: 13px;
}

.current-img {
  width: 46px;
  height: 64px;
  object-fit: cover;
  border-radius: 4px;
  border: 1px solid #ebeef5;
}

.current-placeholder {
  width: 46px;
  height: 64px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #c0c4cc;
  font-size: 12px;
  background: #fff;
  border: 1px dashed #dcdfe6;
  border-radius: 4px;
}

.options {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
}

.option-card {
  border: 2px solid #ebeef5;
  border-radius: 10px;
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  cursor: pointer;
  transition: border-color 0.15s, box-shadow 0.15s;
}

.option-card.selected {
  border-color: #409eff;
  box-shadow: 0 0 0 2px rgba(64, 158, 255, 0.15);
}

.option-head {
  display: flex;
  align-items: center;
  gap: 6px;
}

.option-icon {
  font-size: 18px;
}

.option-name {
  font-weight: 600;
  flex: 1;
}

.option-desc {
  margin: 0;
  color: #909399;
  font-size: 12px;
  line-height: 1.5;
  min-height: 36px;
}

.option-preview {
  width: 100%;
  aspect-ratio: 2 / 3;
  border-radius: 6px;
  overflow: hidden;
  background: #f5f7fa;
  display: flex;
  align-items: center;
  justify-content: center;
}

.option-preview img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.preview-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  color: #909399;
  font-size: 12px;
  text-align: center;
  padding: 8px;
}

.preview-state.unavailable {
  color: #e6a23c;
}

.placeholder-text {
  color: #c0c4cc;
}

.fetch-btn {
  width: 100%;
}
</style>
