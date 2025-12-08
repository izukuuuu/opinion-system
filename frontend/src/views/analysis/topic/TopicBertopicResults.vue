<template>
  <div class="topic-dashboard space-y-8">
    <header class="rounded-2xl border border-soft bg-surface p-6 shadow-sm">
      <div class="flex flex-col gap-2">
        <p class="text-xs font-medium uppercase tracking-wide text-secondary">主题分析 · BERTopic</p>
        <h1 class="text-2xl font-semibold text-primary">查看 BERTopic + Qwen 主题分析结果</h1>
        <p class="text-sm text-secondary">
          选择专题与时间区间，查看已生成的 BERTopic 分析结果，包括主题统计、关键词、降维坐标以及 LLM 再聚类结果。
        </p>
      </div>
    </header>

    <!-- 查询参数 -->
    <section class="rounded-2xl border border-soft bg-surface p-6 shadow-sm">
      <h2 class="text-lg font-semibold text-primary mb-6">查询参数</h2>

      <!-- 历史记录选择 -->
      <div v-if="analysisHistory.length > 0" class="mb-6">
        <label class="block text-sm font-medium text-primary mb-2">
          <span class="text-xs font-semibold text-muted">历史记录</span>
          <select
            v-model="selectedHistoryId"
            class="input mt-1"
            @change="applyHistorySelection(selectedHistoryId, { shouldLoad: true })"
          >
            <option value="">选择历史分析记录...</option>
            <option
              v-for="record in analysisHistory"
              :key="record.id"
              :value="record.id"
            >
              {{ formatTimestamp(record.start) }} - {{ formatTimestamp(record.end) }} ({{ record.topic }})
            </option>
          </select>
        </label>
      </div>

      <!-- 手动输入表单 -->
      <form @submit.prevent="loadResultsFromManual" class="space-y-6">
        <div class="grid gap-4 md:grid-cols-2">
          <label class="flex flex-col gap-1 text-sm font-medium text-primary">
            <div class="flex items-center justify-between gap-2">
              <span class="text-xs font-semibold text-muted">专题 Topic *</span>
              <button
                type="button"
                class="inline-flex items-center gap-1 text-[11px] font-medium text-brand-600 hover:text-brand-700 disabled:cursor-default disabled:opacity-60"
                :disabled="topicsState.loading"
                @click="loadTopics(true)"
              >
                <ArrowPathIcon
                  class="h-3 w-3"
                  :class="topicsState.loading ? 'animate-spin text-brand-600' : 'text-brand-600'"
                />
                <span>{{ topicsState.loading ? '刷新中…' : '刷新专题' }}</span>
              </button>
            </div>
            <select
              v-model="viewManualForm.topic"
              class="input"
              :disabled="topicsState.loading || topicOptions.length === 0"
            >
              <option value="" disabled>请选择专题</option>
              <option v-for="option in topicOptions" :key="option.bucket" :value="option.bucket">
                {{ option.display_name || option.name }}
              </option>
            </select>
          </label>

          <label class="flex flex-col gap-1 text-sm font-medium text-primary">
            <span class="text-xs font-semibold text-muted">开始日期 Start *</span>
            <input
              v-model.trim="viewManualForm.start"
              type="date"
              class="input"
              :disabled="loadState.loading"
            />
          </label>

          <label class="flex flex-col gap-1 text-sm font-medium text-primary">
            <span class="text-xs font-semibold text-muted">结束日期 End</span>
            <input
              v-model.trim="viewManualForm.end"
              type="date"
              class="input"
              :disabled="loadState.loading"
              :min="viewManualForm.start"
            />
          </label>
        </div>

        <!-- 数据可用性提示 -->
        <div v-if="availableRange.start || availableRange.error" class="rounded-xl border p-3 text-sm"
             :class="availableRange.error ? 'border-red-200 bg-red-50' : 'border-blue-200 bg-blue-50'">
          <div class="flex items-start gap-2">
            <span class="text-base">{{ availableRange.error ? '⚠️' : 'ℹ️' }}</span>
            <div>
              <p class="font-medium" :class="availableRange.error ? 'text-red-700' : 'text-blue-700'">
                数据可用性
              </p>
              <p v-if="availableRange.error" class="text-red-600 text-xs mt-1">{{ availableRange.error }}</p>
              <p v-else class="text-blue-600 text-xs mt-1">
                数据范围：{{ availableRange.start }} ~ {{ availableRange.end }}
              </p>
            </div>
          </div>
        </div>

        <div class="flex flex-wrap gap-3">
          <button
            type="submit"
            class="btn btn-primary"
            :disabled="!viewManualForm.topic || !viewManualForm.start || loadState.loading"
          >
            {{ loadState.loading ? '加载中…' : '加载结果' }}
          </button>
          <button
            type="button"
            class="btn btn-soft"
            @click="viewManualForm.topic = viewSelection.topic; viewManualForm.start = viewSelection.start; viewManualForm.end = viewSelection.end"
            :disabled="loadState.loading"
          >
            重置为当前选择
          </button>
        </div>
      </form>

      <p v-if="loadState.error" class="mt-4 rounded-xl border border-red-200 bg-red-50/70 p-4 text-sm text-red-700">
        {{ loadState.error }}
      </p>
    </section>

    <section v-if="hasSummary" class="topic-dashboard__card space-y-6">
      <div class="dashboard-controls">
        <label>
          <span>🔍 搜索主题</span>
          <input v-model.trim="controls.search" type="text" placeholder="输入主题名称关键字…" />
        </label>
        <label>
          <span>📊 排序方式</span>
          <select v-model="controls.sort">
            <option value="docCount-desc">文档数 ↓</option>
            <option value="docCount-asc">文档数 ↑</option>
            <option value="name-asc">主题名称 A-Z</option>
            <option value="name-desc">主题名称 Z-A</option>
          </select>
        </label>
        <label class="topic-dashboard__range">
          <span>📈 显示数量 (Top-N)</span>
          <div class="range-input">
            <input
              :value="controls.topN"
              type="range"
              min="3"
              :max="Math.max(7, maxTopN)"
              @input="updateTopN($event.target.value)"
            />
            <span>{{ controls.topN }}</span>
          </div>
        </label>
      </div>

      <div class="dashboard-overview">
        <div class="overview-header">
          <h3 class="overview-header__title">📈 数据概览</h3>
          <div class="overview-actions">
            <button 
              class="btn-export" 
              @click="exportData"
              title="导出数据"
            >
              📥 导出数据
            </button>
          </div>
        </div>
      <div class="dashboard-stats">
          <div class="stat-card stat-card--primary">
            <div class="stat-card__icon">📊</div>
            <div class="stat-card__content">
          <p class="stat-card__value">{{ llmStats.count }}</p>
          <p class="stat-card__label">新主题总数</p>
              <p v-if="docStats.topicCount > 0" class="stat-card__subtext">
                原始主题: {{ docStats.topicCount }}
              </p>
        </div>
          </div>
          <div class="stat-card stat-card--success">
            <div class="stat-card__icon">📄</div>
            <div class="stat-card__content">
          <p class="stat-card__value">{{ llmStats.totalDocs.toLocaleString() }}</p>
          <p class="stat-card__label">文档总数</p>
              <p v-if="docStats.topicCount > 0" class="stat-card__subtext">
                平均: {{ Math.round(llmStats.totalDocs / docStats.topicCount) }} 篇/主题
              </p>
        </div>
          </div>
          <div class="stat-card stat-card--info">
            <div class="stat-card__icon">📈</div>
            <div class="stat-card__content">
          <p class="stat-card__value">{{ llmStats.maxDocs.toLocaleString() }}</p>
          <p class="stat-card__label">最大主题文档数</p>
              <p v-if="llmStats.totalDocs > 0" class="stat-card__subtext">
                占比: {{ ((llmStats.maxDocs / llmStats.totalDocs) * 100).toFixed(1) }}%
              </p>
            </div>
          </div>
          <div class="stat-card stat-card--warning">
            <div class="stat-card__icon">🎯</div>
            <div class="stat-card__content">
              <p class="stat-card__value">{{ docStats.topicCount }}</p>
              <p class="stat-card__label">原始主题数</p>
              <p v-if="llmStats.count > 0" class="stat-card__subtext">
                合并率: {{ ((1 - llmStats.count / docStats.topicCount) * 100).toFixed(1) }}%
              </p>
            </div>
          </div>
        </div>
      </div>
    </section>

    <section v-if="hasSummary" class="space-y-6">
      <div class="topic-dashboard__chart-grid">
        <PlotlyChartPanel
          :data="barPlotlyData"
          :layout="barPlotlyLayout"
          :config="barPlotlyConfig"
          :has-data="barPlotlyHasData"
          title="📊 主题规模对比（横向条形）"
          description="支持搜索、排序与 Top-N 显示控制，便于定位关注主题。"
        />
        <PlotlyChartPanel
          :data="donutPlotlyData"
          :layout="donutPlotlyLayout"
          :config="donutPlotlyConfig"
          :has-data="donutPlotlyHasData"
          title="🥧 主题占比（环形图）"
          description="基于文档数计算占比，直观呈现主题贡献度。"
        />
      </div>

      <div v-if="sankeyPlotlyHasData" class="chart-panel--tall">
        <PlotlyChartPanel
          :data="sankeyPlotlyData"
          :layout="sankeyPlotlyLayout"
          :config="sankeyPlotlyConfig"
          :has-data="sankeyPlotlyHasData"
          title="🌊 原始主题 → 新主题合并关系（桑基图）"
          description="展示 BERTopic 原始主题与 LLM 新主题之间的合并关系。"
        />
      </div>
    </section>

    <section v-if="coordsOption.hasData" class="topic-dashboard__card umap-section">
      <div class="umap-controls">
        <div class="umap-control-row">
          <label>密度视图：</label>
          <input 
            v-model="umapControls.density" 
            type="checkbox" 
            @change="updateUMAPChart"
            aria-label="启用密度视图"
          />
          <label>降采样上限：</label>
          <input 
            v-model.number="umapControls.maxPoints" 
            type="number" 
            min="1000" 
            step="1000" 
            @change="updateUMAPChart"
            aria-label="降采样上限"
            placeholder="5000"
          />
          <button @click="updateUMAPChart">应用</button>
          <button @click="downloadSelectedDocIds">下载选中 doc_id</button>
          <span class="umap-selected-info">已选 {{ selectedDocIds.length }} 条</span>
        </div>
        <div class="umap-control-row">
          <span>按主题筛选：</span>
          <div class="umap-topics-box">
            <label v-for="topicId in availableTopics" :key="topicId" class="umap-topic-item">
              <input
                type="checkbox"
                :value="topicId"
                v-model="umapControls.selectedTopics"
                @change="updateUMAPChart"
              />
              <span>{{ topicId }}</span>
            </label>
          </div>
        </div>
      </div>
      <AnalysisChartPanel
        ref="umapChartRef"
        :option="coordsOption.option"
        :has-data="coordsOption.hasData"
        title="文档分布地图（UMAP 2D）"
        description="散点≈6k：颜色=topic_id；缩放/拖拽/框选；密度开关；超5k自动降采样。"
      />
    </section>

    <!-- LLM 再聚类结果详细展示 -->
    <section v-if="llmClusters.length > 0" class="topic-dashboard__card">
      <div class="section-header">
        <h2 class="section-header__title">🤖 LLM 再聚类结果</h2>
        <p class="section-header__subtitle">大模型重新命名和聚类的主题详情</p>
      </div>
      <div class="llm-clusters-grid">
        <div 
          v-for="cluster in sortedLLMClusters" 
          :key="cluster.name"
          class="llm-cluster-card"
        >
          <div class="llm-cluster-card__header">
            <div class="llm-cluster-card__title-group">
              <p class="llm-cluster-card__label">{{ cluster.name }}</p>
              <h3 class="llm-cluster-card__title">{{ cluster.title }}</h3>
            </div>
            <div class="llm-cluster-card__badge">{{ cluster.count }} 篇文档</div>
          </div>
          <p v-if="cluster.description" class="llm-cluster-card__description">
            {{ cluster.description }}
          </p>
          <div v-if="cluster.original && cluster.original.length > 0" class="llm-cluster-card__original">
            <span class="llm-cluster-card__original-label">原始主题：</span>
            <template v-for="(orig, idx) in cluster.original" :key="idx">
              <span class="llm-cluster-card__original-tag" :title="formatOriginalTopicName(orig)">
                {{ getOriginalTopicSummary(orig) }}
            </span>
            </template>
          </div>
          <div v-if="cluster.keywords && cluster.keywords.length > 0" class="llm-cluster-card__keywords">
            <span class="llm-cluster-card__keywords-label">关键词：</span>
            <span 
              v-for="(kw, idx) in cluster.keywords" 
              :key="idx"
              class="llm-cluster-card__keyword-tag"
              :title="Array.isArray(kw) ? `权重: ${(kw[1] * 100).toFixed(1)}%` : ''"
            >
              {{ Array.isArray(kw) ? kw[0] : kw }}
            </span>
          </div>
        </div>
      </div>
    </section>

    <section
      v-if="!loadState.loading && !loadState.error && !hasSummary"
      class="topic-dashboard__card topic-dashboard__empty"
    >
      暂无可视化数据，请先填写专题与时间并点击"加载结果"。
    </section>
  </div>
