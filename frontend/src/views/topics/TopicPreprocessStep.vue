<template>
  <div class="space-y-8">
    <header class="flex flex-wrap items-center justify-between gap-3">
      <div class="space-y-1">
        <h1 class="text-2xl font-semibold text-primary">数据预处理</h1>
        <p class="text-sm text-secondary">按日期依次执行 Merge、Clean、Filter，生成标准化结果。</p>
      </div>
      <div class="flex items-center gap-2 rounded-full bg-brand-soft px-3 py-1 text-xs font-semibold text-brand-600">
        <FunnelIcon class="h-4 w-4" />
        <span>步骤 2 · 预处理</span>
      </div>
    </header>

    <section class="card-surface space-y-6 p-6">
      <header class="space-y-2">
        <h2 class="text-xl font-semibold text-primary">准备参数</h2>
        <p class="text-sm text-secondary">
          请填写专题名称与专题所属日期。系统将基于该日期定位上传的原始数据文件。
        </p>
      </header>
      <form class="grid gap-4 md:grid-cols-2">
        <label class="space-y-1 text-sm">
          <span class="font-medium text-secondary">专题名称</span>
          <input
            v-model.trim="topic"
            type="text"
            required
            class="w-full rounded-2xl border border-soft px-4 py-2 text-sm shadow-sm transition focus:border-brand-soft focus:outline-none focus:ring-2 focus:ring-brand-200"
            placeholder="例如：2024-lianghui"
          />
        </label>
        <label class="space-y-1 text-sm">
          <span class="font-medium text-secondary">专题日期</span>
          <input
            v-model="date"
            type="date"
            required
            class="w-full rounded-2xl border border-soft px-4 py-2 text-sm shadow-sm transition focus:border-brand-soft focus:outline-none focus:ring-2 focus:ring-brand-200"
          />
        </label>
      </form>
      <p v-if="parameterError" class="rounded-2xl bg-rose-100 px-4 py-2 text-sm text-rose-600">{{ parameterError }}</p>
    </section>

    <section class="card-surface space-y-5 p-6">
      <header class="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 class="text-xl font-semibold text-primary">执行预处理步骤</h2>
          <p class="text-sm text-secondary">按顺序执行 Merge → Clean → Filter，或单独运行其中某个步骤。</p>
        </div>
        <button
          type="button"
          class="inline-flex items-center gap-2 rounded-full border border-brand-soft px-4 py-2 text-sm font-semibold text-brand-600 transition hover:bg-brand-soft focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-600 disabled:cursor-not-allowed disabled:opacity-60"
          :disabled="pipeline.running"
          @click="runPipeline"
        >
          <SparklesIcon class="h-4 w-4" />
          <span>{{ pipeline.running ? '执行中…' : '一键执行 Pipeline' }}</span>
        </button>
      </header>

      <div class="grid gap-5 lg:grid-cols-3">
        <article
          v-for="operation in operations"
          :key="operation.key"
          class="flex flex-col gap-4 rounded-3xl border border-brand-soft bg-surface-muted p-5"
        >
          <div class="flex items-center gap-3">
            <span class="flex h-10 w-10 items-center justify-center rounded-2xl bg-brand-soft text-brand-600">
              <component :is="operation.icon" class="h-5 w-5" />
            </span>
            <div>
              <h3 class="text-base font-semibold text-primary">{{ operation.title }}</h3>
              <p class="text-xs uppercase tracking-[0.2em] text-muted">{{ operation.subtitle }}</p>
            </div>
          </div>
          <p class="text-sm leading-relaxed text-secondary">
            {{ operation.description }}
          </p>
          <button
            type="button"
            class="inline-flex items-center justify-center rounded-full bg-brand-600 px-4 py-1.5 text-sm font-semibold text-white shadow transition hover:bg-brand-500 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-600 disabled:cursor-not-allowed disabled:bg-brand-300 disabled:text-white/70"
            :disabled="statuses[operation.key].running"
            @click="runOperation(operation.key)"
          >
            <span v-if="statuses[operation.key].running">执行中…</span>
            <span v-else>执行 {{ operation.label }}</span>
          </button>
          <p
            v-if="statuses[operation.key].message"
            :class="[
              'text-sm rounded-2xl px-3 py-1.5',
              statuses[operation.key].success ? 'bg-emerald-100 text-emerald-600' : 'bg-rose-100 text-rose-600'
            ]"
          >
            {{ statuses[operation.key].message }}
          </p>
        </article>
      </div>

      <p v-if="pipeline.message" :class="[
        'rounded-2xl px-4 py-2 text-sm',
        pipeline.success ? 'bg-emerald-100 text-emerald-600' : 'bg-rose-100 text-rose-600'
      ]">
        {{ pipeline.message }}
      </p>
    </section>
  </div>
