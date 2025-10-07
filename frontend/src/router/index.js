import { createRouter, createWebHistory } from 'vue-router'
import ProjectBoardView from '../views/ProjectBoardView.vue'
import ProjectDataView from '../views/ProjectDataView.vue'
import TestView from '../views/TestView.vue'
import SettingsView from '../views/SettingsView.vue'

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
    path: '/datasets',
    name: 'project-data',
    component: ProjectDataView,
    meta: {
      title: '项目数据管理'
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
    path: '/settings',
    name: 'settings',
    component: SettingsView,
    meta: {
      title: '系统设置'
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