</template>

<script setup>
import { computed, reactive, watch, onMounted, nextTick, ref } from 'vue'
import { ArrowPathIcon } from '@heroicons/vue/24/outline'
import AnalysisChartPanel from '@/components/AnalysisChartPanel.vue'
import PlotlyChartPanel from '@/components/PlotlyChartPanel.vue'
import { useTopicBertopicView } from '@/composables/useTopicBertopicView'
import { useActiveProject } from '@/composables/useActiveProject'
import * as echarts from 'echarts'

const {
  topicsState,
  topicOptions,
  viewSelection,
  viewManualForm,
  loadState,
  bertopicData,
  hasResults,
  historyState,
  analysisHistory,
  selectedHistoryId,
  selectedRecord,
  availableRange,
  bertopicStats,
  loadTopics,
  loadHistory,
  loadResults,
  loadResultsFromManual,
  refreshHistory,
  applyHistorySelection,
  formatTimestamp
} = useTopicBertopicView()

// 控制面板状态
const controls = reactive({
  search: '',
  sort: 'docCount-desc',
  topN: 7
})

// UMAP 控制
const umapControls = reactive({
  density: false,
  maxPoints: 5000,
  selectedTopics: []
})

const selectedDocIds = ref([])
const availableTopics = ref([])
const umapChartRef = ref(null)
let umapChartInstance = null

const { activeProjectName } = useActiveProject()

// 监听活动项目变化
watch(
  activeProjectName,
  (value) => {
    if (value && !viewSelection.topic) {
      const matched = topicOptions.value.find(t =>
        t.name === value || t.display_name === value || t.bucket === value
      )
      if (matched) {
        viewSelection.topic = matched.bucket
        viewManualForm.topic = matched.bucket
      }
    }
  },
  { immediate: true }
)

onMounted(() => {
  // 加载专题列表
  loadTopics(true)
})

// 后端返回的数据结构：bertopicData = { files: { summary: {...}, keywords: {...}, ... } }
const results = computed(() => {
  if (!bertopicData.value) return {}
  // 处理嵌套的 data 结构
  if (bertopicData.value.data && bertopicData.value.data.files) {
    return bertopicData.value.data.files
  }
  // 处理直接的 files 结构
  if (bertopicData.value.files) {
    return bertopicData.value.files
  }
  // 兼容旧格式
  return bertopicData.value.results || {}
})
const hasSummary = computed(() => Boolean(results.value.summary))

const summaryEntries = computed(() => {
  // summary 包含 "主题文档统计"
  const summary = results.value.summary || {}
  const stats = summary['主题文档统计'] || {}
  // keywords 包含 "主题关键词"
  const keywordsData = results.value.keywords || {}
  const keywords = keywordsData['主题关键词'] || {}
  const total = Object.values(stats).reduce((sum, info) => sum + (info['文档数'] || 0), 0)
  const entries = Object.entries(stats).map(([name, info]) => {
    const keywordList = keywords[name]?.关键词 || keywords[name] || []
    return {
      name,
      label: name,
      docCount: info['文档数'] || 0,
      ratio: total ? (info['文档数'] / total) * 100 : 0,
      keywords: (keywordList || []).slice(0, 10).map((item) => [item[0], Number(item[1]) || 0])
    }
  })
  return { entries, total }
})

const topicDocMap = computed(() =>
  summaryEntries.value.entries.reduce((acc, item) => {
    acc[item.name] = item.docCount
    return acc
  }, {})
)

const filteredTopics = computed(() => {
  let rows = summaryEntries.value.entries
  if (!rows.length) return []
  const keyword = controls.search.trim()
  if (keyword) {
    rows = rows.filter((item) => item.name.toLowerCase().includes(keyword.toLowerCase()))
  }
  const sorted = [...rows]
  switch (controls.sort) {
    case 'docCount-asc':
      sorted.sort((a, b) => a.docCount - b.docCount)
      break
    case 'name-asc':
      sorted.sort((a, b) => a.name.localeCompare(b.name))
      break
    case 'name-desc':
      sorted.sort((a, b) => b.name.localeCompare(a.name))
      break
    default:
      sorted.sort((a, b) => b.docCount - a.docCount)
  }
  return sorted
})

