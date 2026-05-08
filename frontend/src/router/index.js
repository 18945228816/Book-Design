import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  {
    path: '/',
    name: 'Home',
    component: () => import('../views/Home.vue')
  },
  {
    path: '/login',
    name: 'Login',
    component: () => import('../views/Login.vue')
  },
  {
    path: '/books',
    name: 'Books',
    component: () => import('../views/Books.vue')
  },
  {
    path: '/books/:id/edit',
    name: 'ChapterEditor',
    component: () => import('../views/ChapterEditor.vue')
  },
  {
    path: '/books/:id',
    name: 'BookDetail',
    component: () => import('../views/BookDetail.vue')
  },
  {
    path: '/materials',
    name: 'Materials',
    component: () => import('../views/Materials.vue')
  },
  {
    path: '/chat',
    name: 'Chat',
    component: () => import('../views/Chat.vue')
  },
  {
    path: '/chat/roles',
    name: 'ChatRoles',
    component: () => import('../views/ChatRoles.vue')
  },
  {
    path: '/chat/:conversationId',
    name: 'ChatConversation',
    component: () => import('../views/Chat.vue')
  },
  {
    path: '/settings/ai-models',
    name: 'AIModelSettings',
    component: () => import('../views/AIModelSettings.vue')
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

export default router
