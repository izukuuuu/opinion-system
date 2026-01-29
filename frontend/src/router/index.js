import { createRouter, createWebHistory } from 'vue-router'
import HomeView from '../views/HomeView.vue'
import TopicCreationLayout from '../views/topics/TopicCreationLayout.vue'
import TopicCreationOverview from '../views/topics/TopicCreationOverview.vue'
import TopicUploadStep from '../views/topics/TopicUploadStep.vue'
import TopicPreprocessStep from '../views/topics/TopicPreprocessStep.vue'
import TopicFilterStep from '../views/topics/TopicFilterStep.vue'
import TopicIngestionStep from '../views/topics/TopicIngestionStep.vue'
import ProjectDataLayout from '../views/project-data/ProjectDataLayout.vue'
import ProjectDataLocalView from '../views/project-data/ProjectDataLocalView.vue'
import ProjectDataRemoteCacheView from '../views/project-data/ProjectDataRemoteCacheView.vue'
import ProjectBasicAnalysisLayout from '../views/analysis/basic/ProjectBasicAnalysisLayout.vue'
import ProjectBasicAnalysisOverview from '../views/analysis/basic/ProjectBasicAnalysisOverview.vue'
import ProjectBasicAnalysisRun from '../views/analysis/basic/ProjectBasicAnalysisRun.vue'
import ProjectBasicAnalysisResults from '../views/analysis/basic/ProjectBasicAnalysisResults.vue'
import ContentAnalysisPrompt from '../views/analysis/content/ContentAnalysisPrompt.vue'
import TopicBertopicLayout from '../views/analysis/topic/TopicBertopicLayout.vue'
import TopicBertopicOverview from '../views/analysis/topic/TopicBertopicOverview.vue'
import TopicBertopicRun from '../views/analysis/topic/TopicBertopicRun.vue'
import TopicBertopicResults from '../views/analysis/topic/TopicBertopicResults.vue'
import ReportGenerationView from '../views/analysis/ReportGenerationView.vue'
import DatabaseOverviewView from '../views/DatabaseOverviewView.vue'
import DatabaseDatasetsView from '../views/DatabaseDatasetsView.vue'
import SettingsLayout from '../views/settings/SettingsLayout.vue'
import SettingsDatabasesView from '../views/settings/SettingsDatabasesView.vue'
import SettingsAiView from '../views/settings/SettingsAiView.vue'
import SettingsThemeView from '../views/settings/SettingsThemeView.vue'
import SettingsBackendView from '../views/settings/SettingsBackendView.vue'
import SettingsArchivesView from '../views/settings/SettingsArchivesView.vue'
import PlaceholderModuleView from '../views/PlaceholderModuleView.vue'

