<template>
  <div class="space-y-8">
    <section class="card-surface space-y-5 p-6">
      <header class="flex flex-wrap items-start justify-between gap-3">
        <div class="space-y-2">
          <p class="text-xs font-semibold uppercase tracking-[0.4em] text-muted">Select</p>
          <h2 class="text-2xl font-semibold text-primary">选择分析记录</h2>
          <p class="text-sm text-secondary">先选择专题，系统会列出该专题所有已生成的分析存档，点击任意卡片即可立即刷新结果。</p>
        </div>
        <button
          type="button"
          class="btn-secondary inline-flex items-center gap-2 whitespace-nowrap px-4 py-2 text-xs font-semibold sm:text-sm"
          :disabled="historyState.loading || loadState.loading || !viewSelection.topic"
          @click="refreshHistory"
        >
          <ArrowPathIcon
            class="h-4 w-4"
            :class="historyState.loading ? 'animate-spin' : ''"
          />
          <span>{{ historyState.loading ? '刷新中…' : '刷新记录' }}</span>
        </button>
      </header>
      <div class="space-y-6 text-sm">
        <label class="space-y-2 text-secondary">
          <span class="text-xs font-semibold text-muted">专题 Topic *</span>
          <select
            v-model="viewSelection.topic"
            class="input"
            :disabled="topicsState.loading || !selectableTopicOptions.length"
            required
          >
            <option value="" disabled>请选择远程专题</option>
            <option
              v-for="option in selectableTopicOptions"
              :key="`view-topic-${option}`"
              :value="option"
            >
              {{ option }}
            </option>
          </select>
          <p class="text-xs text-muted">
            <span v-if="topicsState.loading">正在加载专题列表…</span>
            <span v-else-if="!selectableTopicOptions.length">暂无可用专题，请先完成远程数据拉取。</span>
            <span v-else>选择专题后可读取对应的分析记录。</span>
          </p>
        </label>

        <div class="space-y-3" v-if="viewSelection.topic">
          <p class="text-xs font-semibold uppercase tracking-[0.4em] text-muted">已有存档</p>
          <div v-if="historyState.loading" class="rounded-2xl border border-dashed border-soft bg-surface-muted px-4 py-6 text-center text-xs text-muted">
            正在读取该专题的分析存档…
          </div>
          <div v-else-if="historyState.error" class="rounded-2xl border border-danger/40 bg-danger-soft px-4 py-3 text-xs text-danger">
            无法读取记录：{{ historyState.error }}
          </div>
          <div v-else-if="analysisHistory.length" class="grid gap-3 lg:grid-cols-2">
            <button
              v-for="record in analysisHistory"
              :key="record.id"
              type="button"
              class="flex flex-col gap-1 rounded-2xl border px-4 py-3 text-left transition"
              :class="record.id === selectedHistoryId ? 'border-brand-soft bg-brand-soft/60 text-brand-700 shadow-sm' : 'border-soft text-secondary hover:border-brand-soft hover:bg-surface-muted'"
              @click="selectHistory(record.id)"
            >
              <span class="text-sm font-semibold text-primary">{{ record.start }} → {{ record.end }}</span>
              <span class="text-xs text-muted">最新刷新：{{ record.updated_at || '未知' }}</span>
              <span class="text-xs text-muted">存档目录：{{ record.folder || record.id }}</span>
            </button>
          </div>
          <p v-else class="text-xs text-muted">当前专题暂无分析存档，请先前往“运行分析”执行一次 Analyze。</p>
        </div>

        <details v-if="viewSelection.topic" class="rounded-2xl border border-dashed border-soft p-4" :open="false">
          <summary class="cursor-pointer text-xs font-semibold uppercase tracking-[0.4em] text-muted">
            手动输入其它区间
          </summary>
          <form class="mt-4 space-y-3" @submit.prevent="loadResultsFromManual">
            <div class="grid gap-3 md:grid-cols-2">
              <label class="space-y-2 text-secondary">
                <span class="text-xs font-semibold text-muted">开始日期 Start</span>
                <input v-model="viewManualForm.start" type="date" class="input" />
              </label>
              <label class="space-y-2 text-secondary">
                <span class="text-xs font-semibold text-muted">结束日期 End</span>
                <input v-model="viewManualForm.end" type="date" class="input" />
              </label>
            </div>
            <div class="flex flex-wrap gap-3 text-sm">
              <button type="submit" class="btn-secondary" :disabled="!viewSelection.topic">手动查询</button>
              <button type="button" class="btn-ghost" :disabled="loadState.loading || !viewSelection.topic" @click="loadResults()">
                {{ loadState.loading ? '读取中…' : '重新加载' }}
              </button>
            </div>
          </form>
        </details>
      </div>
    </section>

    <section class="card-surface space-y-4 p-6">
      <header class="flex flex-col gap-2">
        <p class="text-xs font-semibold uppercase tracking-[0.4em] text-muted">Summary</p>
        <template v-if="analysisSummary">
          <h2 class="text-2xl font-semibold text-primary">
            专题「{{ analysisSummary.topic }}」 · {{ analysisSummary.range.start }} → {{ analysisSummary.range.end }}
          </h2>
          <p class="text-sm text-secondary">共 {{ analysisSummary.functionCount }} 个分析结果，见下方列表。</p>
        </template>
        <template v-else>
          <h2 class="text-2xl font-semibold text-primary">暂无可用结果</h2>
          <p class="text-sm text-secondary">还未读取任何分析 JSON，请先选择历史记录或手动查询。</p>
        </template>
        <p class="text-xs text-muted">最近刷新：{{ lastLoaded || '尚未读取' }}</p>
      </header>
    </section>

    <section
      class="card-surface space-y-5 p-6"
      :id="analysisSections.length ? 'analysis-section-content' : undefined"
    >
      <header class="flex flex-col gap-1">
        <h3 class="text-lg font-semibold text-primary">分析模块列表</h3>
        <p class="text-sm text-secondary">点击模块卡片即可在下方查看对应图表。</p>
      </header>
      <div v-if="analysisSections.length" class="space-y-5">
        <div class="grid gap-2 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-5">
          <button
            v-for="section in analysisSections"
            :key="section.name"
            type="button"
            class="flex flex-col gap-2 rounded-2xl border px-4 py-3 text-left transition"
            :class="
              section.name === activeSectionName
                ? 'border-transparent bg-brand-soft/70 text-brand-700 shadow-sm ring-1 ring-brand-soft/80'
                : 'border-soft text-secondary hover:border-brand-soft hover:bg-surface-muted'
            "
            @click="setActiveSection(section.name)"
          >
            <span
              class="flex h-9 w-9 items-center justify-center rounded-full"
              :class="section.name === activeSectionName ? 'bg-brand-600/10 text-brand-600' : 'bg-surface-muted text-muted'"
            >
              <component :is="getSectionIcon(section.name)" class="h-5 w-5" />
            </span>
            <span class="text-sm font-semibold text-primary">{{ getChineseTitle(section.label) }}</span>
          </button>
        </div>
        <div v-if="activeSection" class="space-y-4 border-t border-soft pt-4">
          <header class="flex flex-wrap items-center justify-between gap-3">
            <div class="flex items-center gap-3">
              <span class="flex h-11 w-11 items-center justify-center rounded-full bg-brand-600/10 text-brand-600">
                <component :is="getSectionIcon(activeSection.name)" class="h-6 w-6" />
              </span>
              <div class="space-y-1">
                <h3 class="text-xl font-semibold text-primary">{{ getChineseTitle(activeSection.label) }}</h3>
                <p class="text-sm text-secondary">{{ activeSection.description }}</p>
              </div>
            </div>
            <span class="text-xs text-muted">{{ activeSection.targets.length }} 个结果</span>
          </header>
          <div class="grid gap-4 md:grid-cols-2">
            <AnalysisChartPanel
              v-for="target in activeSection.targets"
              :key="`${activeSection.name}-${target.target}`"
              :title="target.title"
              :description="target.subtitle"
              :option="target.option"
              :has-data="target.hasData"
            >
              <template #default>
                <div v-if="target.rows.length" class="rounded-2xl border border-soft">
                  <table class="min-w-full text-sm">
                    <thead class="bg-surface-muted text-xs uppercase tracking-wide text-muted">
                      <tr>
                        <th class="px-3 py-2 text-left">名称</th>
                        <th class="px-3 py-2 text-left">数值</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr v-for="(row, index) in target.rows" :key="`${target.target}-${index}`" class="border-t border-soft text-secondary">
                        <td class="px-3 py-2">{{ formatRowName(row) }}</td>
                        <td class="px-3 py-2">{{ formatRowValue(row) }}</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
                <details class="rounded-2xl border border-dashed border-soft px-3 py-2 text-xs">
                  <summary class="cursor-pointer text-brand-600">查看原始 JSON</summary>
                  <pre class="mt-2 max-h-56 overflow-auto bg-slate-900/90 p-3 text-brand-soft">{{ target.rawText }}</pre>
                </details>
              </template>
            </AnalysisChartPanel>
          </div>
        </div>
      </div>
      <p v-else class="text-xs text-muted">暂无分析结果。请先运行分析并刷新。</p>
    </section>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import {
  ArrowPathIcon,
  ChartBarIcon,
  ChartPieIcon,
  GlobeAltIcon,
  HashtagIcon,
  MegaphoneIcon,
  UsersIcon
} from '@heroicons/vue/24/outline'
import AnalysisChartPanel from '../../../components/AnalysisChartPanel.vue'
import { useBasicAnalysis } from '../../../composables/useBasicAnalysis'
import { useActiveProject } from '../../../composables/useActiveProject'

