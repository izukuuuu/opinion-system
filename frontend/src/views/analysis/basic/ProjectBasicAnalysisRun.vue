<template>
  <div class="space-y-6 pb-12">
    <AnalysisPageHeader
      eyebrow="基础分析"
      title="运行分析"
      description="选择专题、时间范围与分析维度，然后提交分析任务。"
    />

    <form class="space-y-6" @submit.prevent="runSelectedFunctions">
      <AnalysisSectionCard
        title="基础配置"
        description="先确定分析专题和时间区间。系统会自动同步该专题的可用范围，并用于本次任务校验。"
      >
        <div class="grid gap-6 lg:grid-cols-[minmax(240px,0.9fr)_minmax(0,1.4fr)]">
          <div class="space-y-2 text-sm text-secondary">
            <div class="flex items-center justify-between gap-3">
              <span class="text-xs font-semibold uppercase tracking-[0.2em] text-muted">分析专题</span>
              <button
                type="button"
                class="analysis-toolbar__action analysis-toolbar__action--ghost px-3 py-1.5 text-xs focus-ring-accent"
                :disabled="topicsState.loading"
                @click="loadTopics"
              >
                <ArrowPathIcon class="h-4 w-4" :class="{ 'animate-spin': topicsState.loading }" />
                <span>{{ topicsState.loading ? '同步中…' : '刷新专题' }}</span>
              </button>
            </div>
            <div class="relative">
              <select
                v-model="analyzeForm.topic"
                class="input h-12 w-full appearance-none rounded-2xl pr-10"
                :disabled="topicsState.loading || !topicOptions.length"
                required
                @change="changeTopic($event.target.value)"
              >
                <option value="" disabled>请选择远程专题数据源</option>
                <option v-for="option in topicOptions" :key="`analyze-${option}`" :value="option">
                  {{ option }}
                </option>
              </select>
              <div class="pointer-events-none absolute right-4 top-1/2 -translate-y-1/2 text-muted">
                <ChevronUpDownIcon class="h-4 w-4" />
              </div>
            </div>
            <p v-if="analyzeForm.topic && (availableRange.start || availableRange.end)" class="text-xs text-muted">
              可用区间：{{ availableRange.start || '--' }} 至 {{ availableRange.end || '--' }}
            </p>
            <p v-if="topicsState.error" class="text-xs text-danger">{{ topicsState.error }}</p>
          </div>

          <div class="space-y-2 text-sm text-secondary">
            <span class="text-xs font-semibold uppercase tracking-[0.2em] text-muted">分析时间范围</span>
            <div class="grid gap-3 sm:grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] sm:items-center">
              <label class="space-y-2">
                <span class="text-xs font-medium text-muted">开始日期</span>
                <input v-model="analyzeForm.start" type="date" class="input h-12 w-full rounded-2xl" required />
              </label>
              <span class="hidden text-muted sm:inline">→</span>
              <label class="space-y-2">
                <span class="text-xs font-medium text-muted">结束日期</span>
                <input v-model="analyzeForm.end" type="date" class="input h-12 w-full rounded-2xl" required />
              </label>
            </div>
            <p class="rounded-2xl border border-soft bg-surface-muted px-4 py-3 text-xs text-muted">
              <span v-if="availableRange.loading" class="animate-pulse text-secondary">正在同步可用时间范围…</span>
              <span v-else-if="availableRange.error" class="text-danger">{{ availableRange.error }}</span>
              <span v-else>建议范围：{{ availableRange.start || '--' }} ~ {{ availableRange.end || '--' }}</span>
            </p>
          </div>
        </div>
      </AnalysisSectionCard>

      <AnalysisSectionCard
        title="选择分析维度"
        :description="`可同时选择多个维度统一执行。当前已选 ${selectedFunctions.length} 项。`"
        :actions="dimensionActions"
        tone="soft"
      >
        <div class="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          <button
            v-for="func in analysisFunctions"
            :key="func.id"
            type="button"
            class="group relative flex min-h-[176px] flex-col justify-between rounded-[1.6rem] border p-4 text-left transition"
            :class="selectedFunctions.includes(func.id)
              ? 'border-transparent bg-white ring-2 ring-brand-500'
              : 'border-soft bg-surface-muted hover:border-brand-soft hover:bg-white'"
            @click="toggleSelection(func.id)"
          >
            <span class="absolute right-4 top-4">
              <span
                class="flex h-6 w-6 items-center justify-center rounded-full border transition"
                :class="selectedFunctions.includes(func.id)
                  ? 'border-brand-600 bg-brand-600 text-white'
                  : 'border-soft bg-white text-transparent'"
              >
                <CheckIcon class="h-4 w-4" />
              </span>
            </span>

            <div class="space-y-4">
              <div
                class="flex h-11 w-11 items-center justify-center rounded-2xl transition"
                :class="selectedFunctions.includes(func.id)
                  ? 'bg-brand-soft text-brand-700'
                  : 'bg-white text-secondary group-hover:bg-brand-soft-muted group-hover:text-brand-700'"
              >
                <component :is="getIcon(func.id)" class="h-5 w-5" />
              </div>

              <div class="space-y-2">
                <h3 class="text-base font-semibold text-primary">{{ func.label }}</h3>
                <p class="text-sm leading-6 text-secondary">{{ func.description }}</p>
              </div>
            </div>

            <div class="mt-5 flex items-center justify-between border-t border-dashed border-soft pt-3 text-xs">
              <span class="text-muted">支持单独运行</span>
              <button
                type="button"
                class="font-semibold text-brand-700 transition hover:text-brand-800"
                @click.stop="runSingleFunction(func.id)"
                :disabled="analyzeState.running"
              >
                仅运行此项
              </button>
            </div>
          </button>
        </div>
      </AnalysisSectionCard>

      <AnalysisSectionCard
        title="日志与执行"
        description="执行前会先完成基础拉取校验。日志卡会合并显示预拉取与分析执行过程。"
      >
        <div class="space-y-5">
          <AnalysisLogList
            :logs="combinedLogs"
            class="max-h-44 overflow-y-auto"
            empty-label="准备就绪。配置完成后点击下方按钮开始分析任务。"
          />

          <div class="flex flex-col gap-3 rounded-[1.5rem] border border-soft bg-surface-muted px-4 py-4 sm:flex-row sm:items-center sm:justify-between">
            <p class="text-sm text-secondary">
              <span v-if="analyzeState.running" class="font-semibold text-secondary">系统任务处理中，请稍候...</span>
              <span v-else>确认配置后即可统一执行所选分析维度。</span>
            </p>
            <button
              type="submit"
              class="btn-primary inline-flex min-w-[170px] items-center justify-center gap-2 rounded-full px-5 py-3 text-base"
              :disabled="analyzeState.running || !selectedFunctions.length"
            >
              <ArrowPathIcon v-if="analyzeState.running" class="h-5 w-5 animate-spin" />
              <span>{{ analyzeState.running ? '正在执行' : `立即开始分析 (${selectedFunctions.length})` }}</span>
            </button>
          </div>
        </div>
      </AnalysisSectionCard>
    </form>
  </div>
