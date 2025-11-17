<template>
  <div class="space-y-8">
    <section class="card-surface relative overflow-hidden space-y-6 p-6">

      <div
        v-if="fetchState.loading"
        class="pointer-events-none absolute inset-0 z-10 flex flex-col items-center justify-center gap-3 bg-white/80 backdrop-blur-sm"
      >
        <ArrowPathIcon class="h-10 w-10 animate-spin text-primary" />
        <span class="text-sm font-medium text-secondary">正在拉取远程数据…</span>
      </div>
      <header class="flex flex-col gap-2">
        <p class="text-xs font-semibold uppercase tracking-[0.4em] text-muted">Step 1</p>
        <h2 class="text-2xl font-semibold text-primary">拉取远程数据</h2>
        <p class="text-sm text-secondary">
          选择专题与时间区间后，系统会为你准备好对应的原始数据，用于后续分析。
        </p>
      </header>

      <form class="space-y-5 text-sm" @submit.prevent="runFetch">
        <div class="grid gap-4 md:grid-cols-3">
          <label class="space-y-2 text-secondary md:col-span-3">
            <div class="flex items-center justify-between gap-2">
              <span class="text-xs font-semibold text-muted">专题 Topic *</span>
              <button
                type="button"
                class="inline-flex items-center gap-1 text-[11px] font-medium text-brand-600 hover:text-brand-700 disabled:cursor-default disabled:opacity-60"
                :disabled="topicsState.loading"
                @click="loadTopics"
              >
                <ArrowPathIcon
                  class="h-3 w-3"
                  :class="topicsState.loading ? 'animate-spin text-brand-600' : 'text-brand-600'"
                />
                <span>{{ topicsState.loading ? '刷新中…' : '刷新专题' }}</span>
              </button>
            </div>
            <select
              v-model="fetchForm.topic"
              class="input"
              :disabled="topicsState.loading || !topicOptions.length"
              required
            >
              <option value="" disabled>请选择远程专题</option>
              <option v-for="option in topicOptions" :key="option" :value="option">{{ option }}</option>
            </select>
            <p class="text-xs text-muted">
              <span v-if="topicsState.loading">正在读取专题列表…</span>
              <span v-else-if="topicsState.error" class="text-danger">{{ topicsState.error }}</span>
              <span v-else>下拉列表展示当前可用的远程专题，可在下方操作区刷新。</span>
            </p>
          </label>
          <label class="space-y-2 text-secondary">
            <span class="text-xs font-semibold text-muted">开始日期 Start *</span>
            <input v-model="fetchForm.start" type="date" class="input" required />
            <p class="text-xs text-muted">选择数据范围的起始日期（包含当天）。</p>
          </label>
          <label class="space-y-2 text-secondary">
            <span class="text-xs font-semibold text-muted">结束日期 End *</span>
            <input v-model="fetchForm.end" type="date" class="input" required />
            <p class="text-xs text-muted">选择数据范围的结束日期（包含当天）。</p>
          </label>
        </div>
        <p
          class="text-xs"
          :class="availableRange.error ? 'text-danger' : 'text-muted'"
        >
          <template v-if="!fetchForm.topic">
            请选择专题以查看可用日期范围。
          </template>
          <template v-else-if="availableRange.loading">
            正在查询该专题的可用日期范围…
          </template>
          <template v-else-if="availableRange.error">
            当前无法获取可用日期：{{ availableRange.error }}
          </template>
          <template v-else-if="availableRange.start && availableRange.end">
            当前可用数据时间：{{ availableRange.start }} → {{ availableRange.end }}
          </template>
          <template v-else>
            当前专题暂未检测到可用时间范围，请确认数据是否已经准备完成。
          </template>
        </p>
        <div
          class="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-dashed border-soft bg-surface-muted px-4 py-3 text-xs md:text-sm"
        >
          <span class="text-[11px] text-muted md:text-xs">
            本次拉取会更新当前专题在选定时间内的数据，请确认时间范围设置正确。
          </span>
          <div class="flex flex-wrap items-center gap-2">
            <button type="button" class="btn-ghost" :disabled="fetchState.loading" @click="resetFetchForm">
              重置
            </button>
            <button type="submit" class="btn-primary" :disabled="fetchState.loading">
              {{ fetchState.loading ? '处理中…' : '开始拉取' }}
            </button>
          </div>
        </div>
      </form>
      <AnalysisLogList :logs="fetchLogs" empty-label="暂无提取记录。" />
    </section>

    <section class="card-surface space-y-6 p-6">
      <header class="flex flex-col gap-2">
        <p class="text-xs font-semibold uppercase tracking-[0.4em] text-muted">Step 2</p>
        <h2 class="text-2xl font-semibold text-primary">运行分析函数</h2>
        <p class="text-sm text-secondary">挑选需要的函数，系统会在相同专题与时间范围内生成基础分析结果。</p>
      </header>

      <form class="space-y-5 text-sm" @submit.prevent="runSelectedFunctions">
        <div class="grid gap-4 md:grid-cols-3">
          <label class="space-y-2 text-secondary">
            <span class="text-xs font-semibold text-muted">专题 Topic *</span>
            <select
              v-model="analyzeForm.topic"
              class="input"
              :disabled="topicsState.loading || !topicOptions.length"
              required
            >
              <option value="" disabled>请选择远程专题</option>
              <option v-for="option in topicOptions" :key="`analyze-${option}`" :value="option">
                {{ option }}
              </option>
            </select>
            <p class="text-xs text-muted">默认为上方已选专题，也可以单独调整。</p>
          </label>
          <label class="space-y-2 text-secondary">
            <span class="text-xs font-semibold text-muted">开始日期 Start *</span>
            <input v-model="analyzeForm.start" type="date" class="input" required />
          </label>
          <label class="space-y-2 text-secondary">
            <span class="text-xs font-semibold text-muted">结束日期 End *</span>
            <input v-model="analyzeForm.end" type="date" class="input" required />
          </label>
        </div>
        <div class="flex flex-wrap gap-3 text-sm">
          <button type="submit" class="btn-primary" :disabled="analyzeState.running">
            {{ analyzeState.running ? '执行中…' : '运行所选分析' }}
          </button>
          <button type="button" class="btn-secondary" :disabled="analyzeState.running" @click="selectAll">
            全部选择
          </button>
          <button type="button" class="btn-secondary" :disabled="analyzeState.running" @click="clearSelection">
            取消全选
          </button>
          <span class="text-muted">运行成功后可在“查看分析”页刷新结果。</span>
        </div>
      </form>

      <div class="rounded-2xl border border-soft bg-surface p-4">
        <div class="mb-3 flex items-center justify-between gap-3 text-xs text-muted">
          <span>在下方勾选需要的分析项，系统会在相同专题与时间范围内统一处理。</span>
          <span class="hidden whitespace-nowrap md:inline">
            已选 {{ selectedFunctions.length }} / {{ analysisFunctions.length }}
          </span>
        </div>
        <div class="grid gap-3 md:grid-cols-2">
          <article
            v-for="func in analysisFunctions"
            :key="func.id"
            class="group flex items-start justify-between gap-4 rounded-xl border border-soft bg-surface-muted/60 px-4 py-3 transition hover:border-brand-soft hover:bg-surface-muted"
          >
            <label class="flex flex-1 cursor-pointer flex-col gap-1 text-sm">
              <span class="flex items-center gap-2 text-primary">
                <input
                  type="checkbox"
                  :value="func.id"
                  class="h-4 w-4 rounded border-soft text-brand-600 focus:ring-brand-500"
                  v-model="selectedFunctions"
                  :disabled="analyzeState.running"
                />
                <span class="font-semibold">{{ func.label }}</span>
              </span>
              <span class="text-xs text-secondary">{{ func.description }}</span>
            </label>
            <button
              type="button"
              class="btn-ghost px-3 py-1 text-xs text-brand-600 group-hover:bg-brand-soft/20"
              :disabled="analyzeState.running"
              @click="runSingleFunction(func.id)"
            >
              单独运行
            </button>
          </article>
        </div>
      </div>

      <AnalysisLogList :logs="analyzeLogs" empty-label="暂无分析调度记录。" />
    </section>
  </div>
</template>

<script setup>
import { onMounted } from 'vue'
import { ArrowPathIcon, PlayCircleIcon } from '@heroicons/vue/24/outline'
import { useBasicAnalysis } from '../../../composables/useBasicAnalysis'
import AnalysisLogList from '../../../components/analysis/AnalysisLogList.vue'

const {
  topicsState,
  topicOptions,
  fetchForm,
  availableRange,
  fetchState,
  fetchLogs,
  runFetch,
  resetFetchForm,
  loadTopics,
  analyzeForm,
  analyzeState,
  analyzeLogs,
  analysisFunctions,
  selectedFunctions,
  selectAll,
  clearSelection,
  runSelectedFunctions,
  runSingleFunction
} = useBasicAnalysis()

onMounted(() => {
  if (!topicsState.options?.length) {
    loadTopics()
  }
})
</script>
