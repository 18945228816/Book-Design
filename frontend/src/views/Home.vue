<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { userApi, bookApi, materialApi } from '../api'
import QuickEntryPanel from '../components/QuickEntryPanel.vue'

const router = useRouter()
const user = ref(null)
const bookCount = ref(0)
const materialCount = ref(0)
const recentDrafts = ref([])
const recentMaterials = ref([])

const loadData = async () => {
  try {
    const [booksRes, materialsRes, draftsRes] = await Promise.all([
      bookApi.getList(),
      materialApi.getList({ material_status: 'completed', limit: 3 }),
      materialApi.getList({ material_status: 'draft', limit: 5 })
    ])
    bookCount.value = booksRes.total || 0
    materialCount.value = materialsRes.total || 0
    recentMaterials.value = materialsRes.items || []
    recentDrafts.value = draftsRes.items || []
  } catch {}
}

onMounted(async () => {
  const token = localStorage.getItem('token')
  if (!token) {
    router.push('/login')
    return
  }

  try {
    user.value = await userApi.getMe()
    await loadData()
  } catch (error) {
    ElMessage.error('请重新登录')
    localStorage.removeItem('token')
    router.push('/login')
  }
})

const handleLogout = () => {
  localStorage.removeItem('token')
  localStorage.removeItem('user')
  router.push('/login')
}

const goTo = (path) => {
  router.push(path)
}

const handleDraftAction = async (draft, action) => {
  if (action === 'complete') {
    try {
      await materialApi.update(draft.id, { status: 'completed' })
      ElMessage.success('已完成')
      await loadData()
    } catch (error) {
      ElMessage.error(error.message)
    }
  } else if (action === 'edit') {
    router.push('/materials')
  } else if (action === 'delete') {
    try {
      await ElMessageBox.confirm('确定删除这条草稿？', '提示', { type: 'warning' })
      await materialApi.delete(draft.id)
      ElMessage.success('已删除')
      await loadData()
    } catch {}
  }
}

const sourceColor = (type) => {
  if (type === 'book摘录') return '#409eff'
  if (type === '微信读书') return '#67c23a'
  return '#e6a23c'
}

const truncate = (text, len) => {
  if (!text) return ''
  return text.length > len ? text.slice(0, len) + '...' : text
}

const formatDate = (dateStr) => {
  if (!dateStr) return ''
  const d = new Date(dateStr)
  const now = new Date()
  const diff = now - d
  if (diff < 60000) return '刚刚'
  if (diff < 3600000) return Math.floor(diff / 60000) + '分钟前'
  if (diff < 86400000) return Math.floor(diff / 3600000) + '小时前'
  return d.toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit' })
}
</script>