</template>

<script setup>
import { computed, onMounted } from 'vue'
import {
  ArrowPathIcon,
  CheckIcon,
  ChevronUpDownIcon,
  FaceSmileIcon,
  KeyIcon,
  MapIcon,
  PresentationChartLineIcon,
  SparklesIcon,
  TagIcon,
  UserGroupIcon
} from '@heroicons/vue/24/outline'
import AnalysisPageHeader from '../../../components/analysis/AnalysisPageHeader.vue'
import AnalysisSectionCard from '../../../components/analysis/AnalysisSectionCard.vue'
import AnalysisLogList from '../../../components/analysis/AnalysisLogList.vue'
import { useBasicAnalysis } from '../../../composables/useBasicAnalysis'

const {
  topicsState,
  topicOptions,
  fetchLogs,
  loadTopics,
  analyzeForm,
  analyzeState,
  analyzeLogs,
  analysisFunctions,
  selectedFunctions,
  selectAll,
  clearSelection,
  runSelectedFunctions,
  runSingleFunction,
  changeTopic,
  availableRange
} = useBasicAnalysis()

const combinedLogs = computed(() => [...(fetchLogs?.value || []), ...(analyzeLogs?.value || [])])

const dimensionActions = [
  {
    label: '全选',
    variant: 'ghost',
    onClick: selectAll
  },
  {
    label: '清空',
    variant: 'ghost',
    onClick: clearSelection
  }
]

const iconMap = {
  attitude: FaceSmileIcon,
  classification: TagIcon,
  geography: MapIcon,
  keywords: KeyIcon,
  publishers: UserGroupIcon,
  trends: PresentationChartLineIcon,
  volume: SparklesIcon
}

const getIcon = (id) => iconMap[id] || SparklesIcon

const toggleSelection = (id) => {
  if (analyzeState.running) return
  const idx = selectedFunctions.value.indexOf(id)
  if (idx > -1) {
    selectedFunctions.value.splice(idx, 1)
  } else {
    selectedFunctions.value.push(id)
  }
}

onMounted(() => {
  if (!topicsState.options?.length) {
    loadTopics()
  }
})
</script>
