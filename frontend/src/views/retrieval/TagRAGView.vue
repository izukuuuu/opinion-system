<template>
  <div class="space-y-10">
    <!-- Header -->
    <section class="relative overflow-hidden rounded-3xl bg-gradient-to-br from-brand-500 to-brand-700 px-6 py-10 text-white sm:px-10">
      <div class="absolute inset-0 opacity-40">
        <div class="absolute -top-28 left-1/3 h-72 w-72 -translate-x-1/2 rounded-full bg-white/25 blur-3xl"></div>
        <div class="absolute bottom-0 right-10 h-56 w-56 rounded-full bg-brand-200/80 blur-3xl"></div>
      </div>
      <div class="relative space-y-6">
        <div class="space-y-4">
          <p class="text-sm font-semibold uppercase tracking-[0.4em] text-white/70">RAG 检索</p>
          <h1 class="text-3xl font-semibold sm:text-4xl">TagRAG 检索</h1>
        </div>

        <div class="space-y-4">
          <p class="text-sm text-white/90">
            基于标签向量的智能文档检索系统，通过语义相似度快速定位相关内容。
          </p>

          <div>
            <p class="mb-2 text-sm font-semibold text-white">功能特点</p>
            <p class="text-sm leading-relaxed text-white/80">
              支持语义搜索、相似度评分、结果导出等功能，帮助您快速从海量文档中找到所需信息。
            </p>
          </div>
        </div>
      </div>
    </section>

    <!-- Search Form -->
    <section class="card-surface space-y-6 p-6">
      <header class="space-y-2">
        <h2 class="text-2xl font-semibold text-primary">检索设置</h2>
        <p class="text-sm text-secondary">配置检索参数并执行搜索</p>
      </header>

      <form class="space-y-5 text-sm" @submit.prevent="handleSearch">
        <div class="grid gap-4 md:grid-cols-3">
          <!-- Query Input -->
          <div class="md:col-span-2 space-y-2">
            <label class="text-xs font-semibold text-muted">检索查询 *</label>
            <div class="relative">
              <input
                v-model="ragSearchForm.query"
                type="text"
                placeholder="输入要检索的关键词或句子..."
                class="input w-full"
                required
              />
              <svg class="absolute right-3 top-3 h-5 w-5 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
              </svg>
            </div>
          </div>

          <!-- Topic Selection -->
          <div class="space-y-2">
            <div class="flex items-center justify-between gap-2">
              <label class="text-xs font-semibold text-muted">选择专题 *</label>
              <div class="flex items-center gap-2">
                <button
                  type="button"
                  class="inline-flex items-center gap-1 text-[11px] font-medium text-brand-600 hover:text-brand-700 disabled:cursor-default disabled:opacity-60"
                  :disabled="ragTopicsState.loading"
                  @click="loadTopics"
                >
                  <ArrowPathIcon
                    class="h-3 w-3"
                    :class="ragTopicsState.loading ? 'animate-spin text-brand-600' : 'text-brand-600'"
                  />
                  <span>{{ ragTopicsState.loading ? '刷新中…' : '刷新专题' }}</span>
                </button>
                <button
                  type="button"
                  class="text-[11px] font-medium text-brand-600 hover:text-brand-700"
                  @click="toggleBuildPanel"
                >
                  生成检索库
                </button>
              </div>
            </div>
            <select
              v-model="ragSearchForm.topic"
              class="input"
              :disabled="ragTopicsState.loading || !tagragTopicOptions.length"
              required
            >
              <option value="" disabled>请选择专题</option>
              <option v-for="topic in tagragTopicOptions" :key="topic" :value="topic">
                {{ topic }}
              </option>
            </select>
            <p class="text-xs text-muted">
              <span v-if="ragTopicsState.loading">正在读取专题列表…</span>
              <span v-else-if="ragTopicsState.error" class="text-danger">{{ ragTopicsState.error }}</span>
              <span v-else>选择要检索的专题数据</span>
            </p>
            <div v-if="buildPanelVisible" class="rounded-xl border border-brand-100 bg-brand-50/50 p-4 text-xs text-muted">
              <div class="flex items-center justify-between gap-2">
                <span class="font-semibold text-brand-700">从远程专题生成本地检索库</span>
                <button
                  type="button"
                  class="inline-flex items-center gap-1 text-[11px] font-medium text-brand-600 hover:text-brand-700 disabled:cursor-default disabled:opacity-60"
                  :disabled="remoteTopicsState.loading"
                  @click="refreshRemoteTopics"
                >
                  <ArrowPathIcon
                    class="h-3 w-3"
                    :class="remoteTopicsState.loading ? 'animate-spin text-brand-600' : 'text-brand-600'"
                  />
                  <span>{{ remoteTopicsState.loading ? '刷新中…' : '刷新远程' }}</span>
                </button>
              </div>
              <div class="mt-3 grid gap-3 md:grid-cols-3">
                <select
                  v-model="ragBuildForm.topic"
                  class="input"
                  :disabled="remoteTopicsState.loading || !remoteTopicOptions.length"
                >
                  <option value="" disabled>请选择远程专题</option>
                  <option v-for="topic in remoteTopicOptions" :key="`tagrag-build-${topic}`" :value="topic">
                    {{ topic }}
                  </option>
                </select>
                <button
                  type="button"
                  class="btn-secondary"
                  :disabled="ragBuildState.loading || !ragBuildForm.topic"
                  @click="handleBuild"
                >
                  {{ ragBuildState.loading ? '准备中…' : '开始准备' }}
                </button>
              </div>
              <p class="mt-2">同步远程专题内容到当前项目，并建立本地检索索引。</p>
              <p v-if="remoteTopicsState.error" class="mt-1 text-danger">{{ remoteTopicsState.error }}</p>
              <p v-if="ragBuildState.error" class="mt-1 text-danger">{{ ragBuildState.error }}</p>
            </div>
          </div>
        </div>

        <!-- Advanced Options -->
        <details class="group">
          <summary class="cursor-pointer text-xs font-medium text-muted hover:text-primary">
            高级选项
          </summary>
          <div class="mt-4 grid gap-4 md:grid-cols-2">
            <div class="space-y-2">
              <label class="text-xs font-semibold text-muted">返回数量 (Top-K)</label>
              <input
                v-model.number="ragSearchForm.top_k"
                type="number"
                min="1"
                max="50"
                class="input"
              />
            </div>
            <div class="space-y-2">
              <label class="text-xs font-semibold text-muted">相似度阈值</label>
              <div class="flex items-center gap-3">
                <input
                  v-model.number="ragSearchForm.threshold"
                  type="range"
                  min="0"
                  max="1"
                  step="0.05"
                  class="flex-1"
                />
                <span class="w-12 text-xs font-medium text-primary">
                  {{ ragSearchForm.threshold.toFixed(2) }}
                </span>
              </div>
            </div>
          </div>
        </details>

        <!-- Error Message -->
        <p v-if="ragRetrievalState.error" class="rounded-xl border border-red-200 bg-red-50/70 p-4 text-sm text-red-700">
          {{ ragRetrievalState.error }}
        </p>

        <!-- Submit Button -->
        <div class="flex justify-between">
          <div class="flex items-center gap-4 text-xs text-muted">
            <span>TagRAG 向量检索</span>
          </div>
          <button
            type="submit"
            class="btn-primary"
            :disabled="ragRetrievalState.loading || !ragSearchForm.query || !ragSearchForm.topic"
          >
            {{ ragRetrievalState.loading ? '检索中…' : '开始检索' }}
          </button>
        </div>
      </form>
    </section>

    <!-- Results -->
    <section v-if="ragRetrievalState.results.length > 0" class="space-y-6">
      <header class="flex items-center justify-between">
        <div>
          <h2 class="text-2xl font-semibold text-primary">检索结果</h2>
          <p class="text-sm text-secondary">
            共找到 {{ ragRetrievalState.total }} 条相关文档
          </p>
        </div>
        <button
          @click="exportResults"
          class="btn-secondary"
        >
          导出结果
        </button>
      </header>

      <div class="space-y-4">
        <div
          v-for="(result, index) in ragRetrievalState.results"
          :key="index"
          class="card-surface group relative overflow-hidden"
        >
          <div class="p-6">
            <div class="mb-3 flex items-start justify-between">
              <div class="flex items-center gap-3">
                <span class="rounded-full bg-brand-soft px-3 py-1 text-xs font-semibold text-brand-600">
                  #{{ index + 1 }}
                </span>
                <span :class="getScoreClass(result.score)" class="rounded-full px-3 py-1 text-xs font-medium">
                  相似度: {{ (result.score * 100).toFixed(1) }}%
                </span>
              </div>
              <div class="flex items-center gap-2 opacity-0 transition-opacity group-hover:opacity-100">
                <button
                  @click="copyText(result.text)"
                  class="rounded-lg p-2 text-gray-400 hover:bg-gray-100 hover:text-gray-600"
                  title="复制文本"
                >
                  <svg class="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
                  </svg>
                </button>
              </div>
            </div>

            <div class="mb-3">
              <h3 class="font-medium text-primary mb-2">文档内容</h3>
              <p class="text-sm text-secondary leading-relaxed">{{ result.text }}</p>
            </div>

            <div v-if="result.metadata && Object.keys(result.metadata).length > 0" class="border-t pt-3">
              <details class="cursor-pointer">
                <summary class="text-xs font-medium text-muted">元数据信息</summary>
                <pre class="mt-2 overflow-x-auto text-xs text-muted">{{ JSON.stringify(result.metadata, null, 2) }}</pre>
              </details>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- No Results -->
    <section v-else-if="hasSearched && !ragRetrievalState.loading" class="card-surface">
      <div class="py-12 text-center">
        <svg class="mx-auto h-12 w-12 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9.172 16.172a4 4 0 015.656 0M9 10h.01M15 10h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
        <h3 class="mt-4 text-lg font-medium text-primary">未找到相关文档</h3>
        <p class="mt-2 text-sm text-secondary">请尝试调整查询关键词或降低相似度阈值</p>
      </div>
    </section>
    <RagCacheToast :state="ragCacheState" />
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { ArrowPathIcon } from '@heroicons/vue/24/outline'
import { useRAGTopics } from '../../composables/useRAGTopics'
import RagCacheToast from '../../components/rag/RagCacheToast.vue'

