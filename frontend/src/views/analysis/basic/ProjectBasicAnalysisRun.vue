<template>
  <div class="space-y-8">
    <section class="card-surface space-y-6 p-6">
      <header class="flex flex-col gap-2">
        <p class="text-xs font-semibold uppercase tracking-[0.4em] text-muted">Step 1</p>
        <h2 class="text-2xl font-semibold text-primary">拉取远程数据</h2>
        <p class="text-sm text-secondary">
          选择专题与时间区间后触发 Fetch 接口，把远程数据库的数据同步到本地分析目录。
        </p>
      </header>
      <form class="space-y-5 text-sm" @submit.prevent="runFetch">
        <div class="grid gap-4 md:grid-cols-3">
          <label class="space-y-2 text-secondary">
            <span class="text-xs font-semibold text-muted">专题 Topic *</span>
            <div class="flex gap-2">
              <select
                v-model="fetchForm.topic"
                class="input"
                :disabled="topicsState.loading || !topicOptions.length"
                required
              >
                <option value="" disabled>请选择远程专题</option>
                <option v-for="option in topicOptions" :key="option" :value="option">{{ option }}</option>
              </select>
              <button
                type="button"
                class="btn-secondary whitespace-nowrap px-3 py-2 text-xs"
                :disabled="topicsState.loading"
                @click="loadTopics"
              >
                {{ topicsState.loading ? '加载中…' : '刷新' }}
              </button>
            </div>
            <p class="text-xs text-muted">
              <span v-if="topicsState.loading">正在读取专题列表…</span>
              <span v-else-if="topicsState.error" class="text-danger">{{ topicsState.error }}</span>
              <span v-else>下拉列表展示当前可用的远程专题。</span>
            </p>
          </label>
          <label class="space-y-2 text-secondary">
            <span class="text-xs font-semibold text-muted">开始日期 Start *</span>
            <input v-model="fetchForm.start" type="date" class="input" required />
          </label>
          <label class="space-y-2 text-secondary">
            <span class="text-xs font-semibold text-muted">结束日期 End *</span>
            <input v-model="fetchForm.end" type="date" class="input" required />
          </label>
        </div>
        <p
          class="text-xs"
          :class="availableRange.error ? 'text-danger' : 'text-muted'"
        >
          <template v-if="!fetchForm.topic">
            请选择远程专题以查看可用日期区间。
          </template>
          <template v-else-if="availableRange.loading">
            正在查询该专题的可用日期区间…
          </template>
          <template v-else-if="availableRange.error">
            无法获取可用日期：{{ availableRange.error }}
          </template>
          <template v-else-if="availableRange.start && availableRange.end">
            可用数据区间：{{ availableRange.start }} → {{ availableRange.end }}
          </template>
          <template v-else>
            当前专题暂无 published_at 日期，可能尚未写入远程数据。
          </template>
        </p>
        <div class="flex flex-wrap gap-3 text-sm">
          <button type="submit" class="btn-primary" :disabled="fetchState.loading">
            {{ fetchState.loading ? '提取中…' : '执行 Fetch' }}
          </button>
          <button type="button" class="btn-ghost" :disabled="fetchState.loading" @click="resetFetchForm">
            重置
          </button>
          <span class="text-muted">执行后稍等片刻即可继续分析。</span>
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

      <div class="grid gap-4 md:grid-cols-2">
        <article
          v-for="func in analysisFunctions"
          :key="func.id"
          class="rounded-2xl border border-soft bg-surface p-4"
        >
          <div class="flex items-start justify-between gap-4">
            <label class="flex flex-col gap-1 text-sm">
              <span class="flex items-center gap-2 text-primary">
                <input
                  type="checkbox"
                  :value="func.id"
                  class="rounded border-soft"
                  v-model="selectedFunctions"
                  :disabled="analyzeState.running"
                />
                <span class="font-semibold">{{ func.label }}</span>
              </span>
              <span class="text-xs text-secondary">{{ func.description }}</span>
            </label>
            <button
              type="button"
              class="btn-secondary px-3 py-1 text-xs"
              :disabled="analyzeState.running"
              @click="runSingleFunction(func.id)"
            >
              单独运行
            </button>
          </div>
        </article>
      </div>

      <AnalysisLogList :logs="analyzeLogs" empty-label="暂无 Analyze 调度记录。" />
    </section>
  </div>
</template>

<script setup>
import { onMounted } from 'vue'
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
