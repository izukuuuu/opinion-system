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
              <AppSelect
                :options="topicSelectOptions"
                :value="analyzeForm.topic"
                :disabled="topicsState.loading || !topicOptions.length"
                @change="handleTopicChange"
              />
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
            class="group relative flex min-h-[140px] flex-col justify-between rounded-[1.4rem] border p-3.5 text-left transition"
            :style="selectedFunctions.includes(func.id) ? {
              borderColor: getColor(func.id).border,
              backgroundColor: getColor(func.id).bg,
              boxShadow: `0 0 0 2px ${getColor(func.id).border}`
            } : undefined"
            :class="!selectedFunctions.includes(func.id) && 'border-soft bg-surface hover:bg-surface-muted'"
            @click="toggleSelection(func.id)"
          >
            <span class="absolute right-3 top-3">
              <span
                class="flex h-5 w-5 items-center justify-center rounded-full border transition"
                :style="{
                  borderColor: selectedFunctions.includes(func.id) ? getColor(func.id).border : undefined,
                  backgroundColor: selectedFunctions.includes(func.id) ? getColor(func.id).border : undefined,
                  color: selectedFunctions.includes(func.id) ? '#fff' : undefined
                }"
                :class="!selectedFunctions.includes(func.id) && 'border-soft bg-surface text-transparent'"
              >
                <CheckIcon class="h-3.5 w-3.5" />
              </span>
            </span>

            <div class="space-y-2.5">
              <div
                class="flex h-9 w-9 items-center justify-center rounded-xl transition"
                :style="{
                  backgroundColor: selectedFunctions.includes(func.id) ? '#fff' : getColor(func.id).bg,
                  color: getColor(func.id).icon
                }"
              >
                <component :is="getIcon(func.id)" class="h-5 w-5" />
              </div>

              <div class="space-y-1">
                <h3 class="text-sm font-semibold text-primary">{{ func.label }}</h3>
                <p class="text-xs leading-5 text-secondary">{{ func.description }}</p>
              </div>
            </div>

            <div class="mt-3 flex items-center justify-end border-t border-dashed border-soft pt-2.5 text-xs">
              <span class="rounded-full bg-white px-3 py-1">
                <button
                  type="button"
                  class="font-semibold transition"
                  :class="!selectedFunctions.includes(func.id) && 'text-muted'"
                  :style="selectedFunctions.includes(func.id) ? { color: getColor(func.id).icon } : undefined"
                  @click.stop="runSingleFunction(func.id)"
                  :disabled="analyzeState.running"
                >
                  仅运行此项
                </button>
              </span>
            </div>
          </button>
        </div>
      </AnalysisSectionCard>

      <AnalysisSectionCard
        title="日志与执行"
        description="系统会按所选维度创建后台任务，并按真实 worker 状态持续刷新执行阶段。"
      >
        <div class="space-y-5">
          <BasicAnalysisExecutionPanel
            :tasks="analyzeTasks"
            :worker="analyzeWorkerState"
            :loading="analyzeTaskState.loading"
            :error="analyzeTaskState.error"
            :notice="analyzeTaskState.notice"
            empty-label="准备就绪。配置完成后点击下方按钮创建后台分析任务。"
          />

          <div class="flex flex-col gap-3 rounded-[1.5rem] border border-soft bg-surface-muted px-4 py-4 sm:flex-row sm:items-center sm:justify-between">
            <p class="text-sm text-secondary">
              <span v-if="analyzeState.running" class="font-semibold text-secondary">后台任务已启动，可留在当前页查看，也可稍后回来。</span>
              <span v-else>确认配置后即可创建当前范围的分析任务。</span>
            </p>
            <button
              type="submit"
              class="btn-primary inline-flex min-w-[170px] items-center justify-center gap-2 rounded-full px-5 py-3 text-base"
              :disabled="analyzeState.running || !selectedFunctions.length"
            >
              <ArrowPathIcon v-if="analyzeState.running" class="h-5 w-5 animate-spin" />
              <span>{{ analyzeState.running ? '任务执行中' : `创建分析任务 (${selectedFunctions.length})` }}</span>
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
import BasicAnalysisExecutionPanel from '../../../components/analysis/BasicAnalysisExecutionPanel.vue'
import AppSelect from '../../../components/AppSelect.vue'
import { useBasicAnalysis } from '../../../composables/useBasicAnalysis'

const {
  topicsState,
  topicOptions,
  loadTopics,
  analyzeForm,
  analyzeState,
  analyzeTaskState,
  analyzeWorkerState,
  analyzeTasks,
  analysisFunctions,
  selectedFunctions,
  selectAll,
  clearSelection,
  runSelectedFunctions,
  runSingleFunction,
  rebuildAiSummary,
  changeTopic,
  availableRange
} = useBasicAnalysis()

const dimensionActions = [
  {
    label: '重新生成AI摘要',
    variant: 'ghost',
    onClick: rebuildAiSummary
  },
  {
    label: '全选',
    variant: 'pill',
    onClick: selectAll
  },
  {
    label: '清空',
    variant: 'pill',
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

// 莫兰迪色调色表
const colorMap = {
  attitude: { border: '#8aafa0', bg: '#f0f6f4', iconBg: '#e0ebe8', icon: '#8aafa0' },
  classification: { border: '#9abbcc', bg: '#f0f4f6', iconBg: '#e8eef2', icon: '#9abbcc' },
  geography: { border: '#d0b890', bg: '#f4f0e8', iconBg: '#e8e4d8', icon: '#d0b890' },
  keywords: { border: '#b8b0d0', bg: '#f4f2f6', iconBg: '#eceaf0', icon: '#b8b0d0' },
  publishers: { border: '#d0aa9a', bg: '#f4f0ee', iconBg: '#e8e4e0', icon: '#d0aa9a' },
  trends: { border: '#9aaec0', bg: '#f0f4f6', iconBg: '#e4e8ec', icon: '#9aaec0' },
  volume: { border: '#8ac0b0', bg: '#f0f6f4', iconBg: '#e4ece8', icon: '#8ac0b0' }
}

const getIcon = (id) => iconMap[id] || SparklesIcon
const getColor = (id) => colorMap[id] || colorMap.volume

const topicSelectOptions = computed(() =>
  topicOptions.value.map(option => ({ value: option, label: option }))
)

const handleTopicChange = (value) => {
  analyzeForm.topic = value
  changeTopic(value)
}

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