const {
  ragTopicsState,
  tagragTopicOptions,
  remoteTopicsState,
  remoteTopicOptions,
  ragSearchForm,
  ragRetrievalState,
  ragCacheState,
  ragBuildState,
  ragBuildForm,
  loadRAGTopics,
  loadRemoteTopics,
  buildRagTopic,
  retrieveTagRAG
} = useRAGTopics()

const hasSearched = computed(() => ragRetrievalState.error !== '' || ragRetrievalState.results.length > 0)
const showBuildPanel = ref(false)
const buildPanelVisible = computed(() => showBuildPanel.value || tagragTopicOptions.value.length === 0)

// Methods
const loadTopics = async () => {
  await loadRAGTopics()
}

const refreshRemoteTopics = async () => {
  await loadRemoteTopics()
}

const toggleBuildPanel = () => {
  showBuildPanel.value = !showBuildPanel.value
  if (showBuildPanel.value && !remoteTopicOptions.value.length) {
    loadRemoteTopics()
  }
}

const handleBuild = async () => {
  try {
    await buildRagTopic({ type: 'tagrag' })
  } catch (error) {
    // Error is already handled in the composable
  }
}

const handleSearch = async () => {
  if (!ragSearchForm.query || !ragSearchForm.topic) {
    ragRetrievalState.error = '请填写查询内容和选择专题'
    return
  }

  try {
    await retrieveTagRAG()
  } catch (error) {
    // Error is already handled in the composable
  }
}

