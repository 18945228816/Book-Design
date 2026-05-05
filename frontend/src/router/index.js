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