const maxTopN = computed(() => Math.max(1, filteredTopics.value.length || 1))

watch(
  () => maxTopN.value,
  (max) => {
    if (controls.topN > max) {
      controls.topN = max
    }
  }
)

const topTopics = computed(() =>
  filteredTopics.value.slice(0, Math.min(controls.topN, filteredTopics.value.length))
)

const docStats = computed(() => {
  const entries = summaryEntries.value.entries
  if (!entries.length) {
    return { topicCount: 0, docTotal: 0, maxDocs: 0 }
  }
  const maxDocs = entries.reduce((max, item) => Math.max(max, item.docCount), 0)
  return {
    topicCount: entries.length,
    docTotal: summaryEntries.value.total,
    maxDocs
  }
})

const llmClusters = computed(() => {
  // llm_clusters 包含大模型再聚类结果
  const clusters = results.value.llm_clusters || {}
  // llm_keywords 包含大模型主题关键词
  const llmKeywords = results.value.llm_keywords || {}
  
  if (!clusters || Object.keys(clusters).length === 0) {
    return []
  }
  
  const entries = Array.isArray(clusters)
    ? clusters.map((item, idx) => {
        const name = item.name || `新主题${idx}`
        // 尝试从 llm_keywords 中获取关键词
        const keywordsFromFile = llmKeywords[name]?.['关键词'] || llmKeywords[name] || []
        // 处理原始主题集合，确保是数组格式
        let originalTopics = []
        if (Array.isArray(item['原始主题集合'])) {
          originalTopics = item['原始主题集合'].map(t => String(t).trim()).filter(t => t)
        } else if (item['原始主题集合']) {
          // 如果不是数组，尝试转换
          const orig = item['原始主题集合']
          if (typeof orig === 'string') {
            originalTopics = orig.split(',').map(t => t.trim()).filter(t => t)
          }
        }
        return {
          name,
          title: item['主题命名'] || name,
          description: item['主题描述'] || '',
          original: originalTopics,
          keywords: keywordsFromFile.length > 0 ? keywordsFromFile.slice(0, 10) : (item['关键词'] || []).slice(0, 10),
          count: item['文档数'] || (Array.isArray(item['文档ID']) ? item['文档ID'].length : 0)
        }
      })
    : Object.entries(clusters).map(([name, info]) => {
        // 尝试从 llm_keywords 中获取关键词
        const keywordsFromFile = llmKeywords[name]?.['关键词'] || llmKeywords[name] || []
        // 处理原始主题集合，确保是数组格式
        let originalTopics = []
        if (Array.isArray(info?.['原始主题集合'])) {
          originalTopics = info['原始主题集合'].map(t => String(t).trim()).filter(t => t)
        } else if (info?.['原始主题集合']) {
          // 如果不是数组，尝试转换
          const orig = info['原始主题集合']
          if (typeof orig === 'string') {
            originalTopics = orig.split(',').map(t => t.trim()).filter(t => t)
          }
        }
        return {
          name,
          title: info?.['主题命名'] || name,
          description: info?.['主题描述'] || '',
          original: originalTopics,
          keywords: keywordsFromFile.length > 0 ? keywordsFromFile.slice(0, 10) : (info?.['关键词'] || []).slice(0, 10),
          count: info?.['文档数'] || (Array.isArray(info?.['文档ID']) ? info['文档ID'].length : 0)
        }
      })
  return entries
})

// 创建从原始主题名到 LLM 主题命名的映射
const originalTopicToLLMName = computed(() => {
  const mapping = {}
  llmClusters.value.forEach((cluster) => {
    // 确保 original 是数组
    const originalTopics = Array.isArray(cluster.original) ? cluster.original : []
    originalTopics.forEach((origTopic) => {
      // 确保 origTopic 是字符串
      const topicKey = String(origTopic).trim()
      if (topicKey && (!mapping[topicKey] || cluster.count > (mapping[topicKey].count || 0))) {
        mapping[topicKey] = {
          title: cluster.title,
          count: cluster.count
        }
      }
    })
  })
  // 调试：输出映射结果
  if (Object.keys(mapping).length > 0) {
    console.log('原始主题到LLM主题映射:', mapping)
  } else if (llmClusters.value.length > 0) {
    console.warn('LLM聚类结果存在但无法建立映射，检查原始主题集合格式:', llmClusters.value)
  }
  return mapping
})

const llmStats = computed(() => {
  // 如果有LLM聚类，使用LLM聚类数据；否则使用原始主题数据
  if (llmClusters.value.length > 0) {
    const totalDocs = llmClusters.value.reduce((sum, cluster) => sum + (cluster.count || 0), 0)
    const maxDocs = llmClusters.value.reduce((max, cluster) => Math.max(max, cluster.count || 0), 0)
    return {
      count: llmClusters.value.length,
      totalDocs,
      maxDocs
    }
  } else {
    // 使用原始主题数据
    const totalDocs = docStats.value.docTotal
    const maxDocs = docStats.value.maxDocs
    return {
      count: docStats.value.topicCount,
      totalDocs,
      maxDocs
    }
  }
})

// 格式化原始主题名称（用于title提示）
const formatOriginalTopicName = (orig) => {
  if (!orig) return ''
  const str = String(orig).trim()
  // 如果已经是"主题X"格式，直接返回
  if (str.startsWith('主题')) {
    return str
  }
  // 如果是纯数字，添加"主题"前缀
  if (/^\d+$/.test(str)) {
    return `主题${str}`
  }
  // 其他情况直接返回
  return str
}

// 获取原始主题的关键词摘要
const getOriginalTopicSummary = (origTopicName) => {
  if (!origTopicName) return ''
  
  const topicName = formatOriginalTopicName(origTopicName)
  
  // 从 summaryEntries 中查找该主题的关键词
  const topic = summaryEntries.value.entries.find(t => t.name === topicName)
  
  if (topic && topic.keywords && topic.keywords.length > 0) {
    // 取前3-5个关键词，用顿号连接
    const topKeywords = topic.keywords.slice(0, 5).map(kw => kw[0]).join('、')
    return `${topicName}: ${topKeywords}`
  }
  
  // 如果没有找到关键词，返回主题名称
  return topicName
}

// 排序后的 LLM 聚类结果（按文档数降序）
const sortedLLMClusters = computed(() => {
  return [...llmClusters.value].sort((a, b) => (b.count || 0) - (a.count || 0))
})

// 排序后的原始主题统计（按文档数降序）
const sortedSummaryEntries = computed(() => {
  return [...summaryEntries.value.entries].sort((a, b) => b.docCount - a.docCount)
})

// 获取原始主题关键词（用于桑基图节点标签）
const getOriginalTopicKeywords = (topicName) => {
  const topic = summaryEntries.value.entries.find(t => t.name === topicName)
  if (topic && topic.keywords) {
    return topic.keywords.slice(0, 5).map(k => k[0]).join('、')
  }
  return ''
}

