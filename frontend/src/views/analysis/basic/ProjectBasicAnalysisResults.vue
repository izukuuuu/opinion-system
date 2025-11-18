<template>
  <div class="space-y-4">
    <section class="card-surface space-y-4 p-6">
      <header class="flex flex-wrap items-center justify-between gap-3">
        <h2 class="text-xl font-semibold text-primary">选择分析记录</h2>
        <div class="flex items-center gap-2">
          <div ref="manualInputRef" class="relative" v-if="viewSelection.topic">
            <button
              type="button"
              class="btn-secondary inline-flex items-center gap-2 whitespace-nowrap px-4 py-2 text-xs font-semibold sm:text-sm"
              @click="toggleManualInput"
            >
              <CalendarDaysIcon class="h-4 w-4" />
              <span>手动输入</span>
            </button>
            <div
              v-if="showManualInput"
              class="absolute right-0 top-full z-50 mt-2 w-80 rounded-2xl border border-soft bg-surface p-4 shadow-lg"
            >
              <form class="space-y-3" @submit.prevent="handleManualSubmit">
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
            </div>
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
        </div>
      </header>
      <div class="space-y-4 text-sm">
        <div class="flex flex-col gap-2 md:flex-row md:items-end md:gap-4">
          <label class="flex-1 space-y-2 text-secondary">
            <span class="text-xs font-semibold text-muted">专题</span>
            <select
              v-model="viewSelection.topic"
              class="input"
              :disabled="topicsState.loading || !selectableTopicOptions.length"
              required
            >
              <option value="" disabled>请选择专题</option>
              <option
                v-for="option in selectableTopicOptions"
                :key="`view-topic-${option}`"
                :value="option"
              >
                {{ option }}
              </option>
            </select>
          </label>
          
          <div ref="timeRangeRef" class="relative" v-if="viewSelection.topic">
            <label class="space-y-2 text-secondary">
              <span class="text-xs font-semibold text-muted">时间范围</span>
              <button
                type="button"
                class="input flex w-full cursor-pointer items-center justify-between text-left transition"
                :class="showTimeRange ? 'border-brand-soft ring-1 ring-brand-soft/80' : ''"
                @click="toggleTimeRange"
              >
                <span class="truncate" :class="selectedHistoryId && selectedRecord ? 'text-primary' : 'text-muted'">
                  {{ selectedHistoryId && selectedRecord ? `${selectedRecord.start} → ${selectedRecord.end}` : '请选择时间范围' }}
                </span>
                <ChevronDownIcon 
                  class="h-4 w-4 shrink-0 text-muted transition-transform"
                  :class="showTimeRange ? 'rotate-180' : ''"
                />
              </button>
            </label>
            
            <Teleport to="body">
              <div
                v-if="showTimeRange"
                class="fixed z-[9999] rounded-2xl border border-soft bg-surface p-4 shadow-lg"
                :style="timeRangeDropdownStyle"
              >
              <div v-if="historyState.loading" class="rounded-2xl border border-dashed border-soft bg-surface-muted px-4 py-6 text-center text-xs text-muted">
                正在读取该专题的分析存档…
              </div>
              <div v-else-if="historyState.error" class="rounded-2xl border border-danger/40 bg-danger-soft px-4 py-3 text-xs text-danger">
                无法读取记录：{{ historyState.error }}
              </div>
              <div v-else-if="analysisHistory.length" class="grid gap-2.5 lg:grid-cols-2">
                <button
                  v-for="record in analysisHistory"
                  :key="record.id"
                  type="button"
                  class="flex flex-col gap-1.5 rounded-2xl border px-3 py-2.5 text-left transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-soft/80"
                  :class="
                    record.id === selectedHistoryId
                      ? 'border-brand-soft bg-brand-soft text-brand-700 shadow-sm ring-1 ring-brand-soft'
                      : 'border-soft text-secondary hover:border-brand-soft hover:bg-surface-muted'
                  "
                  @click="selectHistoryFromDropdown(record.id)"
                >
                  <span
                    class="text-sm font-semibold"
                    :class="record.id === selectedHistoryId ? 'text-brand-700' : 'text-primary'"
                  >
                    {{ record.start }} → {{ record.end }}
                  </span>
                  <div class="flex flex-wrap items-center gap-x-3 gap-y-0.5 text-xs"
                    :class="record.id === selectedHistoryId ? 'text-brand-700/80' : 'text-muted'"
                  >
                    <span>最新刷新：{{ record.updated_at || '未知' }}</span>
                    <span class="hidden sm:inline">•</span>
                    <span class="truncate">存档：{{ record.folder || record.id }}</span>
                  </div>
                </button>
              </div>
              <p v-else class="text-xs text-muted">当前专题暂无分析存档，请先前往"运行分析"执行一次 Analyze。</p>
              </div>
            </Teleport>
          </div>
        </div>
        
        <template v-if="analysisSummary">
          <div class="border-t border-soft pt-4">
            <dl class="flex flex-wrap items-center gap-4 text-sm">
              <div class="flex items-center gap-2">
                <span class="inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-brand-600/10 text-brand-600">
                  <BookmarkSquareIcon class="h-3.5 w-3.5" />
                </span>
                <div class="flex items-center gap-1.5">
                  <dt class="text-xs font-semibold uppercase tracking-[0.2em] text-muted">专题</dt>
                  <dd class="font-semibold text-primary">
                    {{ analysisSummary.topic }}
                  </dd>
                </div>
              </div>
              <div class="flex items-center gap-2">
                <span class="inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-brand-600/10 text-brand-600">
                  <CalendarDaysIcon class="h-3.5 w-3.5" />
                </span>
                <div class="flex items-center gap-1.5">
                  <dt class="text-xs font-semibold uppercase tracking-[0.2em] text-muted">分析区间</dt>
                  <dd class="font-semibold text-primary">
                    {{ analysisSummary.range?.start || '未提供' }} → {{ analysisSummary.range?.end || '未提供' }}
                  </dd>
                </div>
              </div>
              <div class="flex items-center gap-2">
                <span class="inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-brand-600/10 text-brand-600">
                  <Squares2X2Icon class="h-3.5 w-3.5" />
                </span>
                <div class="flex items-center gap-1.5">
                  <dt class="text-xs font-semibold uppercase tracking-[0.2em] text-muted">分析模块</dt>
                  <dd class="font-semibold text-primary">{{ analysisSummary.functionCount }}</dd>
                </div>
              </div>
            </dl>
          </div>
        </template>
      </div>
    </section>

    <section v-if="aiMainFinding || aiSummaryItems.length" class="card-surface space-y-4 p-5 sm:p-6">
      <header class="flex flex-wrap items-center justify-between gap-3 text-sm">
        <h3 class="text-lg font-semibold text-primary">AI 摘要解读</h3>
        <div class="flex flex-wrap items-center gap-3 text-xs text-muted">
          <span v-if="aiSummaryTimestamp" class="inline-flex items-center gap-1 text-secondary">
            <SparklesIcon class="h-4 w-4 text-brand-600" />
            {{ aiSummaryTimestamp }}
          </span>
          <span v-if="aiSummaryRangeText" class="inline-flex items-center gap-1 text-secondary">
            <CalendarDaysIcon class="h-4 w-4" />
            {{ aiSummaryRangeText }}
          </span>
        </div>
      </header>
      <div
        v-if="aiMainFinding"
        class="rounded-2xl border border-brand-soft bg-brand-soft/30 px-4 py-3 text-sm shadow-sm"
      >
        <div class="flex items-start gap-2">
          <span class="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-brand-600/10 text-brand-600">
            <SparklesIcon class="h-4 w-4" />
          </span>
          <div class="space-y-1">
            <p class="text-[11px] font-semibold uppercase tracking-[0.3em] text-brand-700">主要发现</p>
            <p class="whitespace-pre-line text-sm leading-relaxed text-primary">{{ aiMainFinding.summary }}</p>
            <p v-if="aiMainFinding.sourceFunctions.length" class="text-[11px] text-muted">依据：{{ aiMainFinding.sourceFunctions.join('、') }}</p>
          </div>
        </div>
      </div>
      <AiSummaryList v-if="aiSummaryItems.length" :items="aiSummaryItems" />
      <p class="text-[11px] text-muted">AI 生成解读仅供参考，具体请查看分析图表。</p>
    </section>

    <section
      v-else-if="aiSummaryMeta"
      class="card-surface space-y-3 p-6 text-sm text-secondary"
    >
      <p class="text-lg font-semibold text-primary">AI 摘要暂未生成</p>
      <p>当前专题存在 AI 摘要文件，但未包含有效内容，请稍后刷新或重新运行分析。</p>
    </section>

    <section
      class="card-surface space-y-5 p-6"
      :id="analysisSections.length ? 'analysis-section-content' : undefined"
    >
      <header class="flex flex-col gap-1">
        <h3 class="text-lg font-semibold text-primary">分析模块</h3>
      </header>
      <div v-if="analysisSections.length" class="space-y-5">
        <div class="flex flex-wrap gap-2">
          <button
            v-for="section in analysisSections"
            :key="section.name"
            type="button"
            class="inline-flex flex-none items-center gap-2 rounded-full border px-3 py-1.5 text-xs font-semibold transition sm:text-[13px]"
            :class="
              section.name === activeSectionName
                ? 'border-transparent bg-brand-soft/70 text-brand-700 shadow-sm ring-1 ring-brand-soft/80'
                : 'border-soft text-secondary hover:border-brand-soft hover:bg-surface-muted'
            "
            @click="setActiveSection(section.name)"
          >
            <span
              class="flex h-6 w-6 items-center justify-center rounded-full"
              :class="section.name === activeSectionName ? 'bg-brand-600/10 text-brand-600' : 'bg-surface-muted text-muted'"
            >
              <component :is="getSectionIcon(section.name)" class="h-4 w-4" />
            </span>
            <span class="text-primary">{{ getChineseTitle(section.label) }}</span>
          </button>
        </div>
        <div v-if="activeSection" class="space-y-4 border-t border-soft pt-4">
          <header class="flex flex-wrap items-center justify-between gap-2 text-sm">
            <div class="flex items-center gap-2">
              <span class="flex h-9 w-9 items-center justify-center rounded-full bg-brand-600/10 text-brand-600">
                <component :is="getSectionIcon(activeSection.name)" class="h-5 w-5" />
              </span>
              <div class="space-y-0.5">
                <h3 class="text-base font-semibold leading-tight text-primary">{{ getChineseTitle(activeSection.label) }}</h3>
                <p class="text-xs text-secondary">{{ activeSection.description }}</p>
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
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { Teleport } from 'vue'
import {
  ArrowPathIcon,
  BookmarkSquareIcon,
  CalendarDaysIcon,
  ChartBarIcon,
  ChartPieIcon,
  ChevronDownIcon,
  GlobeAltIcon,
  HashtagIcon,
  Squares2X2Icon,
  MegaphoneIcon,
  UsersIcon,
  SparklesIcon
} from '@heroicons/vue/24/outline'
import AnalysisChartPanel from '../../../components/AnalysisChartPanel.vue'
import AiSummaryList from '../../../components/analysis/AiSummaryList.vue'
import { useBasicAnalysis } from '../../../composables/useBasicAnalysis'

