<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { materialApi, bookApi } from '../api'

const router = useRouter()
const loading = ref(false)
const materials = ref([])
const books = ref([])
const allTags = ref([])
const chaptersMap = ref({})

// 筛选条件
const filter = ref({
  keyword: '',
  source_type: '',
  book_id: '',
  tag: '',
  material_status: ''
})

// 创建素材
const createDialogVisible = ref(false)
const createForm = ref({
  content: '',
  source_type: '自己感悟',
  book_id: '',
  chapter_order: null,
  note: '',
  user_mood: ''
})
const creating = ref(false)
const createChapters = ref([])

// 编辑素材
const editDialogVisible = ref(false)
const editForm = ref({
  id: '',
  content: '',
  note: '',
  tags: [],
  status: ''
})
const editing = ref(false)

const sourceTypes = ['book摘录', '微信读书', '自己感悟']
const moodOptions = ['共鸣', '震动', '难过', '讽刺', '愤怒', '困惑', '温暖', '荒凉', '喜欢', '想反驳']

// 加载数据
onMounted(async () => {
  await Promise.all([fetchMaterials(), fetchBooks(), fetchTags()])
})

const fetchMaterials = async () => {
  loading.value = true
  try {
    const params = {}
    if (filter.value.keyword) params.keyword = filter.value.keyword
    if (filter.value.source_type) params.source_type = filter.value.source_type
    if (filter.value.book_id) params.book_id = filter.value.book_id
    if (filter.value.tag) params.tag = filter.value.tag
    if (filter.value.material_status) params.material_status = filter.value.material_status
    const res = await materialApi.getList(params)
    materials.value = res.items || []
  } catch (error) {
    ElMessage.error(error.message)
  } finally {
    loading.value = false
  }
}

const fetchBooks = async () => {
  try {
    const res = await bookApi.getList()
    books.value = res.items || []
  } catch {}
}

const fetchTags = async () => {
  try {
    const res = await materialApi.getAllTags()
    allTags.value = res.tags || []
  } catch {}
}

// 加载某本书的章节
const loadChapters = async (bookId, target) => {
  if (!bookId) {
    target.value = []
    return
  }
  try {
    const res = await bookApi.getDetail(bookId)
    target.value = (res.chapters || []).map(ch => ({
      order: ch.chapter_order,
      title: ch.title
    }))
  } catch {
    target.value = []
  }
}

// 筛选
const handleFilter = () => {
  fetchMaterials()
}

const handleResetFilter = () => {
  filter.value = { keyword: '', source_type: '', book_id: '', tag: '', material_status: '' }
  fetchMaterials()
}

const handleTagClick = (tag) => {
  filter.value.tag = filter.value.tag === tag ? '' : tag
  fetchMaterials()
}

// 创建素材
const handleOpenCreate = () => {
  createForm.value = {
    content: '',
    source_type: '自己感悟',
    book_id: '',
    chapter_order: null,
    note: '',
    user_mood: ''
  }
  createChapters.value = []
  createDialogVisible.value = true
}

const handleCreateBookChange = async (val) => {
  createForm.value.chapter_order = null
  await loadChapters(val, createChapters)
}

const handleCreate = async () => {
  if (!createForm.value.content.trim()) {
    ElMessage.warning('请输入素材内容')
    return
  }
  creating.value = true
  try {
    await materialApi.create({
      ...createForm.value,
      status: 'completed',
      entry_mode: 'materials_page'
    })
    ElMessage.success('素材已保存，AI 正在理解这段内容')
    createDialogVisible.value = false
    fetchMaterials()
    fetchTags()
  } catch (error) {
    ElMessage.error(error.message)
  } finally {
    creating.value = false
  }
}

// 编辑素材
const handleEdit = (mat) => {
  editForm.value = {
    id: mat.id,
    content: mat.content,
    note: mat.note || '',
    tags: mat.tags || [],
    status: mat.status
  }
  editDialogVisible.value = true
}

const handleEditSave = async () => {
  if (!editForm.value.content.trim()) {
    ElMessage.warning('内容不能为空')
    return
  }
  editing.value = true
  try {
    await materialApi.update(editForm.value.id, {
      content: editForm.value.content,
      note: editForm.value.note,
      tags: editForm.value.tags
    })
    ElMessage.success('更新成功')
    editDialogVisible.value = false
    fetchMaterials()
    fetchTags()
  } catch (error) {
    ElMessage.error(error.message)
  } finally {
    editing.value = false
  }
}

