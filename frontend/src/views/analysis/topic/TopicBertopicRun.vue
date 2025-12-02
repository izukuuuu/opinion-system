<template>
  <div class="space-y-8">
    <header class="rounded-2xl border border-soft bg-surface p-6 shadow-sm">
      <div class="flex flex-col gap-2">
        <p class="text-xs font-medium uppercase tracking-wide text-secondary">主题分析 · BERTopic</p>
        <h1 class="text-2xl font-semibold text-primary">运行 BERTopic + Qwen 主题分析</h1>
        <p class="text-sm text-secondary">
          选择专题与时间区间，触发后端的 BERTopic 分析流程，并生成 1~5 号 JSON 结果文件。
        </p>
      </div>
    </header>

    <section class="rounded-2xl border border-soft bg-surface p-6 shadow-sm">
      <h2 class="text-lg font-semibold text-primary">分析参数</h2>
      <form class="mt-6 space-y-6" @submit.prevent="handleRun">
        <div class="grid gap-4 md:grid-cols-2">
          <label class="flex flex-col gap-1 text-sm font-medium text-primary">
            专题 Bucket（必填）
            <div class="relative">
              <select
                v-model="form.topic"
                class="input"
                :disabled="topicsLoading"
              >
                <option value="" disabled>请选择专题...</option>
                <option v-for="topic in topics" :key="topic.bucket" :value="topic.bucket">
                  {{ topic.name }}
                </option>
              </select>
              <button
                v-if="!topicsLoading"
                type="button"
                class="absolute right-2 top-1/2 -translate-y-1/2 rounded px-2 py-1 text-xs text-secondary hover:bg-surface-muted"
                @click="loadTopics"
                title="刷新专题列表"
              >
                🔄
              </button>
              <span v-if="topicsLoading" class="absolute right-2 top-1/2 -translate-y-1/2 text-xs text-secondary">加载中...</span>
            </div>
          </label>
          <label class="flex flex-col gap-1 text-sm font-medium text-primary">
            开始日期（YYYY-MM-DD）
            <input
              v-model.trim="form.startDate"
              type="date"
              class="input"
            />
          </label>
          <label class="flex flex-col gap-1 text-sm font-medium text-primary">
            结束日期（可选，默认同开始）
            <input
              v-model.trim="form.endDate"
              type="date"
              class="input"
            />
          </label>
          <label class="flex flex-col gap-1 text-sm font-medium text-primary">
            fetch 目录（可选）
            <input
              v-model.trim="form.fetchDir"
              type="text"
              placeholder="F:/opinion-system/backend/data/projects/<topic>/fetch/<range>"
              class="input"
            />
          </label>
          <label class="flex flex-col gap-1 text-sm font-medium text-primary">
            自定义 userdict（可选）
            <input
              v-model.trim="form.userdict"
              type="text"
              placeholder="F:/opinion-system/backend/configs/userdict.txt"
              class="input"
            />
          </label>
          <label class="flex flex-col gap-1 text-sm font-medium text-primary">
            自定义 stopwords（可选）
            <input
              v-model.trim="form.stopwords"
              type="text"
              placeholder="F:/opinion-system/backend/configs/stopwords.txt"
              class="input"
            />
          </label>
        </div>

        <div class="flex flex-wrap gap-3">
          <button
            type="submit"
            class="btn btn-primary"
            :disabled="!canSubmit"
          >
            {{ state.running ? '正在运行…' : '运行 BERTopic 分析' }}
          </button>
          <button
            type="button"
            class="btn btn-soft"
            @click="resetOptionalFields"
            :disabled="state.running"
          >
            清空可选参数
          </button>
          <button
            type="button"
            class="btn btn-ghost"
            @click="resetAll"
            :disabled="state.running"
          >
            重置全部
          </button>
        </div>
      </form>
    </section>

    <section v-if="state.error" class="rounded-2xl border border-red-200 bg-red-50/70 p-5 text-red-700">
      <p class="font-medium">运行失败</p>
      <p class="text-sm mt-1">{{ state.error }}</p>
    </section>

    <section v-if="state.result" class="result-section">
      <div class="result-header">
        <div class="result-header__icon">✅</div>
        <div>
          <h2 class="result-header__title">运行结果</h2>
          <p class="result-header__subtitle">分析任务已成功完成</p>
        </div>
      </div>

      <div class="result-grid">
        <div class="result-card result-card--success">
          <div class="result-card__icon">📊</div>
          <div class="result-card__content">
            <p class="result-card__label">运行状态</p>
            <p class="result-card__value">{{ state.result.status === 'ok' ? '完成' : state.result.status }}</p>
            <p class="result-card__meta">operation: {{ state.result.operation }}</p>
          </div>
        </div>

        <div class="result-card result-card--info">
          <div class="result-card__icon">📅</div>
          <div class="result-card__content">
            <p class="result-card__label">时间区间</p>
            <p class="result-card__value">
              {{ state.result.data?.start_date || state.result.data?.start || '-' }}
              <span v-if="state.result.data?.end_date || state.result.data?.end" class="result-card__arrow">
                → {{ state.result.data?.end_date || state.result.data?.end }}
              </span>
            </p>
            <p class="result-card__meta">专题：{{ state.result.data?.topic || '-' }}</p>
          </div>
        </div>
      </div>

      <div class="result-info-box">
        <div class="result-info-box__header">
          <span class="result-info-box__icon">📁</span>
          <span class="result-info-box__title">生成的文件位置</span>
        </div>
        <div class="result-info-box__content">
          <div class="result-info-box__path">
            <code class="path-code">data/topic/{{ form.topic || state.result.data?.topic }}/&lt;日期范围&gt;/</code>
          </div>
          <p class="result-info-box__hint">
            💡 可在"查看结果"页面或数据目录中查看这些文件，完成可视化或二次分析
          </p>
        </div>
      </div>
    </section>

    <section v-if="lastPayload" class="request-section">
      <div class="request-header" @click="showRequestPayload = !showRequestPayload">
        <div class="request-header__left">
          <span class="request-header__icon">📤</span>
          <h2 class="request-header__title">最近一次请求体</h2>
        </div>
        <span class="request-header__toggle">{{ showRequestPayload ? '▼' : '▶' }}</span>
      </div>
      <div v-if="showRequestPayload" class="request-content">
        <pre class="request-code">{{ formattedPayload }}</pre>
      </div>
    </section>
  </div>