// Plotly 条形图配置（对照模板 - 使用LLM再聚类后的新主题）
const barPlotlyHasData = computed(() => {
  // 如果有LLM聚类，使用LLM聚类；否则使用原始主题
  const dataSource = llmClusters.value.length > 0 ? llmClusters.value : topTopics.value
  return dataSource.length > 0
})
const barPlotlyData = computed(() => {
  // 如果有LLM聚类，使用LLM聚类；否则使用原始主题
  const dataSource = llmClusters.value.length > 0 ? llmClusters.value : topTopics.value
  if (!dataSource.length) return []
  
  // 对LLM聚类进行排序和筛选
  let sortedData = [...dataSource]
  if (llmClusters.value.length > 0) {
    // LLM聚类模式：按文档数排序，支持搜索和Top-N
    const keyword = controls.search.trim()
    if (keyword) {
      sortedData = sortedData.filter(item => 
        item.name?.toLowerCase().includes(keyword.toLowerCase()) ||
        item.title?.toLowerCase().includes(keyword.toLowerCase())
      )
    }
    const [field, order] = controls.sort.split('-')
    sortedData.sort((a, b) => {
      const va = field === 'docCount' ? (a.count || 0) : (a.name || '')
      const vb = field === 'docCount' ? (b.count || 0) : (b.name || '')
      if (field === 'docCount') {
        return order === 'desc' ? (vb - va) : (va - vb)
      } else {
        return order === 'desc' ? vb.localeCompare(va) : va.localeCompare(vb)
      }
    })
    sortedData = sortedData.slice(0, controls.topN)
  }
  
  const colors = ['#4361ee', '#3a0ca3', '#7209b7', '#f72585', '#4cc9f0', '#4895ef', '#560bad']
  
  return [{
    y: sortedData.map(item => {
      if (llmClusters.value.length > 0) {
        // LLM聚类模式
        return `${item.name} - ${item.title}`
      } else {
        // 原始主题模式
        const llmInfo = originalTopicToLLMName.value[item.name]
        const label = llmInfo?.title || item.name
        return `${item.name} - ${label}`
      }
    }),
    x: sortedData.map(item => llmClusters.value.length > 0 ? item.count : item.docCount),
    type: 'bar',
    orientation: 'h',
    marker: {
      color: sortedData.map((_, i) => colors[i % colors.length]),
      line: { color: 'rgba(255,255,255,.8)', width: 1 }
    },
    text: sortedData.map(item => {
      const count = llmClusters.value.length > 0 ? item.count : item.docCount
      return `${count}篇`
    }),
    textposition: 'outside',
    hovertemplate: '<b>%{y}</b><br>文档数: %{x}<br>原始主题: %{customdata}<extra></extra>',
    customdata: sortedData.map(item => {
      if (llmClusters.value.length > 0) {
        return Array.isArray(item.original) ? item.original.join(', ') : ''
      } else {
        const llmCluster = llmClusters.value.find(c => 
          Array.isArray(c.original) && c.original.includes(item.name)
        )
        return llmCluster ? llmCluster.original.join(', ') : item.name
      }
    })
  }]
})
const barPlotlyLayout = computed(() => ({
  title: { text: '主题文档数排名', font: { size: 14, color: '#2d3748' }, x: 0.5 },
  xaxis: { title: '文档数量', tickfont: { size: 11 }, titlefont: { size: 12 } },
  yaxis: { tickfont: { size: 10 }, autorange: 'reversed' },
  margin: { l: 300, r: 50, t: 50, b: 50 },
  plot_bgcolor: 'rgba(255,255,255,.5)',
  paper_bgcolor: 'rgba(255,255,255,.7)',
  font: { family: 'Segoe UI, PingFang SC, Microsoft YaHei' }
}))
const barPlotlyConfig = {
  displayModeBar: true,
  modeBarButtonsToRemove: ['pan2d', 'lasso2d', 'select2d'],
  displaylogo: false,
  responsive: true
}

// Plotly 环形图配置（对照模板 - 使用LLM再聚类后的新主题）
const donutPlotlyHasData = computed(() => {
  const dataSource = llmClusters.value.length > 0 ? llmClusters.value : topTopics.value
  return dataSource.length > 0
})
const donutPlotlyData = computed(() => {
  const dataSource = llmClusters.value.length > 0 ? llmClusters.value : topTopics.value
  if (!dataSource.length) return []
  
  const docCounts = dataSource.map(item => llmClusters.value.length > 0 ? item.count : item.docCount)
  const totalDocs = docCounts.reduce((a, b) => a + b, 0)
  const colors = ['#4361ee', '#3a0ca3', '#7209b7', '#f72585', '#4cc9f0', '#4895ef', '#560bad']
  
  return [{
    values: docCounts,
    labels: dataSource.map(item => {
      if (llmClusters.value.length > 0) {
        return `${item.name}\n${item.title}`
      } else {
        const llmInfo = originalTopicToLLMName.value[item.name]
        const label = llmInfo?.title || item.name
        return `${item.name}\n${label}`
      }
    }),
    type: 'pie',
    hole: 0.6,
    marker: {
      colors: dataSource.map((_, i) => colors[i % colors.length]),
      line: { color: 'rgba(255,255,255,.8)', width: 2 }
    },
    textinfo: 'label+percent',
    textposition: 'outside',
    hovertemplate: '<b>%{label}</b><br>文档数: %{value}<br>占比: %{percent}<extra></extra>',
    insidetextorientation: 'radial'
  }]
})
const donutPlotlyLayout = computed(() => {
  const dataSource = llmClusters.value.length > 0 ? llmClusters.value : topTopics.value
  const totalDocs = dataSource.reduce((sum, item) => {
    return sum + (llmClusters.value.length > 0 ? item.count : item.docCount)
  }, 0)
  return {
    title: { text: '主题占比分布', font: { size: 14, color: '#2d3748' }, x: 0.5 },
    annotations: [
      { font: { size: 16, color: '#4a5568' }, showarrow: false, text: '总文档数', x: 0.5, y: 0.55 },
      { font: { size: 24, color: '#4361ee', weight: 'bold' }, showarrow: false, text: totalDocs.toLocaleString(), x: 0.5, y: 0.45 }
    ],
    showlegend: false,
    margin: { l: 50, r: 50, t: 50, b: 50 },
    plot_bgcolor: 'rgba(255,255,255,.5)',
    paper_bgcolor: 'rgba(255,255,255,.7)',
    font: { family: 'Segoe UI, PingFang SC, Microsoft YaHei' }
  }
})
const donutPlotlyConfig = {
  displayModeBar: true,
  modeBarButtonsToRemove: ['pan2d', 'lasso2d', 'select2d'],
  displaylogo: false,
  responsive: true
}

// Plotly 桑基图配置（对照模板）
const sankeyPlotlyHasData = computed(() => llmClusters.value.length > 0)
const sankeyPlotlyData = computed(() => {
  if (!llmClusters.value.length) return []
  
  const nodes = []
  const links = []
  const nodeSet = new Set()
  const nodeIndexMap = {}
  
  // 构建节点和链接
  llmClusters.value.forEach((cluster) => {
    const targetName = cluster.name || cluster.title
    if (!nodeSet.has(targetName)) {
      nodeSet.add(targetName)
      nodeIndexMap[targetName] = nodes.length
      nodes.push({ name: targetName })
    }
    
    cluster.original.forEach((origTopic) => {
      if (!nodeSet.has(origTopic)) {
        nodeSet.add(origTopic)
        nodeIndexMap[origTopic] = nodes.length
        nodes.push({ name: origTopic })
      }
      
      const value = topicDocMap.value[origTopic] || Math.max(1, Math.round((cluster.count || 1) / (cluster.original.length || 1)))
      links.push({
        source: nodeIndexMap[origTopic],
        target: nodeIndexMap[targetName],
        value: value
      })
    })
  })
  
  if (!links.length) return []
  
  // 生成节点标签
  const getNodeLabel = (nodeName) => {
    if (nodeName.startsWith('主题') && !nodeName.startsWith('新主题')) {
      const kw = getOriginalTopicKeywords(nodeName)
      return kw ? `${nodeName}\n${kw}` : nodeName
    }
    const cluster = llmClusters.value.find(c => (c.name || c.title) === nodeName)
    if (cluster) {
      return `${nodeName}\n${cluster.title || nodeName}`
    }
    return nodeName
  }
  
  const colors = ['#4361ee', '#3a0ca3', '#7209b7', '#f72585', '#4cc9f0', '#4895ef', '#560bad', '#b5179e', '#3f37c9', '#4ade80', '#16a34a', '#f59e0b', '#ef4444']
  const nodeColors = {}
  nodes.forEach((n, idx) => {
    nodeColors[n.name] = colors[idx % colors.length]
  })
  
  return [{
    type: 'sankey',
    orientation: 'h',
    node: {
      pad: 15,
      thickness: 20,
      line: { color: 'rgba(255,255,255,.8)', width: 1 },
      label: nodes.map(n => getNodeLabel(n.name)),
      color: nodes.map(n => nodeColors[n.name])
    },
    link: {
      source: links.map(l => l.source),
      target: links.map(l => l.target),
      value: links.map(l => l.value),
      color: links.map(l => {
        const sourceNode = nodes[l.source]
        const color = nodeColors[sourceNode.name] || '#4361ee'
        return color.replace('rgb', 'rgba').replace(')', ', 0.3)')
      })
    },
    textfont: { family: 'Segoe UI, PingFang SC, Microsoft YaHei', size: 11 }
  }]
})
const sankeyPlotlyLayout = computed(() => ({
  title: { text: '主题合并流向图', font: { size: 14, color: '#2d3748' }, x: 0.5 },
  font: { family: 'Segoe UI, PingFang SC, Microsoft YaHei', size: 12 },
  margin: { l: 50, r: 50, t: 50, b: 50 },
  plot_bgcolor: 'rgba(255,255,255,.5)',
  paper_bgcolor: 'rgba(255,255,255,.7)'
}))
const sankeyPlotlyConfig = {
  displayModeBar: true,
  displaylogo: false,
  responsive: true
}

// UMAP 原始数据
const umapRawData = ref([])

// 降采样函数
const downsample = (points, limit) => {
  if (points.length <= limit) return points
  const step = Math.ceil(points.length / limit)
  const out = []
  for (let i = 0; i < points.length; i += step) out.push(points[i])
  return out
}