// 完成草稿
const handleCompleteDraft = async (mat) => {
  try {
    await materialApi.update(mat.id, { status: 'completed' })
    ElMessage.success('草稿已完成')
    fetchMaterials()
    fetchTags()
  } catch (error) {
    ElMessage.error(error.message)
  }
}

// 重新生成标签
const handleRetag = async (mat) => {
  try {
    await materialApi.retag(mat.id)
    ElMessage.success('标签已重新生成')
    fetchMaterials()
    fetchTags()
  } catch (error) {
    ElMessage.error(error.message)
  }
}

const handleAnalyze = async (mat) => {
  try {
    await materialApi.analyze(mat.id)
    ElMessage.success('AI 分析已开始，请稍后刷新查看')
    fetchMaterials()
  } catch (error) {
    ElMessage.error(error.message)
  }
}

// 删除素材
const handleDelete = (mat) => {
  ElMessageBox.confirm('确定删除这条素材？', '提示', {
    type: 'warning'
  }).then(async () => {
    try {
      await materialApi.delete(mat.id)
      ElMessage.success('已删除')
      fetchMaterials()
      fetchTags()
    } catch (error) {
      ElMessage.error(error.message)
    }
  }).catch(() => {})
}

// 定位到书中
const handleLocate = (mat) => {
  if (mat.book_id && mat.chapter_order) {
    router.push(`/books/${mat.book_id}?chapter=${mat.chapter_order}&material=${mat.id}`)
  }
}

// 移除编辑表单中的标签
const removeEditTag = (tag) => {
  editForm.value.tags = editForm.value.tags.filter(t => t !== tag)
}

// 格式化日期
const formatDate = (dateStr) => {
  if (!dateStr) return ''
  const d = new Date(dateStr)
  return d.toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}
</script>

