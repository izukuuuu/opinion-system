<template>
  <div class="space-y-6 pb-12">
    <AnalysisPageHeader
      eyebrow="基础分析"
      title="查看分析结果"
      description="选择专题与分析记录，浏览图表、AI 摘要与各分析模块结果。"
    />

    <AnalysisSectionCard
      title="选择分析记录"
      description="优先从已生成的专题历史记录中加载结果，也支持手动输入时间区间重新查询。"
    >
      <div class="space-y-4 text-sm">
        <div class="grid gap-4 lg:grid-cols-[minmax(220px,0.85fr)_minmax(0,1.2fr)] lg:items-start">
          <label class="space-y-2 text-secondary">
            <span class="text-xs font-semibold uppercase tracking-[0.2em] text-muted">专题</span>
            <select
              v-model="viewSelection.topic"
              class="input h-12 rounded-2xl"
              :disabled="topicsState.loading || !selectableTopicOptions.length"
              required
            >
              <option value="" disabled>请选择专题</option>
              <option v-for="option in selectableTopicOptions" :key="`view-topic-${option}`" :value="option">
                {{ option }}
              </option>
            </select>
          </label>

          <div class="space-y-2">
            <span class="text-xs font-semibold uppercase tracking-[0.2em] text-muted">时间范围</span>
            <div ref="timeRangeRef" class="relative">
              <button
                type="button"
                class="input flex h-12 w-full cursor-pointer items-center justify-between rounded-2xl text-left transition"
                :class="showTimeRange ? 'border-brand-soft ring-1 ring-brand-200' : ''"
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

              <Teleport to="body">
                <div
                  v-if="showTimeRange"
                  class="fixed z-[9999] rounded-[1.5rem] border border-soft bg-surface p-4"
                  :style="timeRangeDropdownStyle"
                >
                  <div
                    v-if="historyState.loading"
                    class="rounded-2xl border border-dashed border-soft bg-surface-muted px-4 py-6 text-center text-xs text-muted"
                  >
                    正在读取该专题的分析存档…
                  </div>
                  <div
                    v-else-if="historyState.error"
                    class="rounded-2xl border border-danger/40 bg-danger-50/60 px-4 py-3 text-xs text-danger"
                  >
                    无法读取记录：{{ historyState.error }}
                  </div>
                  <div v-else-if="analysisHistory.length" class="grid gap-2.5 lg:grid-cols-2">
                    <button
                      v-for="record in analysisHistory"
                      :key="record.id"
                      type="button"
                      class="flex flex-col gap-1.5 rounded-2xl border px-3 py-3 text-left transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-soft/80"
                      :class="record.id === selectedHistoryId
                        ? 'border-brand-soft bg-brand-soft-muted text-secondary ring-1 ring-brand-200'
                        : 'border-soft text-secondary hover:border-brand-soft hover:bg-surface-muted'"
                      @click="selectHistoryFromDropdown(record.id)"
                    >
                      <span class="text-sm font-semibold text-primary">
                        {{ record.start }} → {{ record.end }}
                      </span>
                      <div
                        class="flex flex-wrap items-center gap-x-3 gap-y-0.5 text-xs"
                        :class="record.id === selectedHistoryId ? 'text-secondary' : 'text-muted'"
                      >
                        <span>最新刷新：{{ record.updated_at || '未知' }}</span>
                        <span class="hidden sm:inline">•</span>
                        <span class="truncate">存档：{{ record.folder || record.id }}</span>
                      </div>
                    </button>
                  </div>
                  <p v-else class="text-xs text-muted">当前专题暂无分析存档，请先前往“运行分析”执行一次分析。</p>
                </div>
              </Teleport>
            </div>
          </div>
        </div>

        <div ref="manualInputRef" class="rounded-[1.5rem] border border-dashed border-soft bg-surface-muted p-4">
          <div class="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
            <div class="space-y-1">
              <h3 class="text-sm font-semibold text-primary">手动输入区间</h3>
              <p class="text-sm text-secondary">当历史记录不满足需求时，可直接输入起止日期发起查询。</p>
            </div>
            <div class="analysis-toolbar">
              <button
                type="button"
                class="analysis-toolbar__action analysis-toolbar__action--secondary focus-ring-accent"
                @click="toggleManualInput"
              >
                <CalendarDaysIcon class="h-4 w-4" />
                <span>{{ showManualInput ? '收起手动输入' : '展开手动输入' }}</span>
              </button>
            </div>
          </div>

          <form v-if="showManualInput" class="mt-4 grid gap-3 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto]" @submit.prevent="handleManualSubmit">
            <label class="space-y-2 text-secondary">
              <span class="text-xs font-semibold uppercase tracking-[0.2em] text-muted">开始日期</span>
              <input v-model="viewManualForm.start" type="date" class="input h-11 rounded-2xl" />
            </label>
            <label class="space-y-2 text-secondary">
              <span class="text-xs font-semibold uppercase tracking-[0.2em] text-muted">结束日期</span>
              <input v-model="viewManualForm.end" type="date" class="input h-11 rounded-2xl" />
            </label>
            <div class="flex items-end gap-2">
              <button type="submit" class="btn-secondary h-11 rounded-full px-4" :disabled="!viewSelection.topic">手动查询</button>
              <button
                type="button"
                class="btn-ghost h-11 rounded-full px-4"
                :disabled="loadState.loading || !viewSelection.topic"
                @click="loadResults()"
              >
                {{ loadState.loading ? '读取中…' : '重新加载' }}
              </button>
            </div>
          </form>
        </div>
      </div>
    </AnalysisSectionCard>

    <AnalysisSectionCard
      v-if="aiMainFinding || aiSummaryItems.length"
      title="AI 摘要解读"
      description="AI 摘要作为辅助层展示，与具体图表结果并行查看。"
      tone="soft"
    >
      <div class="space-y-4">
        <div v-if="aiMainFinding" class="rounded-[1.5rem] border border-brand-soft bg-brand-soft-muted px-4 py-4 text-sm">
          <div class="flex items-start gap-3">
            <span class="analysis-meta-list__icon">
              <SparklesIcon class="h-4 w-4" />
            </span>
            <div class="space-y-2">
              <p class="analysis-meta-list__label text-secondary">主要发现</p>
              <p class="whitespace-pre-line text-sm leading-7 text-primary">{{ aiMainFinding.summary }}</p>
              <p v-if="aiMainFinding.sourceFunctions.length" class="text-[11px] text-muted">依据：{{ aiMainFinding.sourceFunctions.join('、') }}</p>
            </div>
          </div>
        </div>
        <AiSummaryList v-if="aiSummaryItems.length" :items="aiSummaryItems" />
        <p class="text-[11px] text-muted">AI 生成解读仅供参考，具体结论请结合分析图表与原始数据判断。</p>
      </div>
    </AnalysisSectionCard>

    <AnalysisSectionCard
      v-else-if="aiSummaryMeta"
      title="AI 摘要暂未生成"
      description="当前专题存在 AI 摘要文件，但未包含有效内容。"
    >
      <p class="text-sm text-secondary">请稍后刷新或重新运行分析。</p>
    </AnalysisSectionCard>

    <AnalysisSectionCard
      title="分析模块"
      description="在结果模块之间切换浏览图表和结构化结果表。"
      :id="analysisSections.length ? 'analysis-section-content' : undefined"
    >
      <div v-if="analysisSections.length" class="space-y-5">
        <div class="flex flex-wrap gap-2">
          <button
            v-for="section in analysisSections"
            :key="section.name"
            type="button"
            class="inline-flex flex-none items-center gap-2 rounded-full border px-3 py-1.5 text-xs font-semibold transition sm:text-[13px]"
            :class="section.name === activeSectionName
              ? 'border-transparent bg-brand-soft-muted text-secondary ring-1 ring-brand-200'
              : 'border-soft text-secondary hover:border-brand-soft hover:bg-surface-muted'"
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
          <header class="flex flex-wrap items-center justify-between gap-3">
            <div class="flex items-center gap-3">
              <span class="analysis-meta-list__icon">
                <component :is="getSectionIcon(activeSection.name)" class="h-4 w-4" />
              </span>
              <div class="space-y-1">
                <h3 class="text-base font-semibold text-primary">{{ getChineseTitle(activeSection.label) }}</h3>
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
              :is-keywords="activeSection.name === 'keywords'"
              :all-rows="target.allRows || []"
            >
              <template #default>
                <div v-if="target.rows.length && shouldShowDataTable(activeSection.name, target.rows)" class="overflow-hidden rounded-2xl border border-soft">
                  <table class="min-w-full text-sm">
                    <thead class="bg-surface-muted text-xs uppercase tracking-wide text-muted">
                      <tr>
                        <th class="px-3 py-2 text-left">名称</th>
                        <th class="px-3 py-2 text-left">数值</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr
                        v-for="(row, index) in target.rows"
                        :key="`${target.target}-${index}`"
                        class="border-t border-soft text-secondary"
                      >
                        <td class="px-3 py-2">{{ formatRowName(row) }}</td>
                        <td class="px-3 py-2">{{ formatRowValue(row) }}</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
                              </template>
            </AnalysisChartPanel>
          </div>
        </div>
      </div>
      <p v-else class="text-sm text-muted">暂无分析结果。请先运行分析并刷新。</p>
    </AnalysisSectionCard>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { Teleport } from 'vue'
