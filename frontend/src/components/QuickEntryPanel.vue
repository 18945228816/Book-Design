<script setup>
import { ref, watch, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { bookApi, materialApi } from '../api'

const emit = defineEmits(['saved'])

const content = ref('')
const sourceType = ref('自己感悟')
const bookId = ref('')
const chapterOrder = ref(null)
const selectedText = ref('')
const note = ref('')
const expanded = ref(false)
const saving = ref(false)

const books = ref([])
const chapters = ref([])

const sourceTypes = ['自己感悟', 'book摘录', '微信读书']

onMounted(async () => {
  try {
    const res = await bookApi.getList()
    books.value = res.items || []
  } catch {}
})

// 书籍变化时加载章节
watch(bookId, async (newVal) => {
  chapterOrder.value = null
  chapters.value = []
  if (!newVal) return
  try {
    const res = await bookApi.getDetail(newVal)
    chapters.value = (res.chapters || []).map(ch => ({
      order: ch.chapter_order,
      title: ch.title,
      level: ch.level
    }))
  } catch {}
})

const handleFocus = () => {
  expanded.value = true
}

const handleSaveDraft = async () => {
  if (!content.value.trim()) {
    ElMessage.warning('请输入内容')
    return
  }
  if (!bookId.value) {
    ElMessage.warning('请选择关联书籍')
    return
  }
  if (!chapterOrder.value) {
    ElMessage.warning('请选择关联章节')
    return
  }

  saving.value = true
  try {
    await materialApi.create({
      content: content.value.trim(),
      source_type: sourceType.value,
      book_id: bookId.value,
      chapter_order: chapterOrder.value,
      selected_text: selectedText.value.trim() || undefined,
      note: note.value.trim() || undefined,
      status: 'draft',
      entry_mode: 'home_quick'
    })
    ElMessage.success('已保存到草稿')
    resetForm()
    emit('saved')
  } catch (error) {
    ElMessage.error(error.message)
  } finally {
    saving.value = false
  }
}

const handleSaveComplete = async () => {
  if (!content.value.trim()) {
    ElMessage.warning('请输入内容')
    return
  }
  if (!bookId.value) {
    ElMessage.warning('请选择关联书籍')
    return
  }
  if (!chapterOrder.value) {
    ElMessage.warning('请选择关联章节')
    return
  }

  saving.value = true
  try {
    await materialApi.create({
      content: content.value.trim(),
      source_type: sourceType.value,
      book_id: bookId.value,
      chapter_order: chapterOrder.value,
      selected_text: selectedText.value.trim() || undefined,
      note: note.value.trim() || undefined,
      status: 'completed',
      entry_mode: 'home_quick'
    })
    ElMessage.success('素材已保存')
    resetForm()
    emit('saved')
  } catch (error) {
    ElMessage.error(error.message)
  } finally {
    saving.value = false
  }
}

const resetForm = () => {
  content.value = ''
  sourceType.value = '自己感悟'
  bookId.value = ''
  chapterOrder.value = null
  selectedText.value = ''
  note.value = ''
  expanded.value = false
}
</script>

<template>
  <div class="quick-entry">
    <div class="entry-header">
      <el-icon :size="18"><EditPen /></el-icon>
      <span>快速录入</span>
    </div>

    <el-input
      v-model="content"
      type="textarea"
      :autosize="{ minRows: 2, maxRows: 6 }"
      placeholder="记下一句话、一段摘录、一个模糊感受..."
      @focus="handleFocus"
      class="entry-input"
    />

    <!-- 展开的详细字段 -->
    <div v-if="expanded" class="entry-details">
      <div class="detail-row">
        <el-radio-group v-model="sourceType" size="small">
          <el-radio-button v-for="t in sourceTypes" :key="t" :label="t">{{ t }}</el-radio-button>
        </el-radio-group>
      </div>

      <div class="detail-row">
        <el-select v-model="bookId" placeholder="选择关联书籍" size="small" style="width: 100%">
          <el-option v-for="b in books" :key="b.id" :label="b.title" :value="b.id" />
        </el-select>
      </div>

      <div class="detail-row" v-if="bookId && chapters.length > 0">
        <el-select v-model="chapterOrder" placeholder="选择关联章节" size="small" style="width: 100%" filterable>
          <el-option
            v-for="ch in chapters"
            :key="ch.order"
            :label="`${ch.order}. ${ch.title}`"
            :value="ch.order"
          />
        </el-select>
      </div>

      <div class="detail-row">
        <el-input
          v-model="selectedText"
          type="textarea"
          :autosize="{ minRows: 1, maxRows: 3 }"
          placeholder="粘贴触发这段记录的原文（选填，支持精确高亮）"
          size="small"
        />
      </div>

      <div class="detail-row">
        <el-input
          v-model="note"
          placeholder="补充想法（选填）"
          size="small"
        />
      </div>

      <div class="entry-actions">
        <el-button size="small" @click="resetForm">清空</el-button>
        <div class="action-right">
          <el-button size="small" :loading="saving" @click="handleSaveDraft">
            保存草稿
          </el-button>
          <el-button type="primary" size="small" :loading="saving" @click="handleSaveComplete">
            保存并完善
          </el-button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.quick-entry {
  background: #fff;
  border-radius: 12px;
  padding: 20px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.06);
}

.entry-header {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 15px;
  font-weight: 600;
  color: #303133;
  margin-bottom: 12px;
}

.entry-input :deep(textarea) {
  font-size: 15px;
  line-height: 1.6;
}

.entry-details {
  margin-top: 12px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.detail-row {
  display: flex;
  gap: 8px;
}

.entry-actions {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 4px;
}

.action-right {
  display: flex;
  gap: 8px;
}
</style>