// 计算热力图数据
const computeHeatmap = (points, bins = 80) => {
  if (!points.length) return { data: [], min: 0, max: 1, extent: [[0, 0], [1, 1]] }
  let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity
  points.forEach(d => {
    if (d.x < minX) minX = d.x
    if (d.x > maxX) maxX = d.x
    if (d.y < minY) minY = d.y
    if (d.y > maxY) maxY = d.y
  })
  const w = bins, h = bins
  const grid = Array.from({ length: w * h }, () => 0)
  points.forEach(d => {
    const ix = Math.min(w - 1, Math.max(0, Math.floor((d.x - minX) / (maxX - minX || 1) * w)))
    const iy = Math.min(h - 1, Math.max(0, Math.floor((d.y - minY) / (maxY - minY || 1) * h)))
    grid[iy * w + ix] += 1
  })
  const data = []
  let gmax = 0
  for (let iy = 0; iy < h; iy++) {
    for (let ix = 0; ix < w; ix++) {
      const v = grid[iy * w + ix]
      if (v <= 0) continue
      gmax = Math.max(gmax, v)
      const rx = minX + (ix + 0.5) * (maxX - minX) / w
      const ry = minY + (iy + 0.5) * (maxY - minY) / h
      data.push([rx, ry, v])
    }
  }
  return { data, min: 0, max: gmax, extent: [[minX, maxX], [minY, maxY]] }
}

// UMAP 2D 散点图配置（对照模板）
const coordsOption = computed(() => {
  let coords = []
  const coordsData = results.value.coords || results.value.coords_data || {}
  
  if (Array.isArray(coordsData)) {
    coords = coordsData
  } else if (coordsData['文档2D坐标']) {
    coords = coordsData['文档2D坐标']
  } else if (coordsData['coords']) {
    coords = coordsData['coords']
  } else if (coordsData['data']) {
    coords = coordsData['data']
  }
  
  if (!Array.isArray(coords) || !coords.length) {
    return { hasData: false, option: null }
  }
  
  // 过滤噪声点并初始化原始数据
  const filteredCoords = coords.filter(d => {
    const topicId = String(d.topic_id || d.topic_id)
    return topicId !== '-1' && topicId !== '-1'
  })
  
  if (!filteredCoords.length) {
    return { hasData: false, option: null }
  }
  
  // 保存原始数据
  umapRawData.value = filteredCoords.map(d => ({
    doc_id: d.doc_id,
    topic_id: String(d.topic_id),
    x: Number(d.x),
    y: Number(d.y)
  })).filter(d => Number.isFinite(d.x) && Number.isFinite(d.y))
  
  // 更新可用主题列表
  const uniqueTopics = [...new Set(umapRawData.value.map(d => d.topic_id))].sort((a, b) => Number(a) - Number(b))
  if (availableTopics.value.length === 0 || JSON.stringify(availableTopics.value) !== JSON.stringify(uniqueTopics)) {
    availableTopics.value = uniqueTopics
    if (umapControls.selectedTopics.length === 0) {
      umapControls.selectedTopics = [...uniqueTopics]
    }
  }
  
  // 根据选中的主题筛选
  const activeTopics = new Set(umapControls.selectedTopics.length > 0 ? umapControls.selectedTopics : uniqueTopics)
  let pts = umapRawData.value.filter(d => activeTopics.has(d.topic_id))
  
  // 降采样或密度视图
  const sampled = umapControls.density ? pts : downsample(pts, Math.max(1000, umapControls.maxPoints))
  
  const topics = [...new Set(sampled.map(d => d.topic_id))].sort((a, b) => Number(a) - Number(b))
  const palette = ['#5ad8a6', '#6ad1ff', '#ffb36b', '#c38bff', '#ff8f6b', '#78a3ff', '#28c197', '#8bd3ff', '#ffd666', '#95de64', '#ff85c0', '#ffa39e']
  const colorMap = {}
  topics.forEach((t, i) => {
    colorMap[t] = palette[i % palette.length]
  })
  
  const tooltip = {
    formatter: (p) => {
      const d = p.value
      return `${p.marker} doc_id: <b>${d[3]}</b><br/>topic_id: <b>${d[2]}</b><br/>(x,y)=(${d[0].toFixed(4)}, ${d[1].toFixed(4)})`
    },
    backgroundColor: 'rgba(14,24,52,.9)',
    borderColor: '#2a3a63',
    textStyle: { color: '#eaf2ff' }
  }
  
  const series = []
  
  if (umapControls.density) {
    // 密度视图 - 使用scatter + visualMap实现，因为heatmap在连续坐标中可能不稳定
    const heat = computeHeatmap(pts, 100)
    
    // 检查数据是否为空
    if (!heat.data || heat.data.length === 0) {
      console.warn('[UMAP密度视图] 热力图数据为空，pts数量:', pts.length)
      return { hasData: false, option: null }
    }
    
    // 将热力图数据转换为scatter格式 [x, y, value]
    const scatterData = heat.data.map(d => [d[0], d[1], d[2]])
    
    // 计算点的大小，基于数据范围
    const xRange = heat.extent[0]
    const yRange = heat.extent[1]
    const xSpan = xRange[1] - xRange[0]
    const ySpan = yRange[1] - yRange[0]
    const avgSpan = (xSpan + ySpan) / 2
    // 根据数据范围动态计算点大小
    const baseSize = Math.max(8, Math.min(40, avgSpan / 15))
    
    series.push({
      type: 'scatter',
      name: '密度',
      data: scatterData,
      symbolSize: (val) => {
        // 根据密度值调整点大小
        const density = val[2]
        const maxDensity = heat.max || 1
        return baseSize * (0.5 + 0.5 * (density / maxDensity))
      },
      itemStyle: {
        opacity: 0.7,
        borderWidth: 0
      },
      emphasis: {
        itemStyle: {
          opacity: 1
        }
      }
    })
    return {
      hasData: true,
      option: {
        backgroundColor: 'transparent',
        title: {
          text: 'UMAP 2D · 密度视图',
          left: 'center',
          top: 6,
          textStyle: { color: '#2d3748', fontSize: 16, fontWeight: 800 }
        },
        grid: { left: 60, right: 80, top: 40, bottom: 50, containLabel: true },
        toolbox: {
          show: true,
          right: 30,
          top: 10,
          feature: {
            brush: {
              type: ['rect', 'clear']
            }
          },
          iconStyle: {
            borderColor: '#4361ee'
          },
          emphasis: {
            iconStyle: {
              borderColor: '#3a0ca3'
            }
          }
        },
        tooltip: {
          formatter: (p) => {
            const d = p.value
            return `${p.marker} 位置: (${d[0].toFixed(4)}, ${d[1].toFixed(4)})<br/>密度值: <b>${d[2]}</b>`
          },
          backgroundColor: 'rgba(14,24,52,.9)',
          borderColor: '#2a3a63',
          textStyle: { color: '#eaf2ff' }
        },
        xAxis: {
          type: 'value',
          axisLabel: { color: '#4a5568' },
          axisLine: { lineStyle: { color: '#cbd5e0' } },
          splitLine: { lineStyle: { color: '#e2e8f0' } }
        },
        yAxis: {
          type: 'value',
          axisLabel: { color: '#4a5568' },
          axisLine: { lineStyle: { color: '#cbd5e0' } },
          splitLine: { lineStyle: { color: '#e2e8f0' } }
        },
        visualMap: {
          min: 0,
          max: heat.max || 1,
          calculable: true,
          orient: 'vertical',
          right: 20,
          top: 'center',
          textStyle: { color: '#4a5568' },
          inRange: { 
            color: ['#e2e8f0', '#4361ee', '#6ad1ff']
          },
          dimension: 2,  // 使用数据的第3个维度（value，即密度值）进行颜色映射
          seriesIndex: 0
        },
        dataZoom: [
          { type: 'inside', xAxisIndex: 0 },
          { type: 'inside', yAxisIndex: 0 },
          { type: 'slider', xAxisIndex: 0, bottom: 6, height: 20, textStyle: { color: '#4a5568' } },
          { type: 'slider', yAxisIndex: 0, right: 6, width: 20, textStyle: { color: '#4a5568' } }
        ],
        brush: {
          toolbox: ['rect', 'clear'],
          xAxisIndex: [0],
          yAxisIndex: [0],
          brushMode: 'single',
          brushType: 'rect',
          transformable: false,
          brushStyle: {
            borderWidth: 1,
            color: 'rgba(67, 97, 238, 0.2)',
            borderColor: 'rgba(67, 97, 238, 0.8)'
          },
          throttleType: 'debounce',
          throttleDelay: 0,
          removeOnClick: false,
          seriesIndex: 'all',
          inBrush: {
            opacity: 1
          },
          outOfBrush: {
            opacity: 0.3
          }
        },
        series
      }
    }
  }
  
  // 散点视图
  topics.forEach(t => {
    const arr = sampled.filter(d => d.topic_id === t)
    series.push({
      name: `主题 ${t}`,
      type: 'scatter',
      large: true,
      largeThreshold: 2000,
      progressive: 2000,
      symbolSize: 4,
      itemStyle: { color: colorMap[t], opacity: 0.85, borderWidth: 0 },
      emphasis: { focus: 'series', itemStyle: { shadowBlur: 10, shadowColor: `${colorMap[t]}80` } },
      data: arr.map(d => [d.x, d.y, d.topic_id, d.doc_id])
    })
  })
  
  return {
    hasData: true,
    option: {
      backgroundColor: 'transparent',
      title: {
        text: 'UMAP 2D · 文档散点',
        left: 'center',
        top: 6,
        textStyle: { color: '#2d3748', fontSize: 16, fontWeight: 800 }
      },
      grid: { left: 60, right: 20, top: 40, bottom: 50, containLabel: true },
      toolbox: {
        show: true,
        right: 30,
        top: 10,
        feature: {
          brush: {
            type: ['rect', 'clear']
          }
        },
        iconStyle: {
          borderColor: '#4361ee'
        },
        emphasis: {
          iconStyle: {
            borderColor: '#3a0ca3'
          }
        }
      },
      tooltip: tooltip,
      legend: {
        type: 'scroll',
        top: 34,
        textStyle: { color: '#2d3748' },
        data: topics.map(t => `主题 ${t}`),
        pageIconColor: '#4361ee',
        pageTextStyle: { color: '#718096' }
      },
      xAxis: {
        type: 'value',
        name: 'UMAP-1',
        axisLabel: { color: '#4a5568' },
        axisLine: { lineStyle: { color: '#cbd5e0' } },
        splitLine: { lineStyle: { color: '#e2e8f0' } }
      },
      yAxis: {
        type: 'value',
        name: 'UMAP-2',
        axisLabel: { color: '#4a5568' },
        axisLine: { lineStyle: { color: '#cbd5e0' } },
        splitLine: { lineStyle: { color: '#e2e8f0' } }
      },
      dataZoom: [
        { type: 'inside', xAxisIndex: 0 },
        { type: 'inside', yAxisIndex: 0 },
        { type: 'slider', xAxisIndex: 0, bottom: 6, height: 20, textStyle: { color: '#4a5568' } },
        { type: 'slider', yAxisIndex: 0, right: 6, width: 20, textStyle: { color: '#4a5568' } }
      ],
      brush: {
        toolbox: ['rect', 'clear'],
        xAxisIndex: [0],
        yAxisIndex: [0],
        brushMode: 'single',
        brushType: 'rect',
        transformable: false,
        brushStyle: {
          borderWidth: 1,
          color: 'rgba(67, 97, 238, 0.2)',
          borderColor: 'rgba(67, 97, 238, 0.8)'
        },
        throttleType: 'debounce',
        throttleDelay: 0,
        removeOnClick: false,
        seriesIndex: 'all',
        inBrush: {
          opacity: 1
        },
        outOfBrush: {
          opacity: 0.3
        }
      },
      series
    }
  }
})

