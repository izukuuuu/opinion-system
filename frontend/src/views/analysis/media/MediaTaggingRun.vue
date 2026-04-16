<template>
  <div class="space-y-6 pb-12">
    <AnalysisPageHeader
      eyebrow="媒体识别与打标"
      title="运行识别"
      description="选择专题和时间范围，先把该区间里的媒体候选整理出来。"
      :meta-items="metaItems"
    />

    <form class="space-y-6" @submit.prevent="runMediaTagging">
      <AnalysisSectionCard
        title="识别范围"
        description="先确定专题和时间区间。系统会自动带出当前专题已有的本地可用范围。"
      >
        <div class="grid gap-6 lg:grid-cols-[minmax(240px,0.95fr)_minmax(0,1.3fr)]">
          <label class="space-y-2 text-secondary">
            <div class="flex items-center justify-between gap-3">
              <span class="text-xs font-semibold uppercase tracking-[0.2em] text-muted">专题</span>
              <button
                type="button"
                class="analysis-toolbar__action analysis-toolbar__action--ghost px-3 py-1.5 text-xs"
                :disabled="topicsState.loading"
                @click="loadTopics"
              >
                <ArrowPathIcon class="h-4 w-4" :class="{ 'animate-spin': topicsState.loading }" />
                <span>{{ topicsState.loading ? '刷新中…' : '刷新专题' }}</span>
              </button>
            </div>
            <AppSelect
              :options="topicSelectOptions"
              :value="runForm.topic"
              :disabled="topicsState.loading || !topicOptions.length"
              @change="changeTopic"
            />
            <p v-if="topicsState.error" class="text-xs text-danger">{{ topicsState.error }}</p>
          </label>

          <div class="space-y-3">
            <span class="text-xs font-semibold uppercase tracking-[0.2em] text-muted">时间范围</span>
            <div class="grid gap-3 sm:grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] sm:items-center">
              <label class="space-y-2 text-secondary">
                <span class="text-xs font-medium text-muted">开始日期</span>
                <input v-model="runForm.start" type="date" class="input h-12 w-full rounded-2xl" required />
              </label>
              <span class="hidden text-muted sm:inline">→</span>
              <label class="space-y-2 text-secondary">
                <span class="text-xs font-medium text-muted">结束日期</span>
                <input v-model="runForm.end" type="date" class="input h-12 w-full rounded-2xl" required />
              </label>
            </div>

            <div class="rounded-[1.4rem] border border-soft bg-surface-muted px-4 py-3 text-sm text-secondary">
              <p v-if="availableRange.loading" class="animate-pulse">正在同步可用时间范围…</p>
              <p v-else-if="availableRange.error" class="text-danger">{{ availableRange.error }}</p>
              <div v-else class="space-y-1">
                <p>建议范围：{{ availableRange.start || '--' }} 至 {{ availableRange.end || '--' }}</p>
                <p class="text-xs text-muted">媒体识别会直接读取这个时间区间内已落到本地的原始语料。</p>
              </div>
            </div>
          </div>
        </div>
      </AnalysisSectionCard>

      <AnalysisSectionCard
        title="这次会做什么"
        description="V1 只做确定性整理和字典匹配，媒体属性仍由你来确认。"
        tone="soft"
      >
        <div class="grid gap-4 lg:grid-cols-3">
          <article
            v-for="item in runHighlights"
            :key="item.title"
            class="card-surface px-5 py-5"
          >
            <div class="inline-flex h-10 w-10 items-center justify-center rounded-2xl bg-brand-soft text-brand-700">
              <component :is="item.icon" class="h-5 w-5" />
            </div>
            <h3 class="mt-4 text-base font-semibold text-primary">{{ item.title }}</h3>
            <p class="mt-2 text-sm leading-6 text-secondary">{{ item.description }}</p>
          </article>
        </div>
      </AnalysisSectionCard>

      <AnalysisSectionCard
        title="任务状态"
        description="后台会持续整理候选媒体，这里会同步显示实际执行进度。"
      >
        <div class="space-y-5">
          <BasicAnalysisExecutionPanel
            :tasks="tasks"
            :worker="workerState"
            :loading="taskState.loading"
            :error="taskState.error"
            :notice="taskState.notice"
            empty-label="准备就绪。点击下方按钮后，这里会显示识别任务的实时状态。"
          />

          <div class="rounded-[1.5rem] border border-soft bg-surface-muted px-4 py-4">
            <div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <div class="space-y-1">
                <p class="text-sm font-medium text-primary">
                  {{ runState.running ? '任务已启动，可留在当前页继续查看进度。' : '确认范围后即可创建一次新的媒体识别任务。' }}
                </p>
                <p class="text-sm text-secondary">结果生成后，会自动出现在“查看结果”的历史记录中。</p>
              </div>
              <button
                type="submit"
                class="btn-primary inline-flex min-w-[170px] items-center justify-center gap-2 rounded-full px-5 py-3"
                :disabled="runState.running"
              >
                <ArrowPathIcon v-if="runState.running" class="h-5 w-5 animate-spin" />
                <span>{{ runState.running ? '识别进行中' : '启动识别任务' }}</span>
              </button>
            </div>
          </div>
        </div>
      </AnalysisSectionCard>
    </form>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import {
  ArrowPathIcon,
  BookOpenIcon,
  MegaphoneIcon,
  SwatchIcon,
  TableCellsIcon
} from '@heroicons/vue/24/outline'
import AppSelect from '../../../components/AppSelect.vue'
import AnalysisPageHeader from '../../../components/analysis/AnalysisPageHeader.vue'
import AnalysisSectionCard from '../../../components/analysis/AnalysisSectionCard.vue'
import BasicAnalysisExecutionPanel from '../../../components/analysis/BasicAnalysisExecutionPanel.vue'
import { useMediaTagging } from '../../../composables/useMediaTagging'

const {
  topicsState,
  topicOptions,
  runForm,
  availableRange,
  runState,
  taskState,
  workerState,
  tasks,
  loadTopics,
  changeTopic,
  runMediaTagging
} = useMediaTagging()

const topicSelectOptions = computed(() =>
  topicOptions.value.map((item) => ({ value: item, label: item }))
)

const metaItems = computed(() => {
  const items = []
  if (runForm.topic) {
    items.push({ label: '当前专题', value: runForm.topic, icon: MegaphoneIcon })
  }
  if (runForm.start) {
    items.push({
      label: '识别范围',
      value: `${runForm.start} 至 ${runForm.end || runForm.start}`,
      icon: TableCellsIcon
    })
  }
  return items
})

const runHighlights = [
  {
    title: '聚合发布者名称',
    description: '从原始语料的发布者和作者字段中去重归并，得到稳定的媒体候选名单。',
    icon: MegaphoneIcon
  },
  {
    title: '补齐样本上下文',
    description: '统计发布量、最近发布时间、来源平台，并抽取样本标题和链接供人工确认。',
    icon: BookOpenIcon
  },
  {
    title: '对齐共享字典',
    description: '按名称和别名做确定性匹配，帮助你更快完成正式标签维护。',
    icon: SwatchIcon
  }
]
</script>