const {
  analysisSummary,
  analysisSections,
  topicsState,
  topicOptions,
  analysisHistory,
  viewSelection,
  viewManualForm,
  loadResults,
  loadResultsFromManual,
  historyState,
  historyOptions,
  loadHistory,
  selectedHistoryId,
  applyHistorySelection,
  loadState,
  lastLoaded
} = useBasicAnalysis()

const { activeProjectName } = useActiveProject()

const selectableTopicOptions = computed(() => {
  const options = Array.isArray(topicOptions.value) ? topicOptions.value.slice() : []
  const activeName = (activeProjectName.value || '').trim()
  if (activeName && !options.includes(activeName)) {
    return [activeName, ...options]
  }
  return options
})

const autoSelectedTopic = ref('')
const activeSectionName = ref('')

const sectionIconMap = {
  classification: ChartPieIcon,
  attitude: ChartBarIcon,
  trends: MegaphoneIcon,
  publishers: UsersIcon,
  keywords: HashtagIcon,
  volume: MegaphoneIcon,
  geography: GlobeAltIcon
}

const activeSection = computed(() => {
  if (!analysisSections.value?.length) return null
  return analysisSections.value.find((section) => section.name === activeSectionName.value) || analysisSections.value[0]
})

const getSectionIcon = (sectionName) => {
  return sectionIconMap[sectionName] || ChartPieIcon
}