const updateUMAPChart = () => {
  // 触发重新计算
  coordsOption.value
}

const downloadSelectedDocIds = () => {
  const ids = Array.from(new Set(selectedDocIds.value)).sort((a, b) => a - b)
  const blob = new Blob([ids.join('\n')], { type: 'text/plain;charset=utf-8' })
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = 'selected_doc_ids.txt'
  a.click()
  URL.revokeObjectURL(a.href)
}

const exportData = () => {
  if (!bertopicData.value) {
    alert('暂无数据可导出')
    return
  }

  const exportData = {
    metadata: {
      topic: viewSelection.topic,
      start_date: viewSelection.start,
      end_date: viewSelection.end,
      export_time: new Date().toISOString()
    },
    statistics: {
      original_topics_count: docStats.value.topicCount,
      llm_topics_count: llmStats.value.count,
      total_documents: llmStats.value.totalDocs,
      max_topic_docs: llmStats.value.maxDocs
    },
    original_topics: summaryEntries.value.entries.map(topic => ({
      name: topic.name,
      doc_count: topic.docCount,
      ratio: topic.ratio,
      keywords: topic.keywords.map(kw => ({ word: kw[0], weight: kw[1] }))
    })),
    llm_clusters: llmClusters.value.map(cluster => ({
      name: cluster.name,
      title: cluster.title,
      description: cluster.description,
      doc_count: cluster.count,
      original_topics: cluster.original,
      keywords: cluster.keywords.map(kw =>
        Array.isArray(kw) ? { word: kw[0], weight: kw[1] } : { word: kw, weight: 0 }
      )
    }))
  }

  const blob = new Blob([JSON.stringify(exportData, null, 2)], { type: 'application/json;charset=utf-8' })
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = `bertopic_results_${viewSelection.topic}_${viewSelection.start}${viewSelection.end ? `_${viewSelection.end}` : ''}.json`
  a.click()
  URL.revokeObjectURL(a.href)
}

// 监听UMAP图表实例，添加框选事件
watch(
  () => [coordsOption.value.hasData, coordsOption.value.option],
  async ([hasData, option]) => {
    if (hasData && option && umapChartRef.value) {
      // 等待DOM更新和图表渲染完成
      await nextTick()
      await new Promise(resolve => setTimeout(resolve, 100)) // 额外等待确保图表已渲染
      
      const chartEl = umapChartRef.value.$el?.querySelector('.analysis-chart-card__canvas')
      if (chartEl) {
        umapChartInstance = echarts.getInstanceByDom(chartEl)
        if (umapChartInstance) {
          // 移除旧的事件监听
          umapChartInstance.off('brushSelected')
          // 添加新的事件监听
          umapChartInstance.on('brushSelected', (params) => {
            console.log('[Brush] brushSelected事件触发:', params)
            const brushed = params.batch && params.batch[0]
            selectedDocIds.value = []
            if (brushed && brushed.selected) {
              brushed.selected.forEach(sel => {
                const s = umapChartInstance.getOption().series[sel.seriesIndex]
                if (s && s.data) {
                  // 检查是否是密度视图（数据格式为 [x, y, density_value]）
                  const isDensityView = s.type === 'scatter' && s.data.length > 0 && Array.isArray(s.data[0]) && s.data[0].length === 3
                  
                  if (isDensityView) {
                    // 密度视图：根据选中的数据点的坐标范围，从原始数据中筛选
                    const selectedPoints = (sel.dataIndex || []).map(idx => s.data[idx]).filter(p => p && Array.isArray(p))
                    if (selectedPoints.length > 0) {
                      // 计算选中点的坐标范围
                      let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity
                      selectedPoints.forEach(p => {
                        if (p[0] < minX) minX = p[0]
                        if (p[0] > maxX) maxX = p[0]
                        if (p[1] < minY) minY = p[1]
                        if (p[1] > maxY) maxY = p[1]
                      })
                      // 计算原始数据的范围，用于估算网格大小
                      if (umapRawData.value.length > 0) {
                        const allX = umapRawData.value.map(d => d.x)
                        const allY = umapRawData.value.map(d => d.y)
                        const xSpan = Math.max(...allX) - Math.min(...allX)
                        const ySpan = Math.max(...allY) - Math.min(...allY)
                        const binSize = 100 // 与computeHeatmap中的bins一致
                        // 每个网格的大小约为 span/bins，添加1.5倍容差
                        const xTolerance = (xSpan / binSize) * 1.5
                        const yTolerance = (ySpan / binSize) * 1.5
                        
                        // 从原始数据中筛选在范围内的点
                        umapRawData.value.forEach(d => {
                          if (d.x >= (minX - xTolerance) && d.x <= (maxX + xTolerance) && 
                              d.y >= (minY - yTolerance) && d.y <= (maxY + yTolerance)) {
                            selectedDocIds.value.push(d.doc_id)
                          }
                        })
                      }
                    }
                  } else {
                    // 散点视图：数据格式为 [x, y, topic_id, doc_id]
                    (sel.dataIndex || []).forEach(idx => {
                      const v = s.data[idx]
                      if (v && Array.isArray(v) && v.length >= 4 && v[3] !== undefined) {
                        selectedDocIds.value.push(v[3])
                      }
                    })
                  }
                }
              })
            }
            console.log('[Brush] 选中的doc_id数量:', selectedDocIds.value.length)
          })
          
          // 确保brush功能已启用并测试
          const currentOption = umapChartInstance.getOption()
          console.log('[Brush] 当前brush配置:', currentOption.brush)
          
          // 测试brush是否可用
          try {
            // 尝试手动触发brush测试
            const brushComponent = umapChartInstance.getModel().getComponent('brush', 0)
            console.log('[Brush] brush组件:', brushComponent)
          } catch (e) {
            console.warn('[Brush] 无法获取brush组件:', e)
          }
          
          // 监听所有可能的事件以调试
          umapChartInstance.on('brush', (params) => {
            console.log('[Brush] brush事件触发:', params)
          })
          umapChartInstance.on('brushEnd', (params) => {
            console.log('[Brush] brushEnd事件触发:', params)
            // brushEnd事件也可能包含选中信息
            if (params && params.areas) {
              console.log('[Brush] brushEnd包含areas:', params.areas)
            }
          })
          
          // 检查brush是否真的启用了
          console.log('[Brush] 图表配置:', {
            hasBrush: !!currentOption.brush,
            brushConfig: currentOption.brush,
            seriesCount: currentOption.series?.length
          })
        } else {
          console.warn('[Brush] 无法获取图表实例')
        }
      } else {
        console.warn('[Brush] 无法找到图表DOM元素')
      }
    }
  },
  { immediate: true, deep: true }
)

