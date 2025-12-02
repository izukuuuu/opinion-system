<template>
  <div class="space-y-4">
    <section class="card-surface space-y-6 p-6">
      <header class="flex flex-col gap-2">
        <h2 class="text-2xl font-semibold text-primary">运行分析函数</h2>
      </header>

      <form class="space-y-5 text-sm" @submit.prevent="runSelectedFunctions">
        <div class="grid gap-4 md:grid-cols-3">
          <label class="space-y-2 text-secondary">
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
              v-model="analyzeForm.topic"
              class="input"
              :disabled="topicsState.loading || !topicOptions.length"
              required
              @change="changeTopic($event.target.value)"
            >
              <option value="" disabled>请选择远程专题</option>
              <option v-for="option in topicOptions" :key="`analyze-${option}`" :value="option">
                {{ option }}
              </option>
            </select>
            <p class="text-xs text-muted">
              <span v-if="topicsState.loading">正在读取专题列表…</span>
              <span v-else-if="topicsState.error" class="text-danger">{{ topicsState.error }}</span>
              <span v-else>修改专题后会自动检查并同步所需数据。</span>
            </p>
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
                <span class="relative inline-flex h-4 w-4 shrink-0">
                  <input
                    type="checkbox"
                    :value="func.id"
                    class="checkbox-custom"
                    v-model="selectedFunctions"
                    :disabled="analyzeState.running"
                  />
                  <CheckIcon
                    v-if="selectedFunctions.includes(func.id)"
                    class="pointer-events-none absolute inset-0 h-4 w-4 text-white"
                  />
                </span>
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

      <AnalysisLogList
        :logs="combinedLogs"
        empty-label="暂无执行记录，运行分析时会自动触发数据准备与分析进度。"
      />
    </section>
  </div>
</template>

<script setup>
import { computed, onMounted } from 'vue'
import { ArrowPathIcon } from '@heroicons/vue/24/outline'
import { CheckIcon } from '@heroicons/vue/24/solid'
import { useBasicAnalysis } from '../../../composables/useBasicAnalysis'
import AnalysisLogList from '../../../components/analysis/AnalysisLogList.vue'

const {
  topicsState,
  topicOptions,
  fetchState,
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
  changeTopic
} = useBasicAnalysis()

const combinedLogs = computed(() => [...(fetchLogs?.value || []), ...(analyzeLogs?.value || [])])

onMounted(() => {
  if (!topicsState.options?.length) {
    loadTopics()
  }
})
</script>