const getChineseTitle = (label) => {
  if (!label) return '未命名'
  const match = label.match(/^[\u4e00-\u9fa5·\s]+/)
  if (match) {
    return match[0].trim() || label
  }
  const splitted = label.split(/\s+/)
  return splitted.length ? splitted[0] : label
}

const setActiveSection = async (sectionName) => {
  if (!sectionName || sectionName === activeSectionName.value) return
  activeSectionName.value = sectionName
  await nextTick()
  const target = document.getElementById('analysis-section-content')
  if (target) {
    target.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }
}

const selectHistory = (recordId) => {
  if (!recordId || recordId === selectedHistoryId.value) return
  selectedHistoryId.value = recordId
}

const refreshHistory = async () => {
  if (historyState.loading || loadState.loading) return
  const topic = (viewSelection.topic || '').trim()
  if (!topic) return
  await loadHistory(topic)
  if (selectedHistoryId.value) {
    await applyHistorySelection(selectedHistoryId.value, { shouldLoad: true })
  }
}

watch(
  () => activeProjectName.value,
  (name) => {
    const trimmed = (name || '').trim()
    if (!trimmed) return
    if (!viewSelection.topic || viewSelection.topic === autoSelectedTopic.value) {
      autoSelectedTopic.value = trimmed
      viewSelection.topic = trimmed
    }
  },
  { immediate: true }
)

watch(
  () => viewSelection.topic,
  async (value, previous) => {
    if (!value) {
      autoSelectedTopic.value = ''
      return
    }
    if (autoSelectedTopic.value && value !== autoSelectedTopic.value) {
      autoSelectedTopic.value = ''
    }
    if (value && value !== previous) {
      await refreshHistory()
    }
  }
)

watch(
  analysisSections,
  (sections) => {
    if (!sections?.length) {
      activeSectionName.value = ''
    } else if (!sections.some((section) => section.name === activeSectionName.value)) {
      activeSectionName.value = sections[0]?.name || ''
    }
  },
  { immediate: true }
)

watch(
  selectedHistoryId,
  (id) => {
    if (!id) return
    applyHistorySelection(id, { shouldLoad: true })
  }
)

onMounted(() => {
  if (selectedHistoryId.value) {
    applyHistorySelection(selectedHistoryId.value, { shouldLoad: true })
  }
})

const formatRowName = (row) => {
  if (!row) return '-'
  return row.name ?? row.label ?? row.key ?? '未命名'
}

const formatRowValue = (row) => {
  if (!row) return 0
  return row.value ?? row.count ?? row.total ?? 0
}
</script>