<template>
  <div class="materials-page">
    <!-- 顶部 -->
    <div class="page-header">
      <div class="header-left">
        <el-button @click="router.push('/')" icon="ArrowLeft">返回</el-button>
        <h2>素材库</h2>
      </div>
      <el-button type="primary" @click="handleOpenCreate">
        <el-icon><Plus /></el-icon>
        记录素材
      </el-button>
    </div>

    <!-- 筛选栏 -->
    <el-card class="filter-card">
      <div class="filter-row">
        <el-input
          v-model="filter.keyword"
          placeholder="搜索内容..."
          clearable
          style="width: 180px"
          @keyup.enter="handleFilter"
        />
        <el-select v-model="filter.material_status" placeholder="状态" clearable style="width: 110px">
          <el-option label="已完成" value="completed" />
          <el-option label="草稿" value="draft" />
        </el-select>
        <el-select v-model="filter.source_type" placeholder="来源类型" clearable style="width: 130px">
          <el-option v-for="t in sourceTypes" :key="t" :label="t" :value="t" />
        </el-select>
        <el-select v-model="filter.book_id" placeholder="关联书籍" clearable style="width: 180px">
          <el-option v-for="b in books" :key="b.id" :label="b.title" :value="b.id" />
        </el-select>
        <el-button type="primary" @click="handleFilter">筛选</el-button>
        <el-button @click="handleResetFilter">重置</el-button>
      </div>

      <!-- 标签云 -->
      <div v-if="allTags.length > 0" class="tag-cloud">
        <span class="tag-label">标签：</span>
        <el-tag
          v-for="tag in allTags"
          :key="tag"
          :type="filter.tag === tag ? '' : 'info'"
          :effect="filter.tag === tag ? 'dark' : 'plain'"
          class="tag-item"
          @click="handleTagClick(tag)"
        >
          {{ tag }}
        </el-tag>
      </div>
    </el-card>

    <!-- 素材列表 -->
    <div class="materials-list" v-loading="loading">
      <el-empty v-if="materials.length === 0" description="暂无素材" />
      <el-card v-for="mat in materials" :key="mat.id" class="material-card">
        <div class="material-header">
          <el-tag v-if="mat.status === 'draft'" size="small" type="warning" effect="dark">草稿</el-tag>
          <el-tag size="small" :type="mat.source_type === 'book摘录' ? 'primary' : mat.source_type === '微信读书' ? 'success' : 'warning'">
            {{ mat.source_type }}
          </el-tag>
          <span v-if="mat.book_title" class="source-info">
            《{{ mat.book_title }}》
            <span v-if="mat.chapter_title">· {{ mat.chapter_title }}</span>
          </span>
          <span class="material-date">{{ formatDate(mat.updated_at || mat.created_at) }}</span>
        </div>

        <div class="material-content">
          {{ mat.content }}
        </div>

        <div v-if="mat.selected_text" class="material-selected">
          <strong>原文：</strong>{{ mat.selected_text }}
        </div>

        <div v-if="mat.note" class="material-note">
          <strong>备注：</strong>{{ mat.note }}
        </div>

        <div v-if="mat.user_mood" class="material-note">
          <strong>保存时心情：</strong>{{ mat.user_mood }}
        </div>

        <div v-if="mat.ai_analysis_status && mat.ai_analysis_status !== 'not_started'" class="ai-box">
          <div class="ai-box-header">
            <strong>AI 素材理解</strong>
            <el-tag
              size="small"
              :type="mat.ai_analysis_status === 'completed' ? 'success' : mat.ai_analysis_status === 'failed' ? 'danger' : 'warning'"
            >
              {{ mat.ai_analysis_status === 'completed' ? '已完成' : mat.ai_analysis_status === 'failed' ? '失败' : '分析中' }}
            </el-tag>
            <span v-if="mat.ai_analysis_model" class="ai-model">
              {{ mat.ai_analysis_provider }} / {{ mat.ai_analysis_model }}
            </span>
          </div>

          <p v-if="mat.ai_context_summary"><strong>上下文：</strong>{{ mat.ai_context_summary }}</p>
          <p v-if="mat.ai_interpretation"><strong>解读：</strong>{{ mat.ai_interpretation }}</p>
          <p v-if="mat.ai_theme_analysis"><strong>主题：</strong>{{ mat.ai_theme_analysis }}</p>
          <p v-if="mat.ai_analysis_error" class="ai-error"><strong>错误：</strong>{{ mat.ai_analysis_error }}</p>

          <div v-if="mat.ai_possible_feelings?.length" class="ai-list">
            <strong>可能打动你的地方：</strong>
            <el-tag v-for="item in mat.ai_possible_feelings" :key="item" size="small" effect="plain">{{ item }}</el-tag>
          </div>

          <div v-if="mat.ai_insight_candidates?.length" class="ai-insights">
            <strong>感悟候选：</strong>
            <div v-for="item in mat.ai_insight_candidates" :key="item" class="insight-item">{{ item }}</div>
          </div>

          <div v-if="mat.ai_writing_topics?.length" class="ai-list">
            <strong>写作用途：</strong>
            <el-tag v-for="item in mat.ai_writing_topics" :key="item" size="small" type="success" effect="plain">{{ item }}</el-tag>
          </div>
        </div>

        <div v-if="mat.tags && mat.tags.length > 0" class="material-tags">
          <el-tag
            v-for="tag in mat.tags"
            :key="tag"
            size="small"
            type="info"
            effect="plain"
            class="tag-item"
            @click="handleTagClick(tag)"
          >
            {{ tag }}
          </el-tag>
        </div>

        <div class="material-actions">
          <el-button v-if="mat.status === 'draft'" type="success" link @click="handleCompleteDraft(mat)">完成草稿</el-button>
          <el-button type="primary" link @click="handleEdit(mat)">编辑</el-button>
          <el-button v-if="mat.book_id && mat.chapter_order" type="primary" link @click="handleLocate(mat)">查看原文位置</el-button>
          <el-button v-if="mat.status !== 'draft'" type="warning" link @click="handleRetag(mat)">重新生成标签</el-button>
          <el-button v-if="mat.status !== 'draft'" type="success" link @click="handleAnalyze(mat)">AI重新理解</el-button>
          <el-button type="danger" link @click="handleDelete(mat)">删除</el-button>
        </div>
      </el-card>
    </div>

    <!-- 创建弹窗 -->
    <el-dialog v-model="createDialogVisible" title="记录素材" width="600px">
      <el-form :model="createForm" label-width="80px">
        <el-form-item label="内容">
          <el-input
            v-model="createForm.content"
            type="textarea"
            :autosize="{ minRows: 4, maxRows: 8 }"
            placeholder="粘贴摘录的金句、段评或你的感悟..."
          />
        </el-form-item>
        <el-form-item label="来源">
          <el-radio-group v-model="createForm.source_type">
            <el-radio-button v-for="t in sourceTypes" :key="t" :label="t">{{ t }}</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="关联书籍">
          <el-select v-model="createForm.book_id" placeholder="选择书籍" clearable style="width: 100%" @change="handleCreateBookChange">
            <el-option v-for="b in books" :key="b.id" :label="b.title" :value="b.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="关联章节" v-if="createForm.book_id && createChapters.length > 0">
          <el-select v-model="createForm.chapter_order" placeholder="选择章节" clearable style="width: 100%" filterable>
            <el-option v-for="ch in createChapters" :key="ch.order" :label="`${ch.order}. ${ch.title}`" :value="ch.order" />
          </el-select>
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="createForm.note" placeholder="可选，记录你的想法" />
        </el-form-item>
        <el-form-item label="心情">
          <el-select v-model="createForm.user_mood" placeholder="可选：保存时的感觉" clearable style="width: 100%">
            <el-option v-for="mood in moodOptions" :key="mood" :label="mood" :value="mood" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="creating" @click="handleCreate">保存（AI自动生成标签）</el-button>
      </template>
    </el-dialog>

    <!-- 编辑弹窗 -->
    <el-dialog v-model="editDialogVisible" title="编辑素材" width="600px">
      <el-form :model="editForm" label-width="80px">
        <el-form-item label="内容">
          <el-input
            v-model="editForm.content"
            type="textarea"
            :autosize="{ minRows: 4, maxRows: 8 }"
          />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="editForm.note" placeholder="可选" />
        </el-form-item>
        <el-form-item label="标签">
          <div class="edit-tags">
            <el-tag
              v-for="tag in editForm.tags"
              :key="tag"
              closable
              @close="removeEditTag(tag)"
            >
              {{ tag }}
            </el-tag>
            <span v-if="editForm.tags.length === 0" style="color: #909399; font-size: 13px">暂无标签，保存后可点击"重新生成标签"</span>
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="editing" @click="handleEditSave">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.materials-page {
  max-width: 900px;
  margin: 0 auto;
  padding: 20px;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 16px;
}