const getScoreClass = (score) => {
  if (score >= 0.8) return 'bg-green-100 text-green-800'
  if (score >= 0.6) return 'bg-blue-100 text-blue-800'
  if (score >= 0.4) return 'bg-yellow-100 text-yellow-800'
  return 'bg-gray-100 text-gray-800'
}

const copyText = async (text) => {
  try {
    await navigator.clipboard.writeText(text)
    alert('已复制到剪贴板')
  } catch (error) {
    alert('复制失败')
  }
}

const exportResults = () => {
  const exportData = ragRetrievalState.results.map((result, index) => ({
    序号: index + 1,
    相似度: (result.score * 100).toFixed(2) + '%',
    内容: result.text,
    元数据: JSON.stringify(result.metadata)
  }))

  const csv = [
    Object.keys(exportData[0]).join(','),
    ...exportData.map(row => Object.values(row).map(v => `"${v}"`).join(','))
  ].join('\n')

  const blob = new Blob(['\ufeff' + csv], { type: 'text/csv;charset=utf-8;' })
  const link = document.createElement('a')
  link.href = URL.createObjectURL(blob)
  link.download = `tagrag_results_${Date.now()}.csv`
  link.click()
}

// Lifecycle
onMounted(() => {
  loadTopics()
  loadRemoteTopics()
})

watch(tagragTopicOptions, (options) => {
  if (!options.includes(ragSearchForm.topic)) {
    ragSearchForm.topic = options[0] || ''
  }
})
</script>