// canSubmit computed property is now handled inline in template

const updateTopN = (value) => {
  controls.topN = Math.max(3, Math.min(Number(value) || 7, Math.max(7, maxTopN.value)))
}
</script>

<style scoped>
.topic-dashboard__hero {
  border-radius: 24px;
  padding: 32px;
  background: linear-gradient(135deg, #9ab2cb 0%, #7f91a7 100%);
  color: white;
  box-shadow: 0 10px 30px rgba(122, 146, 176, 0.35);
}
.topic-dashboard__hero h1 {
  font-size: 2rem;
  font-weight: 700;
  margin-bottom: 0.5rem;
}
.topic-dashboard__hero p {
  max-width: 700px;
  font-size: 0.95rem;
}
.topic-dashboard__label {
  text-transform: uppercase;
  font-size: 0.75rem;
  letter-spacing: 0.2em;
  opacity: 0.8;
  margin-bottom: 0.5rem;
  display: inline-block;
}
.topic-dashboard__card {
  border-radius: 24px;
  border: 1px solid var(--color-border-soft);
  background: var(--color-surface);
  padding: 24px;
  box-shadow: 0 10px 25px rgba(22, 30, 52, 0.05);
}
.topic-dashboard__form {
  display: grid;
  gap: 16px;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
}

.topic-select-wrapper {
  grid-column: 1 / -1; /* 专题选择框占满整行 */
}
.topic-dashboard__form label {
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-size: 0.9rem;
  color: var(--color-text-secondary);
}
.topic-dashboard__form input {
  padding: 10px 12px;
  border-radius: 16px;
  border: 1px solid var(--color-border-soft);
  background: var(--color-surface);
  font-size: 0.95rem;
}

.topic-select-wrapper {
  position: relative;
  grid-column: 1 / -1; /* 专题选择框占满整行 */
}

.topic-select-container {
  position: relative;
  display: flex;
  align-items: center;
}

.topic-select {
  flex: 1;
  padding: 10px 40px 10px 12px;
  border-radius: 16px;
  border: 1px solid var(--color-border-soft);
  background: var(--color-surface);
  font-size: 0.95rem;
  appearance: none;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12'%3E%3Cpath fill='%23666' d='M6 9L1 4h10z'/%3E%3C/svg%3E");
  background-repeat: no-repeat;
  background-position: right 12px center;
}

.topic-select:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.btn-refresh {
  position: absolute;
  right: 32px;
  top: 50%;
  transform: translateY(-50%);
  background: transparent;
  border: none;
  cursor: pointer;
  padding: 4px 8px;
  font-size: 1rem;
  color: var(--color-text-secondary);
  transition: color 0.2s ease;
  z-index: 1;
  line-height: 1;
}

.btn-refresh:hover {
  color: var(--color-text-primary);
}

.loading-indicator {
  position: absolute;
  right: 12px;
  top: 50%;
  transform: translateY(-50%);
  font-size: 0.85rem;
  color: var(--color-text-secondary);
}
.topic-dashboard__form-actions {
  grid-column: 1 / -1;
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
}
.topic-dashboard__error {
  margin-top: 16px;
  padding: 12px 16px;
  border-radius: 12px;
  border: 1px solid #fecaca;
  background: #fef2f2;
  color: #991b1b;
  font-size: 0.9rem;
}
.dashboard-controls {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 16px;
}
.dashboard-controls label {
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-size: 0.85rem;
  color: var(--color-text-secondary);
}
.dashboard-controls input,
.dashboard-controls select {
  padding: 9px 12px;
  border-radius: 14px;
  border: 1px solid var(--color-border-soft);
}
.topic-dashboard__range .range-input {
  display: flex;
  align-items: center;
  gap: 12px;
}
.dashboard-overview {
  margin-bottom: 2rem;
}

.overview-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 1.25rem;
  padding-bottom: 1rem;
  border-bottom: 2px solid var(--color-border-soft);
}

.overview-header__title {
  font-size: 1.125rem;
  font-weight: 600;
  color: var(--color-text-primary);
  margin: 0;
}

.overview-actions {
  display: flex;
  gap: 0.75rem;
}

.btn-export {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem 1rem;
  border-radius: 0.5rem;
  border: 1px solid var(--color-border-soft);
  background: var(--color-surface);
  color: var(--color-text-primary);
  font-size: 0.875rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s ease;
}

.btn-export:hover {
  background: rgba(67, 97, 238, 0.1);
  border-color: #4361ee;
  color: #4361ee;
}

.dashboard-stats {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 1rem;
}

.stat-card {
  display: flex;
  align-items: flex-start;
  gap: 1rem;
  background: rgba(255, 255, 255, 0.9);
  backdrop-filter: blur(5px);
  border-radius: 0.75rem;
  padding: 1.25rem;
  border-left: 4px solid #4361ee;
  transition: all 0.3s ease;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.05);
}

.stat-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
}

.stat-card--primary {
  border-left-color: #4361ee;
}

.stat-card--success {
  border-left-color: #10b981;
}

.stat-card--info {
  border-left-color: #3b82f6;
}

.stat-card--warning {
  border-left-color: #f59e0b;
}

.stat-card__icon {
  font-size: 1.75rem;
  line-height: 1;
  flex-shrink: 0;
}

.stat-card__content {
  flex: 1;
  min-width: 0;
}

.stat-card__value {
  font-size: 1.75rem;
  font-weight: 700;
  color: #4361ee;
  margin: 0 0 0.25rem 0;
  line-height: 1.2;
}

.stat-card--success .stat-card__value {
  color: #10b981;
}

.stat-card--info .stat-card__value {
  color: #3b82f6;
}

.stat-card--warning .stat-card__value {
  color: #f59e0b;
}

.stat-card__label {
  font-size: 0.875rem;
  font-weight: 500;
  color: var(--color-text-primary);
  margin: 0 0 0.25rem 0;
}

