<script setup>
import { ref, watch, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { materialApi } from '../api'

const props = defineProps({
  visible: Boolean,
  bookId: String,
  bookTitle: String,
  chapterOrder: Number,
  chapterTitle: String,
  selectedText: String,
  anchorStart: Number,
  anchorEnd: Number
})

const emit = defineEmits(['update:visible', 'saved'])

const content = ref('')
const sourceType = ref('book摘录')
const note = ref('')
const userMood = ref('')
const saving = ref(false)

const sourceTypes = ['book摘录', '微信读书', '自己感悟']
const moodOptions = ['共鸣', '震动', '难过', '讽刺', '愤怒', '困惑', '温暖', '荒凉', '喜欢', '想反驳']

watch(() => props.visible, (val) => {
  if (val) {
    content.value = props.selectedText || ''
    sourceType.value = 'book摘录'
    note.value = ''
    userMood.value = ''
  }
})

const dialogVisible = computed({
  get: () => props.visible,
  set: (val) => emit('update:visible', val)
})

const handleSave = async () => {
  if (!content.value.trim()) {
    ElMessage.warning('请输入内容')
    return
  }
  saving.value = true
  try {
    await materialApi.create({
      content: content.value.trim(),
      source_type: sourceType.value,
      book_id: props.bookId,
      chapter_order: props.chapterOrder,
      selected_text: props.selectedText || undefined,
      anchor_start: props.anchorStart,
      anchor_end: props.anchorEnd,
      locator_text: props.chapterTitle ? `第${props.chapterOrder}章 ${props.chapterTitle}` : undefined,
      note: note.value.trim() || undefined,
      user_mood: userMood.value || undefined,
      status: 'completed',
      entry_mode: 'book_detail_selection'
    })
    ElMessage.success('素材已保存，AI 正在理解这段内容')
    emit('saved')
    emit('update:visible', false)
  } catch (error) {
    ElMessage.error(error.message)
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <el-dialog
    v-model="dialogVisible"
    title="记录素材"
    width="500px"
    :close-on-click-modal="false"
    class="quick-create-dialog"
  >
    <!-- 原文展示 -->
    <div v-if="selectedText" class="selected-text-box">
      <div class="selected-label">选中原文</div>
      <div class="selected-content">{{ selectedText }}</div>
    </div>

    <el-form :model="{ content, sourceType, note }" label-width="70px" class="quick-form">
      <el-form-item label="素材内容">
        <el-input
          v-model="content"
          type="textarea"
          :autosize="{ minRows: 3, maxRows: 6 }"
          placeholder="记录你的摘录或感悟..."
        />
      </el-form-item>

      <el-form-item label="来源">
        <el-radio-group v-model="sourceType" size="small">
          <el-radio-button v-for="t in sourceTypes" :key="t" :label="t">{{ t }}</el-radio-button>
        </el-radio-group>
      </el-form-item>

      <el-form-item label="备注">
        <el-input v-model="note" placeholder="可选" size="small" />
      </el-form-item>

      <el-form-item label="心情">
        <el-select v-model="userMood" placeholder="可选：保存时的感觉" clearable size="small" style="width: 100%">
          <el-option v-for="mood in moodOptions" :key="mood" :label="mood" :value="mood" />
        </el-select>
      </el-form-item>

      <el-form-item label="位置">
        <span class="location-text">《{{ bookTitle }}》 / {{ chapterTitle || `第${chapterOrder}章` }}</span>
      </el-form-item>
    </el-form>

    <template #footer>
      <el-button @click="dialogVisible = false">取消</el-button>
      <el-button type="primary" :loading="saving" @click="handleSave">保存素材</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.selected-text-box {
  background: #fef9e7;
  border-left: 3px solid #f39c12;
  border-radius: 4px;
  padding: 10px 14px;
  margin-bottom: 16px;
}

.selected-label {
  font-size: 12px;
  color: #909399;
  margin-bottom: 4px;
}

.selected-content {
  font-size: 14px;
  color: #303133;
  line-height: 1.6;
  max-height: 120px;
  overflow-y: auto;
  word-break: break-all;
}

.quick-form {
  margin-top: 8px;
}

.location-text {
  font-size: 13px;
  color: #606266;
}
</style>
