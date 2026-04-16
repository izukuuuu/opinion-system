import { createRouter, createWebHistory } from 'vue-router'

const HomeView = () => import('../views/HomeView.vue')
const SystemIntroView = () => import('../views/SystemIntroView.vue')
const TopicCreationLayout = () => import('../views/topics/TopicCreationLayout.vue')
const TopicCreationOverview = () => import('../views/topics/TopicCreationOverview.vue')
const TopicUploadStep = () => import('../views/topics/TopicUploadStep.vue')
const TopicPreprocessStep = () => import('../views/topics/TopicPreprocessStep.vue')
const TopicFilterStep = () => import('../views/topics/TopicFilterStep.vue')
const TopicIngestionStep = () => import('../views/topics/TopicIngestionStep.vue')
const DataProcessingLayout = () => import('../views/processing/DataProcessingLayout.vue')
const DataProcessingDeduplicateView = () => import('../views/processing/DataProcessingDeduplicateView.vue')
const DataProcessingPostcleanView = () => import('../views/processing/DataProcessingPostcleanView.vue')
const ProjectDataLayout = () => import('../views/project-data/ProjectDataLayout.vue')
const ProjectDataLocalView = () => import('../views/project-data/ProjectDataLocalView.vue')
const ProjectDataRemoteCacheView = () => import('../views/project-data/ProjectDataRemoteCacheView.vue')
const NetInsightQueueView = () => import('../views/data-acquisition/NetInsightQueueView.vue')
const ProjectBasicAnalysisLayout = () => import('../views/analysis/basic/ProjectBasicAnalysisLayout.vue')
const ProjectBasicAnalysisOverview = () => import('../views/analysis/basic/ProjectBasicAnalysisOverview.vue')
const ProjectBasicAnalysisRun = () => import('../views/analysis/basic/ProjectBasicAnalysisRun.vue')
const ProjectBasicAnalysisResults = () => import('../views/analysis/basic/ProjectBasicAnalysisResults.vue')
const MediaTaggingLayout = () => import('../views/analysis/media/MediaTaggingLayout.vue')
const MediaTaggingOverview = () => import('../views/analysis/media/MediaTaggingOverview.vue')
const MediaTaggingRun = () => import('../views/analysis/media/MediaTaggingRun.vue')
const MediaTaggingResults = () => import('../views/analysis/media/MediaTaggingResults.vue')
const ContentAnalysisPrompt = () => import('../views/analysis/content/ContentAnalysisPrompt.vue')
const TopicBertopicLayout = () => import('../views/analysis/topic/TopicBertopicLayout.vue')
const TopicBertopicOverview = () => import('../views/analysis/topic/TopicBertopicOverview.vue')
const TopicBertopicRun = () => import('../views/analysis/topic/TopicBertopicRun.vue')
const TopicBertopicResults = () => import('../views/analysis/topic/TopicBertopicResults.vue')
const ReportGenerationLayout = () => import('../views/analysis/ReportGenerationLayout.vue')
const ReportGenerationRun = () => import('../views/analysis/ReportGenerationRun.vue')
const ReportGenerationView = () => import('../views/analysis/ReportGenerationView.vue')
const ReportGenerationAiView = () => import('../views/analysis/ReportGenerationAiView.vue')
const DatabaseOverviewView = () => import('../views/DatabaseOverviewView.vue')
const DatabaseDatasetsView = () => import('../views/DatabaseDatasetsView.vue')
const SettingsLayout = () => import('../views/settings/SettingsLayout.vue')
const SettingsDatabasesView = () => import('../views/settings/SettingsDatabasesView.vue')
const SettingsAiView = () => import('../views/settings/SettingsAiView.vue')
const SettingsNetInsightView = () => import('../views/settings/SettingsNetInsightView.vue')
const SettingsThemeView = () => import('../views/settings/SettingsThemeView.vue')
const SettingsBackendView = () => import('../views/settings/SettingsBackendView.vue')
const SettingsArchivesView = () => import('../views/settings/SettingsArchivesView.vue')
const PlaceholderModuleView = () => import('../views/PlaceholderModuleView.vue')