.stat-card__subtext {
  font-size: 0.75rem;
  color: var(--color-text-secondary);
  margin: 0;
}
.topic-dashboard__chart-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 20px;
}
.chart-panel--tall :deep(.analysis-chart-card__canvas) {
  height: 520px;
}
:deep(.analysis-chart-card__canvas) {
  min-height: 280px;
}
.topic-dashboard__section-header h2 {
  font-size: 1.2rem;
  font-weight: 600;
  margin-bottom: 4px;
}
.topic-dashboard__keywords-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
  gap: 16px;
}
.keyword-card {
  border-radius: 18px;
  border: 1px solid var(--color-border-soft);
  background: var(--color-surface-muted);
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.keyword-card__header {
  display: flex;
  justify-content: space-between;
  gap: 10px;
}
.keyword-card__label {
  font-size: 0.75rem;
  color: var(--color-text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}
.keyword-card__title {
  font-size: 1rem;
  font-weight: 600;
}
.keyword-card__badge {
  background: var(--color-border-soft);
  color: var(--color-text-primary);
  padding: 4px 10px;
  border-radius: 999px;
  font-size: 0.75rem;
}
.keyword-card__chips {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.keyword-card__chips span {
  background: var(--color-surface);
  border-radius: 999px;
  padding: 4px 10px;
  font-size: 0.75rem;
  color: var(--color-text-secondary);
  border: 1px solid var(--color-border-soft);
}
.llm-card {
  border-radius: 18px;
  border: 1px solid var(--color-border-soft);
  background: var(--color-surface-muted);
  padding: 18px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.llm-card__header {
  display: flex;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
}
.llm-card__label {
  font-size: 0.75rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--color-text-secondary);
}
.llm-card__title {
  font-size: 1rem;
  font-weight: 600;
}
.llm-card__meta {
  display: flex;
  gap: 12px;
  font-size: 0.8rem;
  color: var(--color-text-secondary);
}
.llm-card__desc {
  font-size: 0.9rem;
  color: var(--color-text-secondary);
}
.topic-dashboard__empty {
  text-align: center;
  color: var(--color-text-secondary);
  font-size: 0.95rem;
}
.btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 10px 18px;
  border-radius: 999px;
  font-size: 0.95rem;
  font-weight: 600;
  border: none;
  cursor: pointer;
  transition: background 0.2s ease;
}
.btn-primary {
  background: #9ab2cb;
  color: white;
}
.btn-primary:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
.btn-soft {
  background: var(--color-surface-muted);
  color: var(--color-text-primary);
  border: 1px solid var(--color-border-soft);
}

.input {
  width: 100%;
  border-radius: 0.75rem;
  border: 1px solid var(--color-border-soft);
  background-color: var(--color-surface);
  padding: 0.5rem 0.85rem;
  font-size: 0.95rem;
  transition: border-color 0.2s ease, box-shadow 0.2s ease;
}
.input:focus {
  border-color: var(--color-brand-500-hex);
  outline: none;
  box-shadow: 0 0 0 2px rgb(var(--color-brand-100) / 1);
}
.input:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
.relative .input {
  padding-right: 2.5rem;
}

/* UMAP 控制样式 */
.umap-section {
  padding: 18px;
}

.umap-controls {
  margin-bottom: 14px;
}

.umap-control-row {
  display: flex;
  gap: 12px;
  align-items: center;
  flex-wrap: wrap;
  margin-bottom: 14px;
}

.umap-control-row:last-child {
  margin-bottom: 0;
}

.umap-control-row label {
  font-size: 14px;
  color: var(--color-text-primary);
}

.umap-control-row input[type="checkbox"] {
  width: 16px;
  height: 16px;
  accent-color: #4361ee;
}

.umap-control-row input[type="number"] {
  width: 100px;
  padding: 8px 10px;
  border-radius: 8px;
  border: 1px solid var(--color-border-soft);
}

.umap-control-row button {
  padding: 8px 16px;
  border-radius: 8px;
  border: none;
  background: linear-gradient(135deg, #4361ee 0%, #3a0ca3 100%);
  color: white;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.3s;
}

.umap-control-row button:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(67, 97, 238, 0.4);
}

.umap-selected-info {
  font-weight: 600;
  color: #4361ee;
  padding: 6px 12px;
  background: rgba(110, 163, 255, 0.1);
  border-radius: 8px;
  font-size: 14px;
}

.umap-topics-box {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  max-height: 140px;
  overflow: auto;
  padding: 10px;
  border: 1px solid var(--color-border-soft);
  border-radius: 10px;
  background: var(--color-surface-muted);
  scrollbar-width: thin;
  scrollbar-color: #4361ee transparent;
}

.umap-topics-box::-webkit-scrollbar {
  width: 8px;
  height: 8px;
}

.umap-topics-box::-webkit-scrollbar-thumb {
  background: #4361ee;
  border-radius: 4px;
}

.umap-topics-box::-webkit-scrollbar-track {
  background: transparent;
}

.umap-topic-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  background: rgba(67, 97, 238, 0.15);
  border-radius: 8px;
  border: 1px solid rgba(67, 97, 238, 0.3);
  transition: all 0.2s ease;
}

.umap-topic-item:hover {
  background: rgba(67, 97, 238, 0.25);
  border-color: #4361ee;
}

.umap-topic-item input[type="checkbox"] {
  margin: 0;
  width: 16px;
  height: 16px;
  accent-color: #4361ee;
}

.umap-topic-item span {
  font-weight: 500;
  color: var(--color-text-primary);
  font-size: 13px;
}

/* 新增样式：部分标题 */
.section-header {
  margin-bottom: 1.5rem;
  padding-bottom: 1rem;
  border-bottom: 2px solid var(--color-border-soft);
}

.section-header__title {
  font-size: 1.25rem;
  font-weight: 600;
  color: var(--color-text-primary);
  margin: 0 0 0.5rem 0;
}

.section-header__subtitle {
  font-size: 0.875rem;
  color: var(--color-text-secondary);
  margin: 0;
}

/* 关键词网格 */
.keywords-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 1rem;
}

.keyword-chip {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  background: var(--color-surface);
  border-radius: 0.5rem;
  padding: 0.375rem 0.75rem;
  font-size: 0.8125rem;
  color: var(--color-text-primary);
  border: 1px solid var(--color-border-soft);
  transition: all 0.2s ease;
}

.keyword-chip:hover {
  background: rgba(67, 97, 238, 0.1);
  border-color: #4361ee;
  transform: translateY(-1px);
}

.keyword-chip__weight {
  font-size: 0.75rem;
  color: var(--color-text-secondary);
  opacity: 0.7;
}

/* LLM 聚类结果网格 */
.llm-clusters-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(350px, 1fr));
  gap: 1.25rem;
}

.llm-cluster-card {
  border-radius: 1rem;
  border: 1px solid var(--color-border-soft);
  background: linear-gradient(135deg, rgba(67, 97, 238, 0.05) 0%, rgba(255, 255, 255, 0.9) 100%);
  padding: 1.25rem;
  transition: all 0.3s ease;
}

.llm-cluster-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 8px 20px rgba(67, 97, 238, 0.15);
  border-color: #4361ee;
}

.llm-cluster-card__header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 1rem;
  margin-bottom: 1rem;
}

.llm-cluster-card__title-group {
  flex: 1;
}

.llm-cluster-card__label {
  font-size: 0.75rem;
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--color-text-secondary);
  margin: 0 0 0.25rem 0;
}

.llm-cluster-card__title {
  font-size: 1.125rem;
  font-weight: 600;
  color: var(--color-text-primary);
  margin: 0;
  line-height: 1.4;
}

.llm-cluster-card__badge {
  background: linear-gradient(135deg, #4361ee 0%, #3a0ca3 100%);
  color: white;
  padding: 0.375rem 0.875rem;
  border-radius: 999px;
  font-size: 0.8125rem;
  font-weight: 600;
  white-space: nowrap;
  flex-shrink: 0;
}

.llm-cluster-card__description {
  font-size: 0.875rem;
  color: var(--color-text-secondary);
  line-height: 1.6;
  margin: 0 0 1rem 0;
  padding: 0.75rem;
  background: rgba(255, 255, 255, 0.7);
  border-radius: 0.5rem;
  border-left: 3px solid #4361ee;
}

.llm-cluster-card__original,
.llm-cluster-card__keywords {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem;
  margin-top: 0.75rem;
  font-size: 0.8125rem;
}

.llm-cluster-card__original-label,
.llm-cluster-card__keywords-label {
  font-weight: 600;
  color: var(--color-text-secondary);
  flex-shrink: 0;
}

.llm-cluster-card__original-tag {
  background: rgba(67, 97, 238, 0.15);
  color: #4361ee;
  padding: 0.25rem 0.625rem;
  border-radius: 0.375rem;
  font-weight: 500;
  border: 1px solid rgba(67, 97, 238, 0.3);
}

.llm-cluster-card__keyword-tag {
  background: var(--color-surface);
  color: var(--color-text-primary);
  padding: 0.25rem 0.625rem;
  border-radius: 0.375rem;
  border: 1px solid var(--color-border-soft);
  transition: all 0.2s ease;
}

.llm-cluster-card__keyword-tag:hover {
  background: rgba(67, 97, 238, 0.1);
  border-color: #4361ee;
}

/* 统计表格 */
.table-container {
  overflow-x: auto;
  border-radius: 0.75rem;
  border: 1px solid var(--color-border-soft);
}

.stats-table {
  width: 100%;
  border-collapse: collapse;
  background: var(--color-surface);
}

.stats-table thead {
  background: linear-gradient(135deg, rgba(67, 97, 238, 0.1) 0%, rgba(67, 97, 238, 0.05) 100%);
}

.stats-table th {
  padding: 1rem;
  text-align: left;
  font-size: 0.875rem;
  font-weight: 600;
  color: var(--color-text-primary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  border-bottom: 2px solid var(--color-border-soft);
}

.stats-table th:first-child {
  border-top-left-radius: 0.75rem;
}

.stats-table th:last-child {
  border-top-right-radius: 0.75rem;
}

.stats-table__row {
  transition: background 0.2s ease;
}

.stats-table__row:hover {
  background: rgba(67, 97, 238, 0.05);
}

.stats-table__row td {
  padding: 0.875rem 1rem;
  font-size: 0.875rem;
  color: var(--color-text-primary);
  border-bottom: 1px solid var(--color-border-soft);
}

.stats-table__topic-name {
  font-weight: 600;
  color: #4361ee;
}

.stats-table__doc-count {
  font-weight: 600;
  color: var(--color-text-primary);
}

.stats-table__ratio {
  color: var(--color-text-secondary);
}

.stats-table__keywords {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}

.stats-table__keyword {
  background: var(--color-surface-muted);
  padding: 0.25rem 0.5rem;
  border-radius: 0.375rem;
  font-size: 0.75rem;
  color: var(--color-text-secondary);
  border: 1px solid var(--color-border-soft);
}
</style>