<template>
  <div class="home-page" v-if="user">
    <!-- 顶部导航 -->
    <header class="top-bar">
      <div class="logo">
        <el-icon :size="22"><Reading /></el-icon>
        <span>智能助手平台</span>
      </div>
      <nav class="nav-links">
        <el-button link @click="goTo('/')">首页</el-button>
        <el-button link @click="goTo('/books')">书籍</el-button>
        <el-button link @click="goTo('/materials')">素材</el-button>
        <el-button link type="primary" @click="goTo('/chat')">AI 对话</el-button>
        <el-button link @click="goTo('/chat/roles')">角色管理</el-button>
      </nav>
      <div class="user-info">
        <span class="username">{{ user.username }}</span>
        <el-button text @click="handleLogout">退出</el-button>
      </div>
    </header>

    <!-- Hero 区域：左侧文案 + 右侧快速录入 -->
    <section class="hero">
      <div class="hero-inner">
        <div class="hero-left">
          <h1>记录你的阅读时光</h1>
          <p class="hero-desc">摘录金句 · 收藏感悟 · 积累素材</p>
          <div class="hero-actions">
            <el-button type="primary" size="large" @click="goTo('/chat')">
              <el-icon><ChatDotSquare /></el-icon>
              AI 对话
            </el-button>
            <el-button type="success" size="large" @click="goTo('/books')">
              <el-icon><Reading /></el-icon>
              我的书籍
            </el-button>
            <el-button type="info" size="large" @click="goTo('/materials')">
              <el-icon><Collection /></el-icon>
              素材库
            </el-button>
            <el-button type="warning" size="large" @click="goTo('/settings/ai-models')">
              <el-icon><Setting /></el-icon>
              AI 模型管理
            </el-button>
          </div>
        </div>
        <div class="hero-right">
          <QuickEntryPanel @saved="loadData" />
        </div>
      </div>
    </section>

    <!-- 数据概览 -->
    <section class="stats-section">
      <div class="stat-card" @click="goTo('/books')">
        <div class="stat-icon" style="background: #ecf5ff">
          <el-icon :size="28" color="#409eff"><Reading /></el-icon>
        </div>
        <div class="stat-info">
          <div class="stat-num">{{ bookCount }}</div>
          <div class="stat-label">已收录书籍</div>
        </div>
      </div>
      <div class="stat-card" @click="goTo('/materials')">
        <div class="stat-icon" style="background: #f0f9eb">
          <el-icon :size="28" color="#67c23a"><Collection /></el-icon>
        </div>
        <div class="stat-info">
          <div class="stat-num">{{ materialCount }}</div>
          <div class="stat-label">素材积累</div>
        </div>
      </div>
      <div class="stat-card" @click="goTo('/materials')">
        <div class="stat-icon" style="background: #fdf6ec">
          <el-icon :size="28" color="#e6a23c"><ChatDotSquare /></el-icon>
        </div>
        <div class="stat-info">
          <div class="stat-num">{{ recentDrafts.length }}</div>
          <div class="stat-label">待整理草稿</div>
        </div>
      </div>
    </section>

    <!-- 内容区：最近草稿 + 最近素材 -->
    <section class="content-section">
      <!-- 最近草稿 -->
      <div class="content-block">
        <div class="section-header">
          <h3>
            <el-icon><EditPen /></el-icon>
            待整理草稿
          </h3>
          <el-button text type="primary" @click="goTo('/materials')">查看全部</el-button>
        </div>
        <div v-if="recentDrafts.length > 0" class="drafts-list">
          <div v-for="draft in recentDrafts" :key="draft.id" class="draft-item">
            <div class="draft-main">
              <div class="draft-source">
                <span class="source-dot" :style="{ background: sourceColor(draft.source_type) }"></span>
                <span>{{ draft.source_type }}</span>
                <span v-if="draft.book_title" class="draft-book">《{{ draft.book_title }}》</span>
                <span v-if="draft.chapter_title" class="draft-chapter">{{ draft.chapter_title }}</span>
              </div>
              <div class="draft-content">{{ truncate(draft.content, 80) }}</div>
              <div class="draft-time">{{ formatDate(draft.updated_at || draft.created_at) }}</div>
            </div>
            <div class="draft-actions">
              <el-button type="success" size="small" @click="handleDraftAction(draft, 'complete')">直接完成</el-button>
              <el-button size="small" @click="handleDraftAction(draft, 'edit')">去完善</el-button>
              <el-button type="danger" size="small" text @click="handleDraftAction(draft, 'delete')">删除</el-button>
            </div>
          </div>
        </div>
        <el-empty v-else description="暂无草稿" :image-size="60" />
      </div>

      <!-- 最近素材 -->
      <div class="content-block">
        <div class="section-header">
          <h3>
            <el-icon><Collection /></el-icon>
            最近素材
          </h3>
          <el-button text type="primary" @click="goTo('/materials')">查看全部</el-button>
        </div>
        <div v-if="recentMaterials.length > 0" class="materials-list">
          <div v-for="mat in recentMaterials" :key="mat.id" class="material-item" @click="goTo('/materials')">
            <div class="material-source">
              <span class="source-dot" :style="{ background: sourceColor(mat.source_type) }"></span>
              <span>{{ mat.source_type }}</span>
              <span v-if="mat.book_title" class="material-book">《{{ mat.book_title }}》</span>
            </div>
            <div class="material-content">{{ truncate(mat.content, 60) }}</div>
            <div v-if="mat.tags && mat.tags.length > 0" class="material-tags">
              <el-tag v-for="tag in mat.tags.slice(0, 3)" :key="tag" size="small" type="info" effect="plain">{{ tag }}</el-tag>
            </div>
          </div>
        </div>
        <el-empty v-else description="暂无素材" :image-size="60" />
      </div>
    </section>
  </div>
