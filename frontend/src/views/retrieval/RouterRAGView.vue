<template>
  <div class="min-h-screen pb-20">
    <main class="mx-auto max-w-4xl px-6 pt-8">
      <div class="mb-6 flex justify-end">
        <button
          @click="showManageModal = true"
          class="group flex items-center gap-2 rounded-full border border-gray-200 bg-white px-3 py-1.5 text-xs font-medium text-gray-700 transition hover:border-brand-300 hover:text-brand-600 active:bg-gray-50"
        >
          <svg class="h-4 w-4 text-gray-400 transition group-hover:text-brand-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
          </svg>
          <span>库管理</span>
        </button>
      </div>

      <!-- 1. 搜索核心区 -->
      <section class="mb-10 text-center">
        <h2 class="mb-5 text-2xl font-extrabold text-gray-900 sm:text-3xl">
          你想查找什么内容？
        </h2>

        <form @submit.prevent="handleSearch" class="relative mx-auto max-w-2xl">
          <div class="group relative flex items-center overflow-hidden rounded-2xl bg-white p-2 shadow-xl shadow-brand-500/5 ring-1 ring-black/5 transition focus-within:ring-2 focus-within:ring-brand-500">
            <div class="relative flex items-center border-r border-gray-100 pr-2">
              <select
                v-model="ragSearchForm.topic"
                class="h-full w-32 cursor-pointer appearance-none rounded-xl border-none bg-transparent py-3 pl-4 pr-8 text-sm font-medium text-gray-700 focus:ring-0"
                required
              >
                <option value="" disabled>选择专题</option>
                <option v-for="topic in selectableTopics" :key="topic" :value="topic">{{ topic }}</option>
              </select>
              <svg class="pointer-events-none absolute right-4 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
              </svg>
            </div>

            <input
              v-model="ragSearchForm.query"
              type="text"
              class="flex-1 border-none bg-transparent px-4 py-3 text-lg text-gray-900 placeholder-gray-400 focus:ring-0"
              placeholder="输入关键词，例如：'数据安全规范'..."
              required
            />

            <button
              type="submit"
              :disabled="ragRetrievalState.loading || !ragSearchForm.query || !ragSearchForm.topic"
              class="ml-2 rounded-xl bg-brand-600 px-6 py-3 font-semibold text-white shadow-md transition hover:bg-brand-700 hover:shadow-lg disabled:cursor-not-allowed disabled:bg-gray-300 disabled:shadow-none"
            >
              <svg v-if="ragRetrievalState.loading" class="h-5 w-5 animate-spin" fill="none" viewBox="0 0 24 24">
                <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
              </svg>
              <span v-else>搜索</span>
            </button>
          </div>

          <div class="mt-4 flex flex-wrap items-center justify-center gap-6 text-sm text-gray-500">
            <label class="flex items-center gap-2">
              <span class="text-xs font-medium">相似度阈值: {{ ragSearchForm.threshold }}</span>
              <input v-model.number="ragSearchForm.threshold" type="range" min="0" max="1" step="0.05" class="h-1.5 w-24 cursor-pointer appearance-none rounded-lg bg-gray-200 accent-brand-600" />
            </label>
            <label class="flex items-center gap-2">
              <span class="text-xs font-medium">Top-K:</span>
              <input v-model.number="ragSearchForm.top_k" type="number" min="1" max="20" class="w-12 rounded-md border-gray-300 py-0.5 text-center text-xs focus:border-brand-500 focus:ring-brand-500" />
            </label>
          </div>

          <div class="mt-4 flex flex-wrap items-center justify-center gap-2">
            <button
              v-for="mode in retrievalModes"
              :key="mode.value"
              type="button"
              @click="ragSearchForm.rag_type = mode.value"
              :class="[
                'rounded-full px-3 py-1 text-xs font-medium transition',
                ragSearchForm.rag_type === mode.value
                  ? 'bg-brand-600 text-white'
                  : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
              ]"
            >
              {{ mode.label }}
            </button>
          </div>
        </form>

        <div v-if="ragRetrievalState.error" class="mx-auto mt-4 max-w-lg rounded-lg bg-red-50 p-3 text-sm text-red-600">
          {{ ragRetrievalState.error }}
        </div>
      </section>

      <!-- 2. 结果展示区 -->
      <section v-if="ragRetrievalState.results.length > 0" class="animate-fade-in-up space-y-6">
        <div class="flex items-end justify-between border-b border-gray-200 pb-2">
          <div>
            <h3 class="text-lg font-bold text-gray-900">检索结果</h3>
            <p class="text-sm text-gray-500">找到 {{ ragRetrievalState.total }} 条相关片段</p>
          </div>
          <button @click="exportResults" class="text-sm font-medium text-brand-600 hover:text-brand-800 hover:underline">
            导出 CSV
          </button>
        </div>

        <div class="grid gap-4">
          <div
            v-for="(result, index) in ragRetrievalState.results"
            :key="index"
            class="relative overflow-hidden rounded-xl border border-gray-100 bg-white p-5 shadow-sm"
          >
            <div
              class="absolute left-0 top-0 h-full w-1"
              :class="getScoreColorClass(result.score)"
            ></div>

            <div class="mb-3 flex items-start justify-between">
              <div class="flex items-center gap-2">
                <span class="flex h-6 w-6 items-center justify-center rounded bg-gray-100 text-xs font-bold text-gray-500">#{{ index + 1 }}</span>
                <span
                  class="rounded-full px-2 py-0.5 text-xs font-bold"
                  :class="getScoreBadgeClass(result.score)"
                >
                  匹配度: {{ (result.score * 100).toFixed(1) }}%
                </span>
              </div>

              <button
                @click="copyText(result.text)"
                class="rounded-lg p-1.5 text-gray-400 hover:bg-gray-100 hover:text-gray-700"
                title="复制内容"
              >
                <svg class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
                </svg>
              </button>
            </div>

            <div class="prose prose-sm max-w-none text-gray-700">
              <p class="leading-relaxed">{{ result.text }}</p>
            </div>

            <div v-if="result.metadata && Object.keys(result.metadata).length" class="mt-4 border-t border-gray-50 pt-3">
              <details class="group/meta">
                <summary class="flex cursor-pointer items-center gap-1 text-xs font-medium text-gray-400 hover:text-gray-600">
                  <svg class="h-3 w-3 transition group-open/meta:rotate-90" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" />
                  </svg>
                  显示元数据来源
                </summary>
                <div class="mt-2 grid grid-cols-2 gap-2 rounded bg-gray-50 p-2 text-xs text-gray-500">
                  <div v-for="(val, key) in result.metadata" :key="key" class="truncate">
                    <span class="font-semibold text-gray-400">{{ key }}:</span> {{ val }}
                  </div>
                </div>
              </details>
            </div>
          </div>
        </div>
      </section>

      <!-- 空状态 -->
      <div v-else-if="hasSearched && !ragRetrievalState.loading" class="mt-12 flex flex-col items-center justify-center text-center">
        <div class="flex h-20 w-20 items-center justify-center rounded-full bg-gray-50">
          <svg class="h-10 w-10 text-gray-300" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9.172 16.172a4 4 0 015.656 0M9 10h.01M15 10h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
        </div>
        <h3 class="mt-4 text-lg font-medium text-gray-900">未找到相关内容</h3>
        <p class="mt-2 max-w-sm text-sm text-gray-500">建议尝试降低相似度阈值，或更换更通用的关键词重新检索。</p>
      </div>
    </main>

    <!-- 3. 模态框：库管理 -->
    <div v-if="showManageModal" class="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4">
      <div class="w-full max-w-lg overflow-hidden rounded-2xl bg-white shadow-2xl">
        <div class="flex items-center justify-between border-b border-gray-100 bg-gray-50/50 px-6 py-4">
          <h3 class="text-lg font-semibold text-gray-900">检索库管理</h3>
          <button @click="showManageModal = false" class="text-gray-400 hover:text-gray-600">
            <svg class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div class="space-y-6 p-6">
          <div>
            <label class="mb-2 block text-sm font-medium text-gray-700">现有专题库状态</label>
            <div class="flex items-center justify-between rounded-lg border border-gray-200 p-3">
              <span class="text-sm text-gray-600">
                RouterRAG 可用专题: <span class="font-bold text-gray-900">{{ routerTopicOptions.length }}</span> 个
              </span>
              <button
                @click="loadTopics"
                :disabled="ragTopicsState.loading"
                class="flex items-center gap-1 text-xs font-medium text-brand-600 hover:text-brand-700"
              >
                <ArrowPathIcon class="h-3 w-3" :class="{ 'animate-spin': ragTopicsState.loading }" />
                {{ ragTopicsState.loading ? '同步中' : '同步列表' }}
              </button>
            </div>
          </div>

          <div>
            <div class="mb-2 flex items-center justify-between">
              <label class="block text-sm font-medium text-gray-700">从远程数据构建新库</label>
              <button
                @click="refreshRemoteTopics"
                :disabled="remoteTopicsState.loading"
                class="text-xs text-brand-600 hover:underline"
              >
                {{ remoteTopicsState.loading ? '加载源数据...' : '刷新源数据' }}
              </button>
            </div>

            <div class="space-y-3 rounded-xl border border-blue-100 bg-blue-50/50 p-4">
              <select
                v-model="ragBuildForm.topic"
                class="w-full rounded-lg border-gray-300 text-sm focus:border-brand-500 focus:ring-brand-500"
                :disabled="remoteTopicsState.loading"
              >
                <option value="" disabled>选择远程数据源...</option>
                <option v-for="topic in remoteTopicOptions" :key="`remote-${topic}`" :value="topic">
                  {{ topic }}
                </option>
              </select>

              <button
                @click="handleBuild"
                :disabled="ragBuildState.loading || !ragBuildForm.topic"
                class="w-full rounded-lg bg-brand-600 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-brand-700 disabled:opacity-50"
              >
                {{ ragBuildState.loading ? '正在构建索引 (耗时较长)...' : '开始构建索引' }}
              </button>
            </div>

            <p v-if="ragBuildState.error" class="mt-2 text-xs text-red-600">{{ ragBuildState.error }}</p>
            <p class="mt-2 text-xs text-gray-400">注意：构建索引可能需要几分钟时间，构建完成后需刷新列表。</p>
          </div>
        </div>
      </div>
    </div>

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
  routerTopicOptions,
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
  retrieveRouterRAG,
  retrieveTagRAG
} = useRAGTopics()