const {
  analysisFunctions,
  analysisSummary,
  analysisSections,
  analysisAiSummary,
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

const selectableTopicOptions = computed(() =>
  Array.isArray(topicOptions.value) ? topicOptions.value.slice() : []
)

const autoSelectedTopic = ref('')
const activeSectionName = ref('')
const showTimeRange = ref(false)
const timeRangeRef = ref(null)
const showManualInput = ref(false)
const manualInputRef = ref(null)

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

const aiSummaryMeta = analysisAiSummary

const aiSummaryItems = computed(() => {
  const summaries = aiSummaryMeta.value?.summaries
  if (!Array.isArray(summaries) || !summaries.length) return []
  return summaries.map((entry) => {
    const meta = analysisFunctions.find((item) => item.id === entry.function) || {}
    const label = meta.label || entry.function_label || entry.function
    const target = entry.target || '总体'
    return {
      id: `${entry.function}-${target}`,
      label,
      target,
      aiSummary: (entry.ai_summary || '').trim(),
      textSnapshot: entry.text_snapshot || '',
      icon: getSectionIcon(entry.function),
      updatedAt: formatTimestamp(entry.updated_at)
    }
  })
})

const aiSummaryTimestamp = computed(() => formatTimestamp(aiSummaryMeta.value?.generated_at))

const aiSummaryRangeText = computed(() => {
  const range = aiSummaryMeta.value?.range
  if (!range?.start) return ''
  const end = range.end || range.start
  return `${range.start} → ${end}`
})

const aiMainFinding = computed(() => {
  const main = aiSummaryMeta.value?.main_finding
  const summary = (main?.summary || '').trim()
  if (!summary) return null
  const sources = Array.isArray(main?.source_functions) ? main.source_functions.filter(Boolean) : []
  return {
    summary,
    sourceFunctions: sources,
    updatedAt: formatTimestamp(main?.updated_at || aiSummaryMeta.value?.generated_at)
  }
})

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
    const offset = target.getBoundingClientRect().top + window.scrollY - 48
    window.scrollTo({
      top: offset > 0 ? offset : 0,
      behavior: 'smooth'
    })
  }
}

