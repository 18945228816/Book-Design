<script setup>
import { ref, onMounted, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { bookApi } from '../api'

const route = useRoute()
const router = useRouter()
const bookId = route.params.id

const book = ref(null)
const bookTitle = ref('')
const bookAuthor = ref('')
const chapters = ref([])
const loading = ref(false)
const saving = ref(false)
const selectedIndex = ref(0)
const editingTitle = ref(null)
const editTitleValue = ref('')

const currentChapter = computed(() => chapters.value[selectedIndex.value] || null)

// 层级文案：0=简介，1=一级（父级容器，如“篇/卷”），2=二级（具体章节）
const levelLabel = (level) => (level === 0 ? '简介' : level === 1 ? '一级' : '二级')

// 加载书籍和章节
onMounted(async () => {
  loading.value = true
  try {
    const res = await bookApi.getDetail(bookId)
    book.value = res
    bookTitle.value = res.title || ''
    bookAuthor.value = res.author || ''
    chapters.value = (res.chapters || []).map(ch => ({
      title: ch.title,
      content: '', // 先不加载内容，选中时再加载
      level: ch.level,
      parent_title: ch.parent_title,
      chapter_order: ch.chapter_order,
      _loaded: false
    }))
    // 加载第一个章节内容
    if (chapters.value.length > 0) {
      await loadChapterContent(0)
    }
  } catch (error) {
    ElMessage.error(error.message)
    router.push('/books')
  } finally {
    loading.value = false
  }
})

// 加载章节内容
const loadChapterContent = async (index) => {
  const ch = chapters.value[index]
  if (ch._loaded) return
  try {
    const res = await bookApi.getChapter(bookId, ch.chapter_order)
    chapters.value[index].content = res.content
    chapters.value[index]._loaded = true
  } catch (error) {
    ElMessage.error('加载章节内容失败')
  }
}

// 选择章节
const handleSelect = async (index) => {
  selectedIndex.value = index
  await loadChapterContent(index)
}

// 开始重命名
const handleStartRename = (index) => {
  editingTitle.value = index
  editTitleValue.value = chapters.value[index].title
}

// 确认重命名
const handleConfirmRename = (index) => {
  if (editTitleValue.value.trim()) {
    chapters.value[index].title = editTitleValue.value.trim()
  }
  editingTitle.value = null
}

// 依据层级和顺序重算 parent_title：二级挂在它前面最近的一级下。
// 这样升级/降级时，原本挂在该节点下的子章会自动改挂到新的一级。
const recomputeParents = () => {
  let currentParent = null
  for (const ch of chapters.value) {
    if (ch.level === 1) {
      currentParent = ch.title
      ch.parent_title = null
    } else if (ch.level === 2) {
      ch.parent_title = currentParent
    }
    // level 0（简介）不参与父子关系
  }
}

// 切换层级（一级 ↔ 二级）
const handleToggleLevel = (index) => {
  const ch = chapters.value[index]
  if (ch.level === 0) return
  ch.level = ch.level === 1 ? 2 : 1
  recomputeParents()
}

// 新增章节（在当前位置之后插入）
const handleAddChapter = () => {
  const idx = selectedIndex.value
  const insertAt = idx + 1
  const newChapter = {
    title: '新章节',
    content: '',
    level: 2,
    parent_title: null,
    chapter_order: insertAt + 1,
    _loaded: true
  }
  // 继承父级
  if (chapters.value[idx]) {
    newChapter.level = chapters.value[idx].level
    newChapter.parent_title = chapters.value[idx].parent_title
  }
  chapters.value.splice(insertAt, 0, newChapter)
  updateOrders()
  selectedIndex.value = insertAt
}

// 拆分章节
const handleSplit = () => {
  const ch = currentChapter.value
  if (!ch || !ch._loaded) return

  // 在内容中间找一个段落边界来拆分
  const content = ch.content
  const midPoint = Math.floor(content.length / 2)

  // 向前后找最近的段落分隔（双换行）
  let splitPos = -1
  for (let i = 0; i < 200; i++) {
    if (midPoint + i < content.length && content.substring(midPoint + i, midPoint + i + 2) === '\n\n') {
      splitPos = midPoint + i + 2
      break
    }
    if (midPoint - i >= 0 && content.substring(midPoint - i, midPoint - i + 2) === '\n\n') {
      splitPos = midPoint - i + 2
      break
    }
  }

  if (splitPos === -1) {
    ElMessage.warning('未找到合适的拆分位置（需要段落间有空行）')
    return
  }

  const firstPart = content.substring(0, splitPos).trim()
  const secondPart = content.substring(splitPos).trim()

  if (firstPart.length < 20 || secondPart.length < 20) {
    ElMessage.warning('拆分后内容太短，请手动在文本中选择拆分位置')
    return
  }

  const idx = selectedIndex.value
  const originalTitle = chapters.value[idx].title

  // 替换当前章节，插入新章节
  chapters.value[idx].content = firstPart
  chapters.value.splice(idx + 1, 0, {
    title: originalTitle + '（续）',
    content: secondPart,
    level: ch.level,
    parent_title: ch.parent_title,
    chapter_order: ch.chapter_order,
    _loaded: true
  })

  // 更新 chapter_order
  updateOrders()
  ElMessage.success('拆分成功')
}

// 在指定位置拆分（从文本选择）
const handleSplitAtSelection = () => {
  const textarea = document.querySelector('.content-textarea')
  if (!textarea) return

  const ch = currentChapter.value
  if (!ch || !ch._loaded) return

  const selStart = textarea.selectionStart
  const selEnd = textarea.selectionEnd

  if (selStart === selEnd) {
    ElMessage.warning('请先在文本中选择拆分位置')
    return
  }

  const content = ch.content
  const firstPart = content.substring(0, selStart).trim()
  const secondPart = content.substring(selEnd).trim()

  if (firstPart.length < 10 || secondPart.length < 10) {
    ElMessage.warning('拆分后内容太短')
    return
  }

  const idx = selectedIndex.value
  chapters.value[idx].content = firstPart
  chapters.value.splice(idx + 1, 0, {
    title: chapters.value[idx].title + '（续）',
    content: secondPart,
    level: ch.level,
    parent_title: ch.parent_title,
    chapter_order: ch.chapter_order,
    _loaded: true
  })

  updateOrders()
  ElMessage.success('拆分成功')
}

// 合并当前章节和下一章
const handleMerge = async () => {
  const idx = selectedIndex.value
  if (idx >= chapters.value.length - 1) {
    ElMessage.warning('没有下一章可合并')
    return
  }

  const current = chapters.value[idx]
  const next = chapters.value[idx + 1]

  // 确保两个章节内容都已加载
  await loadChapterContent(idx)
  await loadChapterContent(idx + 1)

  await ElMessageBox.confirm(
    `将「${current.title}」和「${next.title}」合并为一章？`,
    '合并确认'
  )

  current.content = current.content + '\n\n' + next.content
  chapters.value.splice(idx + 1, 1)
  updateOrders()
  ElMessage.success('合并成功')
}

// 删除章节（内容并入前一章）
const handleDelete = async () => {
  const idx = selectedIndex.value
  if (chapters.value.length <= 1) {
    ElMessage.warning('至少保留一个章节')
    return
  }

  const ch = chapters.value[idx]
  await ElMessageBox.confirm(
    `删除「${ch.title}」？${idx > 0 ? '内容将并入上一章' : '内容将丢失'}`,
    '删除确认'
  )

  if (idx > 0) {
    await loadChapterContent(idx - 1)
    await loadChapterContent(idx)
    chapters.value[idx - 1].content += '\n\n' + ch.content
  }

  chapters.value.splice(idx, 1)
  if (selectedIndex.value >= chapters.value.length) {
    selectedIndex.value = chapters.value.length - 1
  }
  updateOrders()
  ElMessage.success('已删除')
}

// 更新 chapter_order，并同步父子关系
const updateOrders = () => {
  recomputeParents()
  chapters.value.forEach((ch, i) => {
    ch.chapter_order = i + 1
  })
}

// 保存
const handleSave = async () => {
  saving.value = true
  try {
    if (!bookTitle.value.trim()) {
      ElMessage.warning('请填写书名')
      saving.value = false
      return
    }
    // 保存前加载所有未读取的章节内容
    for (let i = 0; i < chapters.value.length; i++) {
      if (!chapters.value[i]._loaded) {
        await loadChapterContent(i)
      }
    }
    const payload = chapters.value.map(ch => ({
      title: ch.title,
      content: ch.content,
      level: ch.level,
      parent_title: ch.parent_title
    }))

    // 书名/作者有改动时先更新书籍信息，再保存章节
    if (bookTitle.value.trim() !== (book.value?.title || '') ||
        (bookAuthor.value.trim() || null) !== (book.value?.author || null)) {
      await bookApi.update(bookId, {
        title: bookTitle.value.trim(),
        author: bookAuthor.value.trim() || null
      })
    }
    await bookApi.updateChapters(bookId, payload)
    ElMessage.success('保存成功')
    router.push(`/books/${bookId}`)
  } catch (error) {
    ElMessage.error(error.message)
  } finally {
    saving.value = false
  }
}

// 跳过，直接进入阅读
const handleSkip = () => {
  router.push(`/books/${bookId}`)
}

// 返回
const handleBack = () => {
  router.push('/books')
}
</script>

<template>
  <div class="editor-page" v-loading="loading">
    <!-- 顶部工具栏 -->
    <div class="toolbar">
      <div class="toolbar-left">
        <el-button @click="router.push('/')" icon="HomeFilled">首页</el-button>
        <el-button @click="handleBack" icon="ArrowLeft">返回</el-button>
        <div class="book-meta-fields">
          <el-input v-model="bookTitle" size="small" class="book-title-input" placeholder="书名">
            <template #prepend>书名</template>
          </el-input>
          <el-input v-model="bookAuthor" size="small" class="book-author-input" placeholder="作者（可空）">
            <template #prepend>作者</template>
          </el-input>
        </div>
      </div>
      <div class="toolbar-right">
        <el-button @click="handleSkip">跳过，直接阅读</el-button>
        <el-button type="primary" @click="handleSave" :loading="saving">保存修改</el-button>
      </div>
    </div>

    <div class="editor-body">
      <!-- 左侧：章节列表 -->
      <div class="chapter-list-panel">
        <div class="panel-header">
          <span>章节列表（{{ chapters.length }}章）</span>
          <el-button size="small" type="primary" @click="handleAddChapter">+ 新增</el-button>
        </div>
        <div class="chapter-list">
          <div
            v-for="(ch, index) in chapters"
            :key="index"
            :class="['chapter-item', { active: selectedIndex === index, 'level-2-item': ch.level === 2 }]"
            @click="handleSelect(index)"
          >
            <!-- 编辑标题模式 -->
            <div v-if="editingTitle === index" class="title-edit" @click.stop>
              <el-input
                v-model="editTitleValue"
                size="small"
                @keyup.enter="handleConfirmRename(index)"
                @blur="handleConfirmRename(index)"
                autofocus
              />
            </div>
            <!-- 普通显示模式 -->
            <div v-else class="title-display">
              <span class="order">{{ index + 1 }}.</span>
              <span class="title">{{ ch.title }}</span>
              <span class="level-tag" :class="{ 'level-1-tag': ch.level === 1, 'level-2-tag': ch.level === 2 }">
                {{ levelLabel(ch.level) }}
              </span>
            </div>
            <div class="item-actions" @click.stop>
              <el-button size="small" text @click="handleStartRename(index)">重命名</el-button>
              <el-button v-if="ch.level !== 0" size="small" text @click="handleToggleLevel(index)">
                {{ ch.level === 1 ? '降为二级' : '升为一级' }}
              </el-button>
            </div>
          </div>
        </div>
      </div>

      <!-- 右侧：内容预览 -->
      <div class="content-panel">
        <div class="panel-header">
          <span>{{ currentChapter ? currentChapter.title : '请选择章节' }}</span>
          <div v-if="currentChapter" class="content-actions">
            <el-button size="small" @click="handleSplit">自动拆分</el-button>
            <el-button size="small" @click="handleSplitAtSelection">选中处拆分</el-button>
            <el-button size="small" @click="handleMerge">合并下一章</el-button>
            <el-button size="small" type="danger" @click="handleDelete">删除</el-button>
          </div>
        </div>
        <div v-if="currentChapter" class="content-body">
          <el-input
            type="textarea"
            v-model="currentChapter.content"
            class="content-textarea"
            :autosize="{ minRows: 20, maxRows: 40 }"
            placeholder="章节内容"
          />
        </div>
        <el-empty v-else description="点击左侧章节查看内容" />
      </div>
    </div>
  </div>
</template>

<style scoped>
.editor-page {
  height: 100vh;
  display: flex;
  flex-direction: column;
}

.toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 20px;
  border-bottom: 1px solid #eee;
  background: #fff;
}