const hasSearched = computed(() => ragRetrievalState.error !== '' || ragRetrievalState.results.length > 0)
const showManageModal = ref(false)

const selectableTopics = computed(() => {
  if (ragSearchForm.rag_type === 'tagrag') return tagragTopicOptions.value
  if (ragSearchForm.rag_type === 'routerrag') return routerTopicOptions.value
  return [...new Set([...tagragTopicOptions.value, ...routerTopicOptions.value])]
})

const retrievalModes = [
  { value: 'routerrag', label: 'RouterRAG' },
  { value: 'tagrag', label: 'TagRAG' },
  { value: 'hybrid', label: '混合模式' }
]

const loadTopics = async () => {
  await loadRAGTopics()
}

const refreshRemoteTopics = async () => {
  await loadRemoteTopics()
}

const handleBuild = async () => {
  try {
    const buildType = ragSearchForm.rag_type === 'tagrag' ? 'tagrag' : 'routerrag'
    await buildRagTopic({ type: buildType })
  } catch (error) {
    // Error handled in composable
  }
}

const handleSearch = async () => {
  if (!ragSearchForm.query || !ragSearchForm.topic) {
    ragRetrievalState.error = '请选择专题并输入查询内容'
    return
  }
  try {
    if (ragSearchForm.rag_type === 'routerrag') {
      await retrieveRouterRAG()
    } else {
      await retrieveTagRAG()
    }
  } catch (error) {
    // Error handled
  }
}

const getScoreColorClass = (score) => {
  if (score >= 0.8) return 'bg-emerald-500'
  if (score >= 0.6) return 'bg-blue-500'
  if (score >= 0.4) return 'bg-yellow-500'
  return 'bg-gray-300'
}

const getScoreBadgeClass = (score) => {
  if (score >= 0.8) return 'bg-emerald-100 text-emerald-700'
  if (score >= 0.6) return 'bg-blue-100 text-blue-700'
  if (score >= 0.4) return 'bg-yellow-100 text-yellow-700'
  return 'bg-gray-100 text-gray-600'
}

const copyText = async (text) => {
  try {
    await navigator.clipboard.writeText(text)
  } catch (error) {
    // ignore
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
  link.download = `routerrag_results_${Date.now()}.csv`
  link.click()
}

onMounted(() => {
  loadTopics()
  loadRemoteTopics()
})

watch(selectableTopics, (options) => {
  if (options.length > 0 && !options.includes(ragSearchForm.topic)) {
    ragSearchForm.topic = options[0]
  }
})
</script>

<style scoped>
.animate-fade-in-up {
  animation: fadeInUp 0.5s ease-out;
}

@keyframes fadeInUp {
  from {
    opacity: 0;
    transform: translateY(10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}
</style>
