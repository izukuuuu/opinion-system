import { createRouter, createWebHistory } from 'vue-router'
import TopicCreationLayout from '../views/topics/TopicCreationLayout.vue'
import TopicCreationOverview from '../views/topics/TopicCreationOverview.vue'
import TopicUploadStep from '../views/topics/TopicUploadStep.vue'
import TopicPreprocessStep from '../views/topics/TopicPreprocessStep.vue'
import TopicIngestionStep from '../views/topics/TopicIngestionStep.vue'
import ProjectDataView from '../views/ProjectDataView.vue'
import ProjectBasicAnalysisView from '../views/ProjectBasicAnalysisView.vue'
import DatabaseOverviewView from '../views/DatabaseOverviewView.vue'
import DatabaseDatasetsView from '../views/DatabaseDatasetsView.vue'
import TestView from '../views/TestView.vue'
import SettingsLayout from '../views/settings/SettingsLayout.vue'
import SettingsDatabasesView from '../views/settings/SettingsDatabasesView.vue'
import SettingsAiView from '../views/settings/SettingsAiView.vue'

export const routes = [
  {
    path: '/',
    redirect: { name: 'topic-create-overview' }
  },
  {
    path: '/topics/new',
    component: TopicCreationLayout,
    alias: ['/projects'],
    children: [
      {
        path: '',
        name: 'topic-create-overview',
        component: TopicCreationOverview,
        meta: {
          title: '新建专题',
          breadcrumb: '流程概览'
        }
      },
      {
        path: 'upload',
        name: 'topic-create-upload',
        component: TopicUploadStep,
        meta: {
          title: '上传原始数据',
          breadcrumb: '上传原始数据'
        }
      },
      {
        path: 'preprocess',
        name: 'topic-create-preprocess',
        component: TopicPreprocessStep,
        meta: {
          title: '数据预处理',
          breadcrumb: '数据预处理'
        }
      },
      {
        path: 'ingest',
        name: 'topic-create-ingest',
        component: TopicIngestionStep,
        meta: {
          title: '数据入库',
          breadcrumb: '数据入库'
        }
      },
    ]
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
    path: '/datasets/analysis',
    name: 'project-data-analysis',
    component: ProjectBasicAnalysisView,
    meta: {
      title: '专题基础分析'
    }
  },
  {
    path: '/database',
    name: 'database',
    component: DatabaseOverviewView,
    meta: {
      title: '数据库查询',
      breadcrumb: '数据库概览'
    }
  },
  {
    path: '/overview/datasets',
    name: 'overview-datasets',
    component: DatabaseDatasetsView,
    meta: {
      title: '数据集概览',
      breadcrumb: '数据集'
    }
  },
  {
    path: '/test',
    name: 'test',
    component: TestView,
    meta: {
      title: '测试工具'
    }
  },
  {
    path: '/settings',
    name: 'settings',
    component: SettingsLayout,
    meta: {
      title: '系统设置'
    },
    children: [
      {
        path: '',
        redirect: { name: 'settings-databases' }
      },
      {
        path: 'databases',
        name: 'settings-databases',
        component: SettingsDatabasesView,
        meta: {
          title: '数据库连接',
          breadcrumb: '数据库连接'
        }
      },
      {
        path: 'ai',
        name: 'settings-ai',
        component: SettingsAiView,
        meta: {
          title: 'AI 服务配置',
          breadcrumb: 'AI 服务配置'
        }
      }
    ]
  },
  {
    path: '/:pathMatch(.*)*',
    redirect: { name: 'topic-create-overview' }
  }
]

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes
})

export default router