export const routes = [
  {
    path: '/',
    name: 'home',
    component: HomeView,
    meta: {
      title: '系统简介',
      layout: 'landing'
    }
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
          title: '新建专题 · 上传原始数据',
          breadcrumb: '上传原始数据'
        }
      },
      {
        path: 'preprocess',
        name: 'topic-create-preprocess',
        component: TopicPreprocessStep,
        meta: {
          title: '新建专题 · 数据预处理',
          breadcrumb: '数据预处理'
        }
      },
      {
        path: 'filter',
        name: 'topic-create-filter',
        component: TopicFilterStep,
        meta: {
          title: '新建专题 · 筛选数据',
          breadcrumb: '筛选数据'
        }
      },
      {
        path: 'ingest',
        name: 'topic-create-ingest',
        component: TopicIngestionStep,
        meta: {
          title: '新建专题 · 数据入库',
          breadcrumb: '数据入库'
        }
      },
    ]
  },
  {
    path: '/datasets',
    component: ProjectDataLayout,
    meta: {
      title: '项目数据管理'
    },
    children: [
      {
        path: '',
        name: 'project-data',
        component: ProjectDataLocalView,
        meta: {
          title: '项目数据 · 本地数据管理',
          description: '导入 Excel 并维护项目数据集'
        }
      },
      {
        path: 'remote-cache',
        name: 'project-data-remote-cache',
        component: ProjectDataRemoteCacheView,
        meta: {
          title: '项目数据 · 远程数据缓存',
          description: '将远程数据库内容按时间区间缓存到本地并查看生成的 JSONL 文件'
        }
      }
    ]
  },
  {
    path: '/analysis/basic',
    component: ProjectBasicAnalysisLayout,
    children: [
      {
        path: '',
        name: 'project-data-analysis',
        component: ProjectBasicAnalysisOverview,
        meta: {
          title: '基础分析 · 流程概览',
          breadcrumb: '流程概览'
        }
      },
      {
        path: 'run',
        name: 'project-data-analysis-run',
        component: ProjectBasicAnalysisRun,
        meta: {
          title: '基础分析 · 运行分析',
          breadcrumb: '运行分析'
        }
      },
      {
        path: 'view',
        name: 'project-data-analysis-view',
        component: ProjectBasicAnalysisResults,
        meta: {
          title: '基础分析 · 查看分析',
        breadcrumb: '查看分析'
        }
      }
    ]
  },
  {
    path: '/analysis/content',
    name: 'content-analysis-prompt',
    component: ContentAnalysisPrompt,
    meta: {
      title: '内容分析 · 提示词配置',
      breadcrumb: '内容分析'
    }
  },
  {
    path: '/analysis/report',
    name: 'report-generation',
    component: ReportGenerationView,
    meta: {
      title: '报告解读',
      breadcrumb: '报告解读'
    }
  },
  {
    path: '/analysis/interpretation',
    name: 'data-interpretation-engine',
    component: PlaceholderModuleView,
    meta: {
      title: '智能解读引擎',
      placeholder: '智能解读引擎功能正在筹备，敬请期待。'
    }
  },
  {
    path: '/analysis/topic/bertopic',
    component: TopicBertopicLayout,
    children: [
      {
        path: '',
        name: 'topic-analysis-bertopic',
        component: TopicBertopicOverview,
        meta: {
          title: 'BERTopic 主题分析',
          breadcrumb: '流程概览'
        }
      },
      {
        path: 'run',
        name: 'topic-analysis-bertopic-run',
        component: TopicBertopicRun,
        meta: {
          title: 'BERTopic 主题分析 · 运行',
          breadcrumb: '运行分析'
        }
      },
      {
        path: 'view',
        name: 'topic-analysis-bertopic-view',
        component: TopicBertopicResults,
        meta: {
          title: 'BERTopic 主题分析 · 查看结果',
          breadcrumb: '查看结果'
        }
      }
    ]
  },
  {
    path: '/analysis/interpretation/tagrag',
    name: 'data-interpretation-tagrag',
    component: PlaceholderModuleView,
    meta: {
      title: 'TagRAG 集成',
      placeholder: 'TagRAG 集成解读流程规划中。'
    }
  },
  {
    path: '/analysis/interpretation/multidimensional',
    name: 'data-interpretation-multidimensional',
    component: PlaceholderModuleView,
    meta: {
      title: '多维度解读',
      placeholder: '多维度智能解读能力即将上线。'
    }
  },
  {
    path: '/data-acquisition/platform',
    name: 'data-acquisition-platform',
    component: PlaceholderModuleView,
    meta: {
      title: '平台数据获取',
      placeholder: '平台数据获取能力规划中，敬请期待。'
    }
  },
  {
    path: '/analysis/deep/fluid-dynamics',
    name: 'deep-analysis-fluid-dynamics',
    component: PlaceholderModuleView,
    meta: {
      title: '舆论流体力学',
      placeholder: '舆论流体力学模块建设中，敬请期待。'
    }
  },
  {
    path: '/retrieval/tagrag',
    name: 'data-retrieval-tagrag',
    component: () => import('../views/retrieval/TagRAGView.vue'),
    meta: {
      title: 'TagRAG 检索',
      breadcrumb: 'TagRAG 检索'
    }
  },
  {
    path: '/retrieval/routerrag',
    name: 'data-retrieval-routerrag',
    component: () => import('../views/retrieval/RouterRAGView.vue'),
    meta: {
      title: 'RouterRAG 检索',
      breadcrumb: 'RouterRAG 检索'
    }
  },
  {
    path: '/retrieval/routerrag/graph',
    name: 'data-retrieval-routerrag-graph',
    component: PlaceholderModuleView,
    meta: {
      title: 'GraphRAG（知识图谱）',
      placeholder: '知识图谱驱动的 GraphRAG 检索方案筹备中。'
    }
  },
  {
    path: '/retrieval/routerrag/semantic',
    name: 'data-retrieval-routerrag-semantic',
    component: PlaceholderModuleView,
    meta: {
      title: 'NormalRAG（语义向量）',
      placeholder: '语义向量检索（NormalRAG）正在建设。'
    }
  },
  {
    path: '/retrieval/routerrag/tag',
    name: 'data-retrieval-routerrag-tag',
    component: PlaceholderModuleView,
    meta: {
      title: 'TagRAG（标签向量）',
      placeholder: 'RouterRAG 中的标签向量检索能力即将上线。'
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
    path: '/settings',
    name: 'settings',
    component: SettingsLayout,
    meta: {
      title: '系统设置'
    },
    children: [
      {
        path: '',
        name: 'settings-default',
        redirect: { name: 'settings-backend' }
      },
      {
        path: 'backend',
        name: 'settings-backend',
        component: SettingsBackendView,
        meta: {
          title: '后端地址',
          breadcrumb: '后端地址'
        }
      },
      {
        path: 'archives',
        name: 'settings-archives',
        component: SettingsArchivesView,
        meta: {
          title: '存档导入导出',
          breadcrumb: '存档导入导出'
        }
      },
      {
        path: 'appearance/theme',
        name: 'settings-theme',
        component: SettingsThemeView,
        meta: {
          title: '主题颜色',
          breadcrumb: '主题颜色'
        }
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
      },
      {
        path: 'rag',
        name: 'settings-rag',
        component: () => import('../views/settings/SettingsRAGView.vue'),
        meta: {
          title: 'RAG 配置',
          breadcrumb: 'RAG 配置'
        }
      },
      {
        path: 'experimental',
        name: 'settings-experimental',
        component: () => import('../views/settings/SettingsExperimentalView.vue'),
        meta: {
          title: '实验性功能',
          breadcrumb: '实验性功能'
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