const selectHistory = (recordId) => {
  if (!recordId || recordId === selectedHistoryId.value) return
  selectedHistoryId.value = recordId
}

const selectedRecord = computed(() => {
  return analysisHistory.value.find((item) => item.id === selectedHistoryId.value)
})

const toggleTimeRange = async (event) => {
  event.stopPropagation()
  showTimeRange.value = !showTimeRange.value
  if (showTimeRange.value) {
    await nextTick()
    updateTimeRangePosition()
  }
}

const timeRangeDropdownStyle = ref({})

const updateTimeRangePosition = () => {
  if (!timeRangeRef.value) return
  const rect = timeRangeRef.value.getBoundingClientRect()
  timeRangeDropdownStyle.value = {
    top: `${rect.bottom + 8}px`,
    right: `${window.innerWidth - rect.right}px`,
    width: `${Math.max(rect.width, 400)}px`
  }
}

watch(showTimeRange, async (isOpen) => {
  if (isOpen) {
    await nextTick()
    updateTimeRangePosition()
    window.addEventListener('scroll', updateTimeRangePosition, true)
    window.addEventListener('resize', updateTimeRangePosition)
  } else {
    window.removeEventListener('scroll', updateTimeRangePosition, true)
    window.removeEventListener('resize', updateTimeRangePosition)
  }
})

