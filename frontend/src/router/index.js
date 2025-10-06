import { createRouter, createWebHistory } from 'vue-router'
import ProjectBoardView from '../views/ProjectBoardView.vue'
import TestView from '../views/TestView.vue'

export const routes = [
  {
    path: '/',
    name: 'projects',
    component: ProjectBoardView,
    alias: ['/projects'],
    meta: {
      title: '项目面板'
    }
  },
  {
    path: '/test',
    name: 'test',
    component: TestView,
    meta: {
      title: '测试界面'
    }
  },
  {
    path: '/:pathMatch(.*)*',
    redirect: '/'
  }
]

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes
})

export default router