.toolbar-left {
  display: flex;
  align-items: center;
  gap: 16px;
}

.toolbar-left h3 {
  margin: 0;
}

.book-meta-fields {
  display: flex;
  align-items: center;
  gap: 10px;
}

.book-title-input {
  width: 220px;
}

.book-author-input {
  width: 180px;
}

.toolbar-right {
  display: flex;
  gap: 8px;
}

.editor-body {
  flex: 1;
  display: flex;
  overflow: hidden;
}

.chapter-list-panel {
  width: 280px;
  border-right: 1px solid #eee;
  display: flex;
  flex-direction: column;
  background: #fafafa;
}

.panel-header {
  padding: 12px 16px;
  font-weight: 600;
  border-bottom: 1px solid #eee;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  flex-wrap: wrap;
}

.chapter-list {
  flex: 1;
  overflow-y: auto;
}

.chapter-item {
  padding: 8px 12px;
  cursor: pointer;
  border-bottom: 1px solid #f0f0f0;
  transition: background-color 0.2s;
}

/* 二级章节缩进并加左侧层级线，父子关系一眼可见 */
.chapter-item.level-2-item {
  padding-left: 26px;
  position: relative;
}

.chapter-item.level-2-item::before {
  content: '';
  position: absolute;
  left: 14px;
  top: 6px;
  bottom: 6px;
  width: 2px;
  background: #dcdfe6;
  border-radius: 2px;
}

.chapter-item:hover {
  background-color: #ecf5ff;
}

.chapter-item.active {
  background-color: #d9ecff;
}

.title-display {
  display: flex;
  align-items: center;
  gap: 6px;
}

.order {
  color: #909399;
  font-size: 12px;
  min-width: 20px;
}

.title {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.level-tag {
  font-size: 11px;
  color: #909399;
  background: #f0f0f0;
  padding: 1px 6px;
  border-radius: 3px;
  flex-shrink: 0;
}

.level-tag.level-1-tag {
  color: #409eff;
  background: #ecf5ff;
}

.level-tag.level-2-tag {
  color: #67c23a;
  background: #f0f9eb;
}

.item-actions {
  margin-top: 4px;
}

.content-panel {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.content-actions {
  display: flex;
  gap: 4px;
}

.content-body {
  flex: 1;
  padding: 16px;
  overflow-y: auto;
}

.content-textarea :deep(textarea) {
  font-size: 15px;
  line-height: 1.8;
}
</style>