</template>

<script setup>
import { computed, reactive, ref, watch, onMounted } from 'vue'
import { useTopicBertopicAnalysis } from '@/composables/useTopicBertopicAnalysis'
import { useActiveProject } from '@/composables/useActiveProject'
import { useApiBase } from '@/composables/useApiBase'

const form = reactive({
  topic: '',
  startDate: '',
  endDate: '',
  fetchDir: '',
  userdict: '',
  stopwords: ''
})

const topics = ref([])
const topicsLoading = ref(false)
const showRequestPayload = ref(false)

const { state, lastPayload, runBertopicAnalysis, resetState } = useTopicBertopicAnalysis()
const { activeProjectName } = useActiveProject()
const { callApi } = useApiBase()

const loadTopics = async () => {
  topicsLoading.value = true
  try {
    const response = await callApi('/api/analysis/topic/bertopic/topics', { method: 'GET' })
    topics.value = response?.data?.topics || response?.topics || []
  } catch (error) {
    console.error('Failed to load topics:', error)
    topics.value = []
  } finally {
    topicsLoading.value = false
  }
}

onMounted(() => {
  loadTopics()
})

watch(
  activeProjectName,
  (value) => {
    if (value && !form.topic) {
      form.topic = value
    }
  },
  { immediate: true }
)

const canSubmit = computed(() => Boolean(form.topic.trim() && form.startDate.trim() && !state.running))

const formattedPayload = computed(() => JSON.stringify(lastPayload.value, null, 2))

