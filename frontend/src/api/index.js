import axios from 'axios'

const api = axios.create({
  baseURL: '/api/v1',
  timeout: 10000
})

// Request interceptor: attach token.
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// Response interceptor
api.interceptors.response.use(
  (response) => response.data,
  (error) => {
    const message = error.response?.data?.detail || '请求失败'
    return Promise.reject(new Error(message))
  }
)

// User APIs
export const userApi = {
  register: (data) => api.post('/auth/register', data),
  login: (data) => api.post('/auth/login', data),
  sendCode: (data) => api.post('/auth/send-code', data),
  getMe: () => api.get('/user/me')
}

// Book APIs
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
  coverPreview: (id, method) => api.post(`/books/${id}/cover/preview`, null, {
    params: { method },
    timeout: 120000
  }),
  setCover: (id, method) => api.post(`/books/${id}/cover`, null, {
    params: { method },
    timeout: 60000
  }),
  updateChapters: (bookId, chapters) => api.put(`/books/${bookId}/chapters`, { chapters }),
  getReadingProgress: (bookId) => api.get(`/books/${bookId}/reading-progress`),
  saveReadingProgress: (bookId, data) => api.put(`/books/${bookId}/reading-progress`, data)
}

// Material APIs
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

// AI model management APIs
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

export const chatApi = {
  getRoles: () => api.get('/chat/roles'),
  createRole: (data) => api.post('/chat/roles', data),
  getRole: (id) => api.get(`/chat/roles/${id}`),
  updateRole: (id, data) => api.patch(`/chat/roles/${id}`, data),
  deleteRole: (id) => api.delete(`/chat/roles/${id}`),
  getConversations: (params) => api.get('/chat/conversations', { params }),
  createConversation: (data) => api.post('/chat/conversations', data),
  getConversation: (id) => api.get(`/chat/conversations/${id}`),
  updateConversation: (id, data) => api.patch(`/chat/conversations/${id}`, data),
  deleteConversation: (id) => api.delete(`/chat/conversations/${id}`),
  deleteFailedConversations: () => api.delete('/chat/conversations/failed'),
  getMessages: (id, params) => api.get(`/chat/conversations/${id}/messages`, { params }),
  sendMessageSync: (id, data) => api.post(`/chat/conversations/${id}/messages/sync`, data, { timeout: 120000 }),
  deleteFromMessage: (id) => api.delete(`/chat/messages/${id}/from-here`),
  getMemories: (roleId) => api.get(`/chat/roles/${roleId}/memories`),
  deleteMemory: (id) => api.delete(`/chat/memories/${id}`),
  streamMessage: async (conversationId, data, onEvent, signal) => {
    const token = localStorage.getItem('token')
    const timeoutController = new AbortController()
    const relayAbort = () => timeoutController.abort()
    let didTimeout = false
    const timeoutId = window.setTimeout(() => {
      didTimeout = true
      timeoutController.abort()
    }, 120000)
    signal?.addEventListener('abort', relayAbort, { once: true })

    try {
      const response = await fetch(`/api/v1/chat/conversations/${conversationId}/messages`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {})
        },
        body: JSON.stringify(data),
        signal: timeoutController.signal
      })

      if (!response.ok) {
        const errorText = await response.text()
        throw new Error(errorText || `Stream request failed (${response.status})`)
      }

      const reader = response.body.getReader()
      const decoder = new TextDecoder('utf-8')
      let buffer = ''
      while (true) {
        const { value, done } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const events = buffer.replace(/\r\n/g, '\n').split('\n\n')
        buffer = events.pop() || ''
        for (const raw of events) {
          const payload = raw
            .split('\n')
            .filter(item => item.startsWith('data:'))
            .map(item => item.slice(5).trim())
            .join('\n')
          if (!payload) continue
          if (payload === '[DONE]') return
          await onEvent(JSON.parse(payload))
        }
      }
    } catch (error) {
      if (didTimeout) {
        throw new Error('AI 回复超时：后端请求已发出，但 SSE 连接长时间未结束。请查看后端日志中的具体阶段错误。')
      }
      throw error
    } finally {
      window.clearTimeout(timeoutId)
      signal?.removeEventListener('abort', relayAbort)
    }
  }
}

