<script setup>
import { ref, computed, onMounted, onBeforeUnmount, nextTick, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { bookApi, materialApi } from '../api'
import ReadingSelectionToolbar from '../components/ReadingSelectionToolbar.vue'
import MaterialQuickCreateDialog from '../components/MaterialQuickCreateDialog.vue'

const route = useRoute()
const router = useRouter()
const bookId = route.params.id

const book = ref(null)
const chapters = ref([])
const loading = ref(false)
const currentChapter = ref(null)
const expandedSections = ref({})
const sidebarVisible = ref(true)
const isMobile = ref(window.innerWidth <= 768)

const materialDialogVisible = ref(false)
const materialForm = ref({
  content: '',
  source_type: 'book摘录',
  note: '',
  userMood: '',
  selectedText: '',
  anchorStart: null,
  anchorEnd: null
})
const materialSaving = ref(false)

const chapterContentRef = ref(null)
const chapterHighlights = ref([])
const focusedMaterialId = ref('')
const restoringProgress = ref(false)
const saveProgressTimer = ref(null)

const selectionToolbarVisible = ref(false)
const selectionToolbarPos = ref({ x: 0, y: 0 })
const quickDialogVisible = ref(false)
const selectionData = ref({
  selectedText: '',
  anchorStart: null,
  anchorEnd: null
})

const sourceTypes = ['book摘录', '微信读书', '自己感悟']
const moodOptions = ['共鸣', '震动', '难过', '讽刺', '愤怒', '困惑', '温暖', '荒凉', '喜欢', '想反驳']

const escapeHtml = (str = '') => {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
}

const escapeRegExp = (str = '') => {
  return String(str).replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

const normalizeHighlightText = (item) => {
  return (item.selected_text || item.content?.substring(0, 60) || '').trim()
}

const renderParagraph = (text) => {
  let html = escapeHtml(text)
  const highlights = [...chapterHighlights.value]
    .map((item) => ({ ...item, highlightText: normalizeHighlightText(item) }))
    .filter((item) => item.highlightText)
    .sort((a, b) => b.highlightText.length - a.highlightText.length)

  for (const item of highlights) {
    const escapedText = escapeHtml(item.highlightText)
    const regex = new RegExp(`(${escapeRegExp(escapedText)})`, 'g')
    const className = item.id === focusedMaterialId.value
      ? 'material-highlight focused'
      : 'material-highlight'

    html = html.replace(
      regex,
      `<mark class="${className}" data-material-id="${item.id}">$1</mark>`
    )
  }

  return html
}

const sections = computed(() => {
  const chs = chapters.value
  if (chs.length === 0) return []

  const hasParent = chs.some(c => c.level === 0 || c.level === 1)
  if (!hasParent) {
    return chs.map(ch => ({
      title: ch.title,
      chapter_order: ch.chapter_order,
      children: [],
      hasOwnContent: true
    }))
  }

  const result = []
  let current = null
  for (const ch of chs) {
    if (ch.level === 0 || ch.level === 1) {
      current = {
        title: ch.title,
        chapter_order: ch.chapter_order,
        children: [],
        hasOwnContent: ch.level === 0
      }
      result.push(current)
    } else if (current) {
      current.children.push(ch)
    } else {
      current = {
        title: ch.title,
        chapter_order: ch.chapter_order,
        children: [],
        hasOwnContent: true
      }
      result.push(current)
    }
  }

  for (const section of result) {
    if (section.children.length === 0) {
      section.hasOwnContent = true
    }
  }
  return result
})

const fetchBook = async () => {
  loading.value = true
  try {
    const res = await bookApi.getDetail(bookId)
    book.value = res
    chapters.value = res.chapters || []
    if (sections.value.length > 0) {
      expandedSections.value[sections.value[0].title] = true
    }
  } catch (error) {
    ElMessage.error(error.message)
    router.push('/books')
  } finally {
    loading.value = false
  }
}

const toggleSidebar = () => {
  sidebarVisible.value = !sidebarVisible.value
}

const handleResize = () => {
  isMobile.value = window.innerWidth <= 768
  if (isMobile.value) {
    sidebarVisible.value = false
  }
}

onMounted(() => {
  fetchBook()
  document.addEventListener('mouseup', handleMouseUp)
  window.addEventListener('resize', handleResize)
  if (isMobile.value) {
    sidebarVisible.value = false
  }
})

onBeforeUnmount(() => {
  document.removeEventListener('mouseup', handleMouseUp)
  window.removeEventListener('resize', handleResize)
  if (saveProgressTimer.value) {
    clearTimeout(saveProgressTimer.value)
  }
  saveReadingProgress()
})

const toggleSection = (title) => {
  expandedSections.value[title] = !expandedSections.value[title]
}

const loadChapterHighlights = async (chapterOrder, focusMaterialId = '') => {
  try {
    const res = await materialApi.getList({
      book_id: bookId,
      chapter_order: chapterOrder
    })
    chapterHighlights.value = (res.items || []).filter((item) => {
      return normalizeHighlightText(item) || (item.anchor_start != null && item.anchor_end != null)
    })
    focusedMaterialId.value = focusMaterialId
  } catch {
    chapterHighlights.value = []
    focusedMaterialId.value = focusMaterialId
  }
}

const buildChapterQuery = (order, clearMaterialQuery) => {
  if (clearMaterialQuery) {
    return { chapter: order }
  }

  return {
    ...route.query,
    chapter: order
  }
}

const findFirstReadableOrder = () => {
  for (const section of sections.value) {
    if (section.hasOwnContent) return section.chapter_order
    if (section.children.length > 0) return section.children[0].chapter_order
  }
  return null
}

const restoreScrollPosition = (progress) => {
  nextTick(() => {
    const el = chapterContentRef.value
    if (!el) return

    const maxScroll = Math.max(el.scrollHeight - el.clientHeight, 0)
    const scrollTop = progress.scroll_top > 0
      ? progress.scroll_top
      : Math.round(maxScroll * (progress.scroll_ratio || 0))

    el.scrollTop = Math.min(scrollTop, maxScroll)
  })
}

const getReadingProgressPayload = () => {
  const el = chapterContentRef.value
  if (!el || !currentChapter.value) return null

  const maxScroll = Math.max(el.scrollHeight - el.clientHeight, 1)
  return {
    chapter_order: currentChapter.value.chapter_order,
    scroll_top: Math.round(el.scrollTop),
    scroll_ratio: Number((el.scrollTop / maxScroll).toFixed(4))
  }
}

const saveReadingProgress = async () => {
  if (restoringProgress.value) return

  const payload = getReadingProgressPayload()
  if (!payload) return

  try {
    await bookApi.saveReadingProgress(bookId, payload)
  } catch {
    // Reading progress is a background convenience; avoid interrupting reading.
  }
}

const scheduleSaveReadingProgress = () => {
  if (restoringProgress.value || !currentChapter.value) return

  if (saveProgressTimer.value) {
    clearTimeout(saveProgressTimer.value)
  }

  saveProgressTimer.value = setTimeout(() => {
    saveProgressTimer.value = null
    saveReadingProgress()
  }, 800)
}

const handleChapterScroll = () => {
  scheduleSaveReadingProgress()
}

const restoreReadingProgress = async () => {
  restoringProgress.value = true
  try {
    const progress = await bookApi.getReadingProgress(bookId)
    if (progress?.chapter_order) {
      await handleViewChapterByOrder(progress.chapter_order, { skipProgressSave: true })
      restoreScrollPosition(progress)
      return
    }

    const firstOrder = findFirstReadableOrder()
    if (firstOrder) {
      await handleViewChapterByOrder(firstOrder, { skipProgressSave: true })
    }
  } catch {
    const firstOrder = findFirstReadableOrder()
    if (firstOrder) {
      await handleViewChapterByOrder(firstOrder, { skipProgressSave: true })
    }
  } finally {
    setTimeout(() => {
      restoringProgress.value = false
    }, 0)
  }
}

const handleViewChapter = async (chapter) => {
  await handleViewChapterByOrder(chapter.chapter_order, { clearMaterialQuery: true })
}

const handleViewChapterByOrder = async (order, options = {}) => {
  const {
    focusMaterialId = '',
    loadHighlights = true,
    clearMaterialQuery = false,
    skipProgressSave = false
  } = options

  try {
    chapterHighlights.value = []
    focusedMaterialId.value = focusMaterialId

    const res = await bookApi.getChapter(bookId, order)
    currentChapter.value = res
    expandSectionForOrder(order)

    if (String(order) !== String(route.query.chapter) || clearMaterialQuery) {
      router.replace({ query: buildChapterQuery(order, clearMaterialQuery) })
    }

    if (loadHighlights) {
      await loadChapterHighlights(order, focusMaterialId)
    }

    await nextTick()
    if (!skipProgressSave && !focusMaterialId && chapterContentRef.value) {
      chapterContentRef.value.scrollTop = 0
    }
    if (!skipProgressSave && !restoringProgress.value) {
      scheduleSaveReadingProgress()
    }
  } catch (error) {
    ElMessage.error(error.message)
  }
}

const hasContent = (ch) => {
  if (ch.level === 2 || ch.level === 0) return true
  return !chapters.value.some(c => c.level === 2 && c.parent_title === ch.title)
}

const handlePrev = () => {
  if (!currentChapter.value) return
  let order = currentChapter.value.chapter_order - 1
  while (order >= 1) {
    const ch = chapters.value.find(c => c.chapter_order === order)
    if (ch && hasContent(ch)) {
      handleViewChapterByOrder(order, { clearMaterialQuery: true })
      return
    }
    order--
  }
}

const handleNext = () => {
  if (!currentChapter.value) return
  let order = currentChapter.value.chapter_order + 1
  while (order <= chapters.value.length) {
    const ch = chapters.value.find(c => c.chapter_order === order)
    if (ch && hasContent(ch)) {
      handleViewChapterByOrder(order, { clearMaterialQuery: true })
      return
    }
    order++
  }
}

const expandSectionForOrder = (order) => {
  for (const section of sections.value) {
    if (section.chapter_order === order) {
      expandedSections.value[section.title] = true
      return
    }
    for (const ch of section.children) {
      if (ch.chapter_order === order) {
        expandedSections.value[section.title] = true
        return
      }
    }
  }
}

const handleBack = () => {
  router.push('/books')
}

const calcAnchorOffsets = (selectedText) => {
  if (!currentChapter.value || !selectedText) return { start: null, end: null }
  const content = currentChapter.value.content
  const idx = content.indexOf(selectedText)
  if (idx === -1) return { start: null, end: null }
  return { start: idx, end: idx + selectedText.length }
}

const getSelectedChapterText = () => {
  const selection = window.getSelection()
  if (!selection || selection.isCollapsed || !selection.toString().trim()) return ''

  const range = selection.getRangeAt(0)
  const contentEl = chapterContentRef.value
  if (!contentEl || !contentEl.contains(range.commonAncestorContainer)) return ''

  return selection.toString().trim()
}

const handleOpenMaterial = () => {
  const selectedText = getSelectedChapterText()
  const { start, end } = calcAnchorOffsets(selectedText)

  materialForm.value = {
    content: selectedText || '',
    source_type: 'book摘录',
    note: '',
    userMood: '',
    selectedText,
    anchorStart: start,
    anchorEnd: end
  }
  materialDialogVisible.value = true
}

const handleSaveMaterial = async () => {
  if (!materialForm.value.content.trim()) {
    ElMessage.warning('请输入素材内容')
    return
  }
  materialSaving.value = true
  try {
    const created = await materialApi.create({
      content: materialForm.value.content,
      source_type: materialForm.value.source_type,
      book_id: bookId,
      chapter_order: currentChapter.value?.chapter_order,
      selected_text: materialForm.value.selectedText || undefined,
      anchor_start: materialForm.value.anchorStart,
      anchor_end: materialForm.value.anchorEnd,
      locator_text: currentChapter.value?.title
        ? `${currentChapter.value.chapter_order}. ${currentChapter.value.title}`
        : undefined,
      note: materialForm.value.note || undefined,
      user_mood: materialForm.value.userMood || undefined,
      status: 'completed',
      entry_mode: 'book_detail'
    })
    ElMessage.success('素材已保存，AI 正在理解这段内容')
    materialDialogVisible.value = false
    await loadChapterHighlights(currentChapter.value?.chapter_order, created.id)
    scrollToFocusedHighlight(created.id)
  } catch (error) {
    ElMessage.error(error.message)
  } finally {
    materialSaving.value = false
  }
}

const handleMouseUp = () => {
  requestAnimationFrame(() => {
    const sel = window.getSelection()
    if (!sel || sel.isCollapsed || !sel.toString().trim()) {
      selectionToolbarVisible.value = false
      return
    }

    const range = sel.getRangeAt(0)
    const contentEl = chapterContentRef.value
    if (!contentEl || !contentEl.contains(range.commonAncestorContainer)) {
      selectionToolbarVisible.value = false
      return
    }

    const text = sel.toString().trim()
    if (text.length < 2 || /^[\s\p{P}]+$/u.test(text)) {
      selectionToolbarVisible.value = false
      return
    }

    const rect = range.getBoundingClientRect()
    selectionToolbarPos.value = {
      x: rect.left + rect.width / 2 - 50,
      y: rect.bottom + 8
    }
    selectionData.value.selectedText = text
    selectionToolbarVisible.value = true
  })
}

const handleSelectionRecord = () => {
  selectionToolbarVisible.value = false
  const text = selectionData.value.selectedText
  const { start, end } = calcAnchorOffsets(text)
  selectionData.value.anchorStart = start
  selectionData.value.anchorEnd = end
  quickDialogVisible.value = true
}

const handleQuickSaved = async () => {
  quickDialogVisible.value = false
  const tempId = '__recent_saved__'
  const tempHighlight = {
    id: tempId,
    selected_text: selectionData.value.selectedText,
    content: selectionData.value.selectedText
  }
  chapterHighlights.value = [
    tempHighlight,
    ...chapterHighlights.value.filter(item => item.id !== tempId)
  ]
  focusedMaterialId.value = tempId

  if (currentChapter.value?.chapter_order) {
    await loadChapterHighlights(currentChapter.value.chapter_order)
  }
}

const scrollToFocusedHighlight = (materialId) => {
  nextTick(() => {
    if (!chapterContentRef.value) return

    const marks = Array.from(chapterContentRef.value.querySelectorAll('.material-highlight'))
    const target = marks.find(mark => mark.dataset.materialId === String(materialId)) || marks[0]

    if (target) {
      target.scrollIntoView({ behavior: 'smooth', block: 'center' })
    } else {
      ElMessage.warning('未找到精确原文片段，已打开对应章节')
    }
  })
}

const loadMaterialLocation = async (materialId) => {
  try {
    const loc = await materialApi.getLocation(materialId)

    if (!loc.book_id || !loc.chapter_order) {
      ElMessage.warning('这条素材没有绑定原文位置')
      return
    }

    await handleViewChapterByOrder(loc.chapter_order, {
      focusMaterialId: materialId,
      loadHighlights: true,
      skipProgressSave: true
    })
    scrollToFocusedHighlight(materialId)
  } catch {
    ElMessage.error('无法加载素材定位信息')
  }
}

watch(chapters, async (newVal) => {
  if (newVal.length === 0) return

  const materialId = route.query.material
  if (materialId) {
    await loadMaterialLocation(materialId)
    return
  }

  const order = Number(route.query.chapter)
  if (order && order >= 1 && order <= newVal.length) {
    await handleViewChapterByOrder(order, { skipProgressSave: true })
    return
  }

  await restoreReadingProgress()
})
</script>

<template>
  <div class="book-detail" v-loading="loading">
    <div class="page-header">
      <el-button @click="router.push('/')" icon="HomeFilled">首页</el-button>
      <el-button @click="handleBack" icon="ArrowLeft">返回</el-button>
      <h2 v-if="book">{{ book.title }}</h2>
      <el-button v-if="book" type="warning" @click="router.push(`/books/${bookId}/edit`)">编辑章节</el-button>
    </div>

    <el-card v-if="book" class="info-card">
      <div class="info-content">
        <img src="/书封面.webp" alt="封面" class="detail-cover" />
        <div class="book-meta">
          <h3 class="detail-title">{{ book.title }}</h3>
          <p><strong>作者：</strong>{{ book.author || '未知' }}</p>
          <p><strong>类型：</strong>{{ book.file_type }}</p>
          <p><strong>章节：</strong>{{ book.chapters_count }} 章</p>
        </div>
      </div>
    </el-card>

    <div class="content-area">
      <div v-if="isMobile && sidebarVisible" class="sidebar-overlay" @click="sidebarVisible = false"></div>
      <div class="sidebar-toggle" @click="toggleSidebar">
        <el-icon :size="20">
          <component :is="sidebarVisible ? 'Fold' : 'Expand'" />
        </el-icon>
      </div>
      <transition name="slide">
        <el-card v-show="sidebarVisible" class="chapters-card">
          <template #header>
            <div class="sidebar-header">
              <span>章节列表</span>
              <el-icon class="close-btn" @click="sidebarVisible = false"><Close /></el-icon>
            </div>
          </template>
        <div class="chapters-list">
          <div v-for="section in sections" :key="section.title" class="section-group">
            <div
              v-if="section.children.length === 0"
              :class="['chapter-item', 'standalone', { active: currentChapter?.chapter_order === section.chapter_order }]"
              @click="handleViewChapterByOrder(section.chapter_order, { clearMaterialQuery: true })"
            >
              {{ section.title }}
            </div>
            <template v-else>
              <div class="section-header" @click="toggleSection(section.title)">
                <span class="arrow" :class="{ expanded: expandedSections[section.title] }">&#9654;</span>
                <span class="section-title">{{ section.title }}</span>
                <span class="child-count">{{ section.children.length }}章</span>
              </div>
              <div v-if="expandedSections[section.title]" class="section-children">
                <div
                  v-if="section.hasOwnContent"
                  :class="['chapter-item', { active: currentChapter?.chapter_order === section.chapter_order }]"
                  @click.stop="handleViewChapterByOrder(section.chapter_order, { clearMaterialQuery: true })"
                >
                  查看简介
                </div>
                <div
                  v-for="ch in section.children"
                  :key="ch.id"
                  :class="['chapter-item', { active: currentChapter?.chapter_order === ch.chapter_order }]"
                  @click="handleViewChapter(ch)"
                >
                  {{ ch.title }}
                </div>
              </div>
            </template>
          </div>
        </div>
        </el-card>
      </transition>

      <el-card class="content-card">
        <template #header>
          <div class="content-header">
            <span>{{ currentChapter ? currentChapter.title : '请选择章节' }}</span>
            <el-button v-if="currentChapter" type="success" size="small" @click="handleOpenMaterial">
              <el-icon><EditPen /></el-icon>
              记录素材
            </el-button>
          </div>
        </template>

        <div
          v-if="currentChapter"
          class="chapter-content"
          ref="chapterContentRef"
          @scroll="handleChapterScroll"
        >
          <p
            v-for="(para, i) in currentChapter.content.split('\n').filter(p => p.trim())"
            :key="i"
            v-html="renderParagraph(para)"
          ></p>
        </div>
        <el-empty v-else description="点击左侧章节查看内容" />

        <div v-if="currentChapter" class="chapter-nav">
          <el-button
            :disabled="currentChapter.chapter_order <= 1"
            @click="handlePrev"
            icon="ArrowLeft"
          >上一章</el-button>
          <span class="nav-info">{{ currentChapter.chapter_order }} / {{ chapters.length }}</span>
          <el-button
            :disabled="currentChapter.chapter_order >= chapters.length"
            @click="handleNext"
          >下一章<el-icon class="el-icon--right"><ArrowRight /></el-icon></el-button>
        </div>
      </el-card>
    </div>

    <el-dialog v-model="materialDialogVisible" title="记录素材" width="550px">
      <el-form :model="materialForm" label-width="80px">
        <el-form-item label="内容">
          <el-input
            v-model="materialForm.content"
            type="textarea"
            :autosize="{ minRows: 4, maxRows: 8 }"
            placeholder="粘贴你摘录的金句、段评或感悟..."
          />
        </el-form-item>
        <el-form-item label="来源">
          <el-radio-group v-model="materialForm.source_type">
            <el-radio-button v-for="type in sourceTypes" :key="type" :label="type">{{ type }}</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="materialForm.note" placeholder="可选，记录你的想法" />
        </el-form-item>
        <el-form-item label="心情">
          <el-select v-model="materialForm.userMood" placeholder="可选：保存时的感觉" clearable style="width: 100%">
            <el-option v-for="mood in moodOptions" :key="mood" :label="mood" :value="mood" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="book && currentChapter" label="关联">
          <span style="color: #606266">《{{ book.title }}》 · {{ currentChapter.title }}</span>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="materialDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="materialSaving" @click="handleSaveMaterial">保存</el-button>
      </template>
    </el-dialog>

    <ReadingSelectionToolbar
      :visible="selectionToolbarVisible"
      :position="selectionToolbarPos"
      @record="handleSelectionRecord"
      @close="selectionToolbarVisible = false"
    />

    <MaterialQuickCreateDialog
      v-model:visible="quickDialogVisible"
      :book-id="bookId"
      :book-title="book?.title"
      :chapter-order="currentChapter?.chapter_order"
      :chapter-title="currentChapter?.title"
      :selected-text="selectionData.selectedText"
      :anchor-start="selectionData.anchorStart"
      :anchor-end="selectionData.anchorEnd"
      @saved="handleQuickSaved"
    />
  </div>
</template>

<style scoped>
.page-header {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 20px;
}

.page-header h2 {
  margin: 0;
}

.info-card {
  margin-bottom: 20px;
}

.info-content {
  display: flex;
  gap: 20px;
  align-items: flex-start;
}

.detail-cover {
  width: 100px;
  height: 140px;
  object-fit: cover;
  border-radius: 4px;
  flex-shrink: 0;
}

.book-meta {
  color: #606266;
}

.book-meta p {
  margin: 4px 0;
}

.detail-title {
  margin: 0 0 12px;
}

.content-area {
  display: flex;
  gap: 20px;
  position: relative;
}

.sidebar-toggle {
  position: fixed;
  left: 10px;
  top: 80px;
  width: 36px;
  height: 36px;
  background: #409eff;
  color: white;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  z-index: 1000;
  transition: all 0.3s;
  box-shadow: 0 2px 8px rgba(64, 158, 255, 0.4);
}

.sidebar-toggle:hover {
  background: #337ecc;
  transform: scale(1.1);
}

.chapters-card {
  width: 300px;
  flex-shrink: 0;
  transition: all 0.3s ease;
}

.sidebar-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.close-btn {
  cursor: pointer;
  color: #909399;
  transition: color 0.2s;
}

.close-btn:hover {
  color: #409eff;
}

.slide-enter-active,
.slide-leave-active {
  transition: all 0.3s ease;
}

.slide-enter-from,
.slide-leave-to {
  transform: translateX(-100%);
  opacity: 0;
}

.sidebar-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  z-index: 998;
}

/* 移动端适配 */
@media (max-width: 768px) {
  .content-area {
    flex-direction: column;
  }

  .sidebar-toggle {
    position: fixed;
    right: 16px;
    bottom: 80px;
    left: auto;
    top: auto;
    width: 48px;
    height: 48px;
    border-radius: 50%;
    box-shadow: 0 2px 12px rgba(0, 0, 0, 0.2);
    z-index: 1000;
  }

  .chapters-card {
    position: fixed;
    left: 0;
    top: 0;
    bottom: 0;
    width: 80%;
    max-width: 320px;
    z-index: 999;
    border-radius: 0;
    overflow-y: auto;
  }

  .slide-enter-active,
  .slide-leave-active {
    transition: transform 0.3s ease;
  }

  .slide-enter-from,
  .slide-leave-to {
    transform: translateX(-100%);
  }

  .chapters-list {
    max-height: none;
  }

  .chapter-content {
    max-height: none;
  }

  .page-header {
    flex-wrap: wrap;
    gap: 8px;
    padding-left: 50px;
  }

  .page-header h2 {
    width: 100%;
    font-size: 18px;
  }

  .info-content {
    flex-direction: column;
    align-items: center;
    text-align: center;
  }

  .el-dialog {
    width: 90% !important;
    margin: 0 auto;
  }
}

.chapters-list {
  max-height: 600px;
  overflow-y: auto;
}

.section-group {
  border-bottom: 1px solid #f0f0f0;
}

.section-header {
  padding: 10px 12px;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
  color: #303133;
  transition: background-color 0.2s;
}

.section-header:hover {
  background-color: #f5f7fa;
}

.arrow {
  font-size: 10px;
  transition: transform 0.2s;
  color: #909399;
}

.arrow.expanded {
  transform: rotate(90deg);
}

.section-title {
  flex: 1;
}

.child-count {
  font-size: 12px;
  font-weight: 400;
  color: #909399;
}

.section-children {
  background-color: #fafafa;
}

.chapter-item {
  padding: 8px 12px 8px 32px;
  cursor: pointer;
  font-size: 14px;
  color: #606266;
  transition: background-color 0.2s;
}

.chapter-item:hover {
  background-color: #ecf5ff;
}

.chapter-item.active {
  background-color: #ecf5ff;
  color: #409eff;
  font-weight: 500;
}

.chapter-item.standalone {
  padding-left: 12px;
  font-weight: 600;
  color: #303133;
}

.content-card {
  flex: 1;
  min-width: 0;
}

.content-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.chapter-content {
  line-height: 1.8;
  font-size: 16px;
  max-height: 600px;
  overflow-y: auto;
}

.chapter-content p {
  text-indent: 2em;
  margin: 0 0 8px 0;
}

.chapter-content :deep(.material-highlight) {
  background: #fff3bf;
  padding: 1px 2px;
  border-radius: 2px;
}

.chapter-content :deep(.material-highlight.focused) {
  background: #fef08a;
  box-shadow: 0 0 0 2px #f59e0b;
}

.chapter-nav {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px solid #eee;
}

.nav-info {
  font-size: 14px;
  color: #909399;
}
</style>