export const routes = [
  {
    path: '/',
    name: 'home',
    component: HomeView,
    meta: {
      title: '首页',
      layout: 'landing'
    }
  },
  {
    path: '/system-intro',
    name: 'system-intro',
    component: SystemIntroView,
    meta: {
      title: '系统介绍',
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
    path: '/processing',
    component: DataProcessingLayout,
    children: [
      {
        path: '',
        redirect: { name: 'processing-deduplicate' }
      },
      {
        path: 'deduplicate',
        name: 'processing-deduplicate',
        component: DataProcessingDeduplicateView,
        meta: {
          title: '数据处理 · 数据库去重',
          breadcrumb: '数据库去重'
        }
      },
      {
        path: 'postclean',
        name: 'processing-postclean',
        component: DataProcessingPostcleanView,
        meta: {
          title: '数据处理 · 后清洗',
          breadcrumb: '后清洗'
        }
      }
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
    path: '/analysis/media-tags',
    component: MediaTaggingLayout,
    children: [
      {
        path: '',
        name: 'analysis-media-tagging',
        component: MediaTaggingOverview,
        meta: {
          title: '媒体识别与打标 · 流程概览',
          breadcrumb: '流程概览'
        }
      },
      {
        path: 'run',
        name: 'analysis-media-tagging-run',
        component: MediaTaggingRun,
        meta: {
          title: '媒体识别与打标 · 运行识别',
          breadcrumb: '运行识别'
        }
      },
      {
        path: 'view',
        name: 'analysis-media-tagging-view',
        component: MediaTaggingResults,
        meta: {
          title: '媒体识别与打标 · 查看结果',
          breadcrumb: '查看结果'
        }
      }
    ]
  },
  {
    path: '/analysis/report',
    component: ReportGenerationLayout,
    children: [
      {
        path: '',
        redirect: { name: 'report-generation-run' }
      },
      {
        path: 'run',
        name: 'report-generation-run',
        component: ReportGenerationRun,
        meta: {
          title: '报告生成 · 运行',
          breadcrumb: '运行报告'
        }
      },
      {
        path: 'view',
        name: 'report-generation-view',
        component: ReportGenerationView,
        meta: {
          title: '报告解读 · 查看结果',
          breadcrumb: '查看报告'
        }
      },
      {
        path: 'ai',
        name: 'report-generation-ai',
        component: ReportGenerationAiView,
        meta: {
          title: '报告解读 · AI 完整报告',
          breadcrumb: 'AI 完整报告'
        }
      }
    ]
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
    path: '/topic/bertopic',
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
    component: NetInsightQueueView,
    meta: {
      title: '平台数据获取',
      breadcrumb: 'NetInsight 下载队列',
      fullscreen: true
    }
  },
  {
    path: '/deep-analysis/fluid-dynamics',
    component: () => import('../views/analysis/deep/fluid/FluidAnalysisLayout.vue'),
    children: [
      {
        path: '',
        name: 'deep-analysis-fluid-dynamics',
        component: () => import('../views/analysis/deep/fluid/FluidAnalysisOverview.vue'),
        meta: {
          title: '舆论流体力学 · 概览',
          breadcrumb: '流程概览'
        }
      },
      {
        path: 'run',
        name: 'deep-analysis-fluid-dynamics-run',
        component: () => import('../views/analysis/deep/fluid/FluidAnalysisRun.vue'),
        meta: {
          title: '舆论流体力学 · 运行分析',
          breadcrumb: '运行分析'
        }
      },
      {
        path: 'view',
        name: 'deep-analysis-fluid-dynamics-view',
        component: () => import('../views/analysis/deep/fluid/FluidAnalysisResults.vue'),
        meta: {
          title: '舆论流体力学 · 查看结果',
          breadcrumb: '查看结果'
        }
      }
    ]
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
        path: 'advanced/theme',
        name: 'settings-theme',
        component: SettingsThemeView,
        meta: {
          title: '主题颜色',
          breadcrumb: '主题颜色'
        }
      },
      {
        path: 'appearance/theme',
        redirect: { name: 'settings-theme' }
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
        path: 'netinsight',
        name: 'settings-netinsight',
        component: SettingsNetInsightView,
        meta: {
          title: 'NetInsight 配置',
          breadcrumb: 'NetInsight 配置'
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
        path: 'bertopic',
        name: 'settings-bertopic',
        component: () => import('../views/settings/SettingsBertopicView.vue'),
        meta: {
          title: 'BERTopic 配置',
          breadcrumb: 'BERTopic 配置'
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