const selectHistoryFromDropdown = (recordId) => {
  selectHistory(recordId)
  showTimeRange.value = false
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
  topicOptions,
  (options) => {
    const first = Array.isArray(options) && options.length ? options[0] : ''
    if (!viewSelection.topic && first) {
      autoSelectedTopic.value = first
      viewSelection.topic = first
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

onMounted(async () => {
  // 进入页面时自动刷新记录
  if (viewSelection.topic) {
    await refreshHistory()
  }
  
  if (selectedHistoryId.value) {
    applyHistorySelection(selectedHistoryId.value, { shouldLoad: true })
  }
})

const formatTimestamp = (value) => {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return value
  }
  return date.toLocaleString('zh-CN', {
    hour12: false,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  })
}

const formatRowName = (row) => {
  if (!row) return '-'
  return row.name ?? row.label ?? row.key ?? '未命名'
}

const formatRowValue = (row) => {
  if (!row) return 0
  return row.value ?? row.count ?? row.total ?? 0
}

const toggleManualInput = (event) => {
  event.stopPropagation()
  showManualInput.value = !showManualInput.value
}

const handleManualSubmit = () => {
  loadResultsFromManual()
  showManualInput.value = false
}

// 点击外部关闭悬浮窗
const handleClickOutside = (event) => {
  if (manualInputRef.value && !manualInputRef.value.contains(event.target)) {
    showManualInput.value = false
  }
  if (timeRangeRef.value && !timeRangeRef.value.contains(event.target)) {
    showTimeRange.value = false
  }
}

onMounted(() => {
  document.addEventListener('click', handleClickOutside)
})

onBeforeUnmount(() => {
  document.removeEventListener('click', handleClickOutside)
  window.removeEventListener('scroll', updateTimeRangePosition, true)
  window.removeEventListener('resize', updateTimeRangePosition)
})
</script>