</template>

<style scoped>
.home-page {
  min-height: 100vh;
  background: #f5f7fa;
}

/* 顶部导航 */
.top-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 14px 40px;
  background: #fff;
  border-bottom: 1px solid #ebeef5;
}

.logo {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 17px;
  font-weight: 600;
  color: #303133;
}

.nav-links {
  display: flex;
  gap: 4px;
}

.user-info {
  display: flex;
  align-items: center;
  gap: 12px;
}

.username {
  color: #606266;
  font-size: 14px;
}

/* Hero 区域 */
.hero {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  padding: 40px;
}

.hero-inner {
  max-width: 1200px;
  margin: 0 auto;
  display: flex;
  gap: 40px;
  align-items: flex-start;
}

.hero-left {
  flex: 1;
  color: #fff;
  padding-top: 20px;
}

.hero-left h1 {
  font-size: 30px;
  margin: 0 0 10px;
  font-weight: 600;
}

.hero-desc {
  font-size: 15px;
  opacity: 0.85;
  margin: 0 0 28px;
  letter-spacing: 3px;
}

.hero-actions {
  display: flex;
  gap: 12px;
}

.hero-right {
  width: 420px;
  flex-shrink: 0;
}

/* 数据概览 */
.stats-section {
  display: flex;
  gap: 20px;
  padding: 0 40px;
  margin-top: -20px;
  position: relative;
  z-index: 1;
  max-width: 1200px;
  margin-left: auto;
  margin-right: auto;
}

.stat-card {
  flex: 1;
  background: #fff;
  border-radius: 10px;
  padding: 20px;
  display: flex;
  align-items: center;
  gap: 14px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.05);
  cursor: pointer;
  transition: transform 0.2s, box-shadow 0.2s;
}

.stat-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 14px rgba(0, 0, 0, 0.08);
}

.stat-icon {
  width: 50px;
  height: 50px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.stat-num {
  font-size: 26px;
  font-weight: 700;
  color: #303133;
  line-height: 1;
}

.stat-label {
  font-size: 13px;
  color: #909399;
  margin-top: 3px;
}

/* 内容区 */
.content-section {
  display: flex;
  gap: 20px;
  padding: 24px 40px 40px;
  max-width: 1200px;
  margin: 0 auto;
}

.content-block {
  flex: 1;
  background: #fff;
  border-radius: 10px;
  padding: 20px;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.04);
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.section-header h3 {
  margin: 0;
  font-size: 16px;
  color: #303133;
  display: flex;
  align-items: center;
  gap: 6px;
}

/* 草稿列表 */
.drafts-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.draft-item {
  padding: 12px;
  border: 1px solid #f0f0f0;
  border-radius: 8px;
  transition: border-color 0.2s;
}

.draft-item:hover {
  border-color: #d9ecff;
}

.draft-main {
  margin-bottom: 8px;
}

.draft-source {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: #909399;
  margin-bottom: 6px;
}

.source-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex-shrink: 0;
}

.draft-book {
  color: #606266;
}

.draft-chapter {
  color: #909399;
}

.draft-content {
  font-size: 14px;
  color: #303133;
  line-height: 1.5;
}

.draft-time {
  font-size: 12px;
  color: #c0c4cc;
  margin-top: 4px;
}

.draft-actions {
  display: flex;
  gap: 8px;
  border-top: 1px solid #f5f5f5;
  padding-top: 8px;
}

/* 素材列表 */
.materials-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.material-item {
  padding: 10px;
  border-radius: 6px;
  cursor: pointer;
  transition: background 0.2s;
}

.material-item:hover {
  background: #fafafa;
}

.material-source {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: #909399;
  margin-bottom: 4px;
}

.material-book {
  color: #606266;
}

.material-content {
  font-size: 14px;
  color: #303133;
  line-height: 1.5;
}

.material-tags {
  margin-top: 6px;
  display: flex;
  gap: 4px;
}
</style>