import {
  BookmarkSquareIcon,
  CalendarDaysIcon,
  ChartBarIcon,
  ChartPieIcon,
  ChevronDownIcon,
  GlobeAltIcon,
  HashtagIcon,
  MegaphoneIcon,
  SparklesIcon,
  Squares2X2Icon,
  UsersIcon
} from '@heroicons/vue/24/outline'
import AnalysisChartPanel from '../../../components/AnalysisChartPanel.vue'
import AnalysisPageHeader from '../../../components/analysis/AnalysisPageHeader.vue'
import AnalysisSectionCard from '../../../components/analysis/AnalysisSectionCard.vue'
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
  return row.displayName ?? row.name ?? row.label ?? row.key ?? '未命名'
}

const formatRowValue = (row) => {
  if (!row) return 0
  if (row.displayValue != null) return row.displayValue
  return row.value ?? row.count ?? row.total ?? 0
}

const isPureDateRows = (rows) => {
  if (!Array.isArray(rows) || !rows.length) return false
  const datePattern = /^\d{4}-\d{2}-\d{2}$/
  return rows.every((row) => {
    const name = row.displayName ?? row.name ?? row.label ?? row.key ?? ''
    return datePattern.test(name)
  })
}

const shouldShowDataTable = (sectionName, rows) => {
  if (sectionName === 'trends' && isPureDateRows(rows)) return false
  return true
}

const toggleManualInput = (event) => {
  if (event?.stopPropagation) {
    event.stopPropagation()
  }
  showManualInput.value = !showManualInput.value
}

const handleManualSubmit = () => {
  loadResultsFromManual()
  showManualInput.value = false
}

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