.header-left h2 {
  margin: 0;
}

.filter-card {
  margin-bottom: 20px;
}

.filter-row {
  display: flex;
  gap: 10px;
  align-items: center;
  flex-wrap: wrap;
}

.tag-cloud {
  margin-top: 12px;
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.tag-label {
  font-size: 13px;
  color: #606266;
}

.tag-item {
  cursor: pointer;
  transition: all 0.2s;
}

.tag-item:hover {
  opacity: 0.8;
}

.materials-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.material-card {
  transition: box-shadow 0.2s;
}

.material-card:hover {
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
}

.material-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
}

.source-info {
  font-size: 13px;
  color: #606266;
  flex: 1;
}

.material-date {
  font-size: 12px;
  color: #909399;
}

.material-content {
  font-size: 15px;
  line-height: 1.8;
  color: #303133;
  margin-bottom: 8px;
  white-space: pre-wrap;
}

.material-selected {
  font-size: 13px;
  color: #909399;
  margin-bottom: 8px;
  padding: 8px 12px;
  background: #fdf6ec;
  border-radius: 4px;
  border-left: 3px solid #e6a23c;
}

.material-note {
  font-size: 13px;
  color: #909399;
  margin-bottom: 8px;
  padding: 8px 12px;
  background: #fafafa;
  border-radius: 4px;
}

.material-tags {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  margin-bottom: 8px;
}

.ai-box {
  background: #f6fbf7;
  border: 1px solid #d9f0df;
  border-left: 3px solid #67c23a;
  border-radius: 6px;
  padding: 10px 12px;
  margin-bottom: 10px;
  color: #303133;
}

.ai-box p {
  margin: 6px 0;
  font-size: 13px;
  line-height: 1.7;
}

.ai-box-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}

.ai-model {
  font-size: 12px;
  color: #909399;
}

.ai-error {
  color: #c45656;
}

.ai-list {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  align-items: center;
  margin-top: 8px;
  font-size: 13px;
}

.ai-insights {
  margin-top: 8px;
  font-size: 13px;
}

.insight-item {
  background: #fff;
  border-radius: 4px;
  padding: 6px 8px;
  margin-top: 6px;
  line-height: 1.6;
}

.material-actions {
  display: flex;
  gap: 12px;
  border-top: 1px solid #f0f0f0;
  padding-top: 8px;
  flex-wrap: wrap;
}

.edit-tags {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  align-items: center;
}
</style>
