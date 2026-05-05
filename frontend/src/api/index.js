import axios from 'axios'

const api = axios.create({
  baseURL: '/api/v1',
  timeout: 10000
})

// 请求拦截器 - 添加 token
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// 响应拦截器
api.interceptors.response.use(
  (response) => response.data,
  (error) => {
    const message = error.response?.data?.detail || '请求失败'
    return Promise.reject(new Error(message))
  }
)

// 用户相关
export const userApi = {
  register: (data) => api.post('/auth/register', data),
  login: (data) => api.post('/auth/login', data),
  getMe: () => api.get('/user/me')
}

// 书籍相关
export const bookApi = {
  getList: () => api.get('/books'),
  getDetail: (id) => api.get(`/books/${id}`),
  getChapter: (bookId, order) => api.get(`/books/${bookId}/chapters/${order}`),
  upload: (formData) => api.post('/books', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 120000
  }),
  delete: (id) => api.delete(`/books/${id}`),
  update: (id, data) => api.patch(`/books/${id}`, data),
  updateChapters: (bookId, chapters) => api.put(`/books/${bookId}/chapters`, { chapters }),
  getReadingProgress: (bookId) => api.get(`/books/${bookId}/reading-progress`),
  saveReadingProgress: (bookId, data) => api.put(`/books/${bookId}/reading-progress`, data)
}

// 素材相关
export const materialApi = {
  create: (data) => api.post('/materials', data),
  getList: (params) => api.get('/materials', { params }),
  getDetail: (id) => api.get(`/materials/${id}`),
  update: (id, data) => api.patch(`/materials/${id}`, data),
  delete: (id) => api.delete(`/materials/${id}`),
  retag: (id) => api.post(`/materials/${id}/retag`),
  analyze: (id) => api.post(`/materials/${id}/analyze`),
  getLocation: (id) => api.get(`/materials/${id}/location`),
  getAllTags: () => api.get('/tags')
}

// AI 模型管理
export const aiAdminApi = {
  getProviders: () => api.get('/admin/ai/providers'),
  createProvider: (data) => api.post('/admin/ai/providers', data),
  updateProvider: (id, data) => api.patch(`/admin/ai/providers/${id}`, data),
  deleteProvider: (id) => api.delete(`/admin/ai/providers/${id}`),
  getModels: (params) => api.get('/admin/ai/models', { params }),
  createModel: (data) => api.post('/admin/ai/models', data),
  updateModel: (id, data) => api.patch(`/admin/ai/models/${id}`, data),
  deleteModel: (id) => api.delete(`/admin/ai/models/${id}`),
  testModel: (id, data) => api.post(`/admin/ai/models/${id}/test`, data),
  getTaskRoutes: (params) => api.get('/admin/ai/task-routes', { params }),
  updateTaskRoute: (taskType, data) => api.put(`/admin/ai/task-routes/${taskType}`, data),
  getCallLogs: (params) => api.get('/admin/ai/call-logs', { params })
}