</template>

<script setup>
import { reactive, ref } from 'vue'
import {
  FunnelIcon,
  ArrowPathRoundedSquareIcon,
  TrashIcon,
  AdjustmentsHorizontalIcon,
  SparklesIcon
} from '@heroicons/vue/24/outline'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api'

const topic = ref('')
const date = ref('')
const parameterError = ref('')

const operations = [
  {
    key: 'merge',
    label: 'Merge',
    title: '合并 Merge',
    subtitle: 'Step 01',
    description: '整合 TRS 导出的多份原始 Excel，生成标准化的主题数据表。',
    endpoint: `${API_BASE_URL}/merge`,
    icon: ArrowPathRoundedSquareIcon
  },
  {
    key: 'clean',
    label: 'Clean',
    title: '清洗 Clean',
    subtitle: 'Step 02',
    description: '执行数据清洗，补齐字段与格式，移除重复与异常值，确保数据稳定。',
    endpoint: `${API_BASE_URL}/clean`,
    icon: TrashIcon
  },
  {
    key: 'filter',
    label: 'Filter',
    title: '筛选 Filter',
    subtitle: 'Step 03',
    description: '调用 AI 相关性筛选模型，保留与专题高度关联的数据。',
    endpoint: `${API_BASE_URL}/filter`,
    icon: AdjustmentsHorizontalIcon
  }
]

const statuses = reactive({
  merge: { running: false, success: null, message: '' },
  clean: { running: false, success: null, message: '' },
  filter: { running: false, success: null, message: '' }
})

const pipeline = reactive({
  running: false,
  success: null,
  message: ''
})

const ensureParameters = () => {
  if (!topic.value || !date.value) {
    parameterError.value = '请填写专题名称与日期后再执行操作'
    return false
  }
  parameterError.value = ''
  return true
}

const runOperation = async (key) => {
  if (!ensureParameters()) return
  const operation = operations.find((item) => item.key === key)
  if (!operation) return

  const state = statuses[key]
  state.running = true
  state.message = ''
  state.success = null

  try {
    const response = await fetch(operation.endpoint, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ topic: topic.value, date: date.value })
    })
    const result = await response.json()
    const ok = response.ok && result.status !== 'error'
    state.success = ok
    state.message = ok ? `${operation.label} 执行成功` : (result.message || `${operation.label} 执行失败`)
  } catch (err) {
    state.success = false
    state.message = err instanceof Error ? err.message : `${operation.label} 执行失败`
  } finally {
    state.running = false
  }
}

const runPipeline = async () => {
  if (!ensureParameters()) return
  pipeline.running = true
  pipeline.message = ''
  pipeline.success = null

  try {
    const response = await fetch(`${API_BASE_URL}/pipeline`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ topic: topic.value, date: date.value })
    })
    const result = await response.json()
    const ok = response.ok && result.status !== 'error'
    pipeline.success = ok
    pipeline.message = ok ? 'Pipeline 执行成功，所有步骤均已完成。' : (result.message || 'Pipeline 执行失败')
  } catch (err) {
    pipeline.success = false
    pipeline.message = err instanceof Error ? err.message : 'Pipeline 执行失败'
  } finally {
    pipeline.running = false
  }
}
</script>