const resetOptionalFields = () => {
  form.fetchDir = ''
  form.userdict = ''
  form.stopwords = ''
}

const resetAll = () => {
  const topic = form.topic
  form.topic = topic
  form.startDate = ''
  form.endDate = ''
  resetOptionalFields()
  resetState()
}

const handleRun = async () => {
  try {
    await runBertopicAnalysis({
      topic: form.topic,
      startDate: form.startDate,
      endDate: form.endDate,
      fetchDir: form.fetchDir,
      userdict: form.userdict,
      stopwords: form.stopwords
    })
  } catch {
    // 错误信息已由 state.error 承担
  }
}
</script>

<style scoped>
.input {
  width: 100%;
  border-radius: 0.75rem;
  border: 1px solid var(--color-border-soft);
  background-color: var(--color-surface);
  padding: 0.5rem 0.85rem;
  font-size: 0.95rem;
  transition: border-color 0.2s ease, box-shadow 0.2s ease;
}
.input:focus {
  border-color: var(--color-brand-500-hex);
  outline: none;
  box-shadow: 0 0 0 2px rgb(var(--color-brand-100) / 1);
}
.input:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
.relative .input {
  padding-right: 2.5rem;
}
.btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 0.75rem;
  padding: 0.5rem 1.25rem;
  font-size: 0.95rem;
  font-weight: 500;
  transition: background-color 0.2s ease, color 0.2s ease, border-color 0.2s ease;
}
.btn-primary {
  background-color: var(--color-brand-600-hex);
  color: #fff;
}
.btn-primary:hover:not(:disabled) {
  background-color: var(--color-brand-500-hex);
}
.btn-primary:disabled {
  cursor: not-allowed;
  background-color: rgb(var(--color-brand-200) / 1);
}
.btn-soft {
  border: 1px solid var(--color-border-soft);
  background-color: var(--color-surface);
  color: var(--color-text-primary);
}
.btn-soft:hover:not(:disabled) {
  background-color: rgb(var(--color-brand-100) / 0.4);
}
.btn-soft:disabled {
  cursor: not-allowed;
  color: var(--color-text-secondary);
}
.btn-ghost {
  color: var(--color-text-secondary);
  border: 1px solid transparent;
}
.btn-ghost:hover:not(:disabled) {
  color: var(--color-text-primary);
  background-color: rgb(var(--color-brand-100) / 0.4);
}
.btn-ghost:disabled {
  cursor: not-allowed;
  opacity: 0.5;
}

/* 运行结果部分样式 */
.result-section {
  border-radius: 1.5rem;
  border: 1px solid var(--color-border-soft);
  background: var(--color-surface);
  padding: 1.5rem;
  box-shadow: 0 10px 25px rgba(22, 30, 52, 0.05);
}

.result-header {
  display: flex;
  align-items: center;
  gap: 1rem;
  margin-bottom: 1.5rem;
  padding-bottom: 1rem;
  border-bottom: 2px solid var(--color-border-soft);
}

.result-header__icon {
  font-size: 2rem;
  line-height: 1;
}

.result-header__title {
  font-size: 1.25rem;
  font-weight: 600;
  color: var(--color-text-primary);
  margin: 0;
}

.result-header__subtitle {
  font-size: 0.875rem;
  color: var(--color-text-secondary);
  margin: 0.25rem 0 0 0;
}

.result-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: 1rem;
  margin-bottom: 1.5rem;
}

.result-card {
  display: flex;
  align-items: flex-start;
  gap: 1rem;
  padding: 1.25rem;
  border-radius: 1rem;
  border: 1px solid var(--color-border-soft);
  background: linear-gradient(135deg, rgba(255, 255, 255, 0.9) 0%, rgba(255, 255, 255, 0.7) 100%);
  transition: all 0.3s ease;
}

.result-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 8px 20px rgba(67, 97, 238, 0.15);
}

.result-card--success {
  border-left: 4px solid #10b981;
}

.result-card--info {
  border-left: 4px solid #4361ee;
}

