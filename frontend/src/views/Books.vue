<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { bookApi } from '../api'

const router = useRouter()
const loading = ref(false)
const books = ref([])
const uploadDialogVisible = ref(false)
const selectedFile = ref(null)

const uploadForm = ref({
  title: '',
  author: ''
})

const editDialogVisible = ref(false)
const editForm = ref({ id: '', title: '', author: '' })

// 获取书籍列表
const fetchBooks = async () => {
  loading.value = true
  try {
    const res = await bookApi.getList()
    books.value = res.items || []
  } catch (error) {
    ElMessage.error(error.message)
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  fetchBooks()
})

// 文件选择
const handleFileChange = (file) => {
  selectedFile.value = file.raw
}

// 上传
const handleUpload = async () => {
  if (!selectedFile.value) {
    ElMessage.warning('请先选择文件')
    return
  }

  const formData = new FormData()
  formData.append('file', selectedFile.value)
  if (uploadForm.value.title) {
    formData.append('title', uploadForm.value.title)
  }
  if (uploadForm.value.author) {
    formData.append('author', uploadForm.value.author)
  }

  loading.value = true
  try {
    const res = await bookApi.upload(formData)
    ElMessage.success(`上传成功，共 ${res.chapters_count} 章`)
    uploadDialogVisible.value = false
    uploadForm.value = { title: '', author: '' }
    selectedFile.value = null
    // 跳转到章节编辑器
    router.push(`/books/${res.id}/edit`)
  } catch (error) {
    ElMessage.error(error.message)
  } finally {
    loading.value = false
  }
}

// 删除
const handleDelete = (book) => {
  ElMessageBox.confirm(`确定删除《${book.title}》？`, '提示', {
    type: 'warning'
  }).then(async () => {
    try {
      await bookApi.delete(book.id)
      ElMessage.success('删除成功')
      fetchBooks()
    } catch (error) {
      ElMessage.error(error.message)
    }
  }).catch(() => {})
}

// 查看详情
const handleViewDetail = (book) => {
  router.push(`/books/${book.id}`)
}

// 编辑
const handleEdit = (book) => {
  editForm.value = { id: book.id, title: book.title, author: book.author || '' }
  editDialogVisible.value = true
}

const handleEditSave = async () => {
  try {
    await bookApi.update(editForm.value.id, {
      title: editForm.value.title,
      author: editForm.value.author
    })
    ElMessage.success('修改成功')
    editDialogVisible.value = false
    fetchBooks()
  } catch (error) {
    ElMessage.error(error.message)
  }
}
</script>

<template>
  <div class="books">
    <div class="page-header">
      <div class="header-left">
        <el-button @click="router.push('/')" icon="HomeFilled">首页</el-button>
        <h2>书籍管理</h2>
      </div>
      <el-button type="primary" @click="uploadDialogVisible = true">
        <el-icon><Upload /></el-icon>
        上传书籍
      </el-button>
    </div>

    <!-- 书籍列表 -->
    <el-card v-loading="loading">
      <el-empty v-if="books.length === 0" description="暂无书籍，快去上传吧">
        <el-button type="primary" @click="uploadDialogVisible = true">上传书籍</el-button>
      </el-empty>

      <div v-else class="books-grid">
        <el-card v-for="book in books" :key="book.id" shadow="hover" class="book-card">
          <div class="book-cover">
            <img :src="book.cover_url || '/书封面.webp'" alt="封面" class="cover-img"
                 @error="(e) => { e.target.src = '/书封面.webp' }" />
          </div>
          <div class="book-info">
            <h3 class="book-title">{{ book.title }}</h3>
            <p class="book-author">{{ book.author || '未知作者' }}</p>
            <p class="book-meta">{{ book.chapters_count }} 章</p>
          </div>
          <div class="book-actions">
            <el-button type="primary" link @click="handleViewDetail(book)">查看详情</el-button>
            <el-button type="warning" link @click="handleEdit(book)">编辑</el-button>
            <el-button type="danger" link @click="handleDelete(book)">删除</el-button>
          </div>
        </el-card>
      </div>
    </el-card>

    <!-- 上传弹窗 -->
    <el-dialog v-model="uploadDialogVisible" title="上传书籍" width="500px">
      <el-form :model="uploadForm" label-width="80px">
        <el-form-item label="书名">
          <el-input v-model="uploadForm.title" placeholder="不填则从文件名提取" />
        </el-form-item>
        <el-form-item label="作者">
          <el-input v-model="uploadForm.author" placeholder="选填" />
        </el-form-item>
        <el-form-item label="文件">
          <el-upload
            drag
            :auto-upload="false"
            :limit="1"
            :on-change="handleFileChange"
            accept=".txt"
          >
            <el-icon :size="48"><Upload /></el-icon>
            <div class="el-upload__text">拖拽文件到此处，或 <em>点击选择</em></div>
            <template #tip>
              <div class="el-upload__tip">支持 txt 格式，最大 50MB</div>
            </template>
          </el-upload>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="uploadDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="loading" @click="handleUpload">上传</el-button>
      </template>
    </el-dialog>

    <!-- 编辑弹窗 -->
    <el-dialog v-model="editDialogVisible" title="编辑书籍信息" width="400px">
      <el-form :model="editForm" label-width="60px">
        <el-form-item label="书名">
          <el-input v-model="editForm.title" />
        </el-form-item>
        <el-form-item label="作者">
          <el-input v-model="editForm.author" placeholder="填写作者名" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleEditSave">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.page-header h2 {
  margin: 0;
}

.books-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
  gap: 20px;
}

.book-card {
  cursor: pointer;
  transition: all 0.3s;
}

.book-card:hover {
  transform: translateY(-5px);
}

.book-cover {
  text-align: center;
  background-color: #f5f7fa;
  border-radius: 4px;
  margin-bottom: 12px;
  overflow: hidden;
}

.cover-img {
  width: 100%;
  height: 180px;
  object-fit: cover;
  display: block;
}

.book-info {
  text-align: center;
}

.book-title {
  margin: 0 0 8px;
  font-size: 16px;
}

.book-author {
  color: #909399;
  margin: 0 0 4px;
  font-size: 14px;
}

.book-meta {
  color: #409eff;
  margin: 0;
  font-size: 12px;
}

.book-actions {
  display: flex;
  justify-content: center;
  gap: 12px;
  margin-top: 12px;
}
</style>