.result-card__icon {
  font-size: 1.75rem;
  line-height: 1;
  flex-shrink: 0;
}

.result-card__content {
  flex: 1;
  min-width: 0;
}

.result-card__label {
  font-size: 0.75rem;
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--color-text-secondary);
  margin: 0 0 0.5rem 0;
}

.result-card__value {
  font-size: 1.125rem;
  font-weight: 600;
  color: var(--color-text-primary);
  margin: 0 0 0.25rem 0;
}

.result-card__arrow {
  color: var(--color-text-secondary);
  font-weight: 600;
  margin-left: 0.5rem;
}

.result-card__meta {
  font-size: 0.75rem;
  color: var(--color-text-secondary);
  margin: 0;
  word-break: break-all;
}

.result-info-box {
  border-radius: 1rem;
  border: 1px solid var(--color-border-soft);
  background: linear-gradient(135deg, rgba(67, 97, 238, 0.05) 0%, rgba(67, 97, 238, 0.02) 100%);
  overflow: hidden;
}

.result-info-box__header {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 1rem 1.25rem;
  background: rgba(67, 97, 238, 0.08);
  border-bottom: 1px solid var(--color-border-soft);
}

.result-info-box__icon {
  font-size: 1.25rem;
}

.result-info-box__title {
  font-size: 0.9375rem;
  font-weight: 600;
  color: var(--color-text-primary);
  margin: 0;
}

.result-info-box__content {
  padding: 1.25rem;
}

.result-info-box__path {
  margin-bottom: 1rem;
}

.path-code {
  display: inline-block;
  padding: 0.5rem 0.75rem;
  background: rgba(0, 0, 0, 0.05);
  border-radius: 0.5rem;
  font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
  font-size: 0.875rem;
  color: #4361ee;
  font-weight: 500;
  border: 1px solid rgba(67, 97, 238, 0.2);
}

.result-info-box__hint {
  font-size: 0.8125rem;
  color: var(--color-text-secondary);
  margin: 0;
  padding-top: 0.75rem;
  border-top: 1px solid var(--color-border-soft);
}

/* 请求体部分样式 */
.request-section {
  border-radius: 1.5rem;
  border: 1px dashed var(--color-border-soft);
  background: var(--color-surface-muted);
  overflow: hidden;
  transition: all 0.3s ease;
}

.request-section:hover {
  border-color: #4361ee;
  background: rgba(67, 97, 238, 0.02);
}

.request-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 1.25rem 1.5rem;
  cursor: pointer;
  user-select: none;
  transition: background 0.2s ease;
}

.request-header:hover {
  background: rgba(67, 97, 238, 0.05);
}

.request-header__left {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.request-header__icon {
  font-size: 1.25rem;
}

.request-header__title {
  font-size: 1.125rem;
  font-weight: 600;
  color: var(--color-text-primary);
  margin: 0;
}

.request-header__toggle {
  font-size: 0.875rem;
  color: var(--color-text-secondary);
  transition: transform 0.2s ease;
}

.request-content {
  padding: 0 1.5rem 1.5rem 1.5rem;
  animation: slideDown 0.3s ease;
}

@keyframes slideDown {
  from {
    opacity: 0;
    transform: translateY(-10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.request-code {
  margin: 0;
  padding: 1.25rem;
  background: rgba(0, 0, 0, 0.85);
  border-radius: 0.75rem;
  overflow-x: auto;
  font-size: 0.8125rem;
  line-height: 1.6;
  color: #e2e8f0;
  font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
  border: 1px solid rgba(255, 255, 255, 0.1);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2);
}

.request-code::-webkit-scrollbar {
  height: 8px;
}

.request-code::-webkit-scrollbar-track {
  background: rgba(255, 255, 255, 0.05);
  border-radius: 4px;
}

.request-code::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.2);
  border-radius: 4px;
}

.request-code::-webkit-scrollbar-thumb:hover {
  background: rgba(255, 255, 255, 0.3);
}
</style>

