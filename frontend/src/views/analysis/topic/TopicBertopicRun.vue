<template>
  <div class="mx-auto max-w-5xl pt-0 pb-12 space-y-6">
    <form class="space-y-6" @submit.prevent="handleRun">
      <!-- Analysis Parameters -->
      <section class="card-surface space-y-4 p-6">
        <div class="mb-5 flex items-center justify-between">
          <h2 class="text-lg font-semibold text-primary">分析参数</h2>
          <button type="button"
            class="flex items-center gap-1 text-xs text-brand-600 transition-colors hover:text-brand-700 disabled:opacity-50"
            :disabled="topicsState.loading" @click="loadTopics(true)">
            <ArrowPathIcon class="h-3 w-3" :class="{ 'animate-spin': topicsState.loading }" />
            {{ topicsState.loading ? '正在同步专题...' : '刷新同步' }}
          </button>
        </div>

        <div class="grid gap-6 md:grid-cols-2">
          <!-- Topic Selection -->
          <div class="space-y-2">
            <label class="text-xs font-semibold text-muted tracking-wide uppercase">专题 Topic *</label>
            <div class="relative">
              <select v-model="form.topic" class="input w-full appearance-none pr-8"
                :disabled="topicsState.loading || topicOptions.length === 0" required @change="handleTopicChange">
                <option value="" disabled>请选择远程专题</option>
                <option v-for="option in topicOptions" :key="option.bucket" :value="option.bucket">
                  {{ option.display_name || option.name }}
                </option>
              </select>
              <div class="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-muted">
                <ChevronUpDownIcon class="h-4 w-4" />
              </div>
            </div>
          </div>

          <!-- Date Range -->
          <div class="grid grid-cols-2 gap-4">
            <div class="space-y-2">
              <label class="text-xs font-semibold text-muted tracking-wide uppercase">开始日期 Start *</label>
              <input v-model.trim="form.startDate" type="date" class="input w-full" required
                :disabled="availableRange.loading" />
            </div>
            <div class="space-y-2">
              <label class="text-xs font-semibold text-muted tracking-wide uppercase">结束日期 End</label>
              <input v-model.trim="form.endDate" type="date" class="input w-full" :disabled="availableRange.loading"
                :min="form.startDate" />
            </div>
          </div>

          <!-- Optional Fields -->
          <div class="space-y-2">
            <label class="text-xs font-semibold text-muted tracking-wide uppercase">fetch 目录（可选）</label>
            <input v-model.trim="form.fetchDir" type="text" placeholder="默认从 fetch/<range> 读取" class="input w-full" />
          </div>
          <div class="space-y-2">
            <label class="text-xs font-semibold text-muted tracking-wide uppercase">自定义 userdict（可选）</label>
            <input v-model.trim="form.userdict" type="text" placeholder="configs/userdict.txt" class="input w-full" />
          </div>
          <div class="space-y-2">
            <label class="text-xs font-semibold text-muted tracking-wide uppercase">自定义 stopwords（可选）</label>
            <input v-model.trim="form.stopwords" type="text" placeholder="configs/stopwords.txt" class="input w-full" />
          </div>
        </div>

        <!-- Data Availability Hint -->
        <div v-if="availableRange.start || availableRange.error" class="rounded-xl border p-4 text-sm mt-4"
          :class="availableRange.error ? 'border-red-200 bg-red-50 text-red-700' : 'border-brand-soft bg-brand-soft/10 text-brand-700'">
          <div class="flex items-start gap-2">
            <InformationCircleIcon v-if="!availableRange.error" class="h-5 w-5 shrink-0" />
            <ExclamationTriangleIcon v-else class="h-5 w-5 shrink-0" />
            <div>
              <p class="font-bold">数据可用性</p>
              <p class="text-xs mt-0.5 opacity-80">
                {{ availableRange.error || `有效范围：${availableRange.start} ~ ${availableRange.end}` }}
              </p>
            </div>
          </div>
        </div>

        <div class="flex flex-wrap gap-3 pt-2 text-sm">
          <button type="submit" class="btn-primary min-w-[160px] py-2.5" :disabled="!canSubmit">
            <span v-if="runState.running" class="flex items-center gap-2">
              <ArrowPathIcon class="h-4 w-4 animate-spin" />
              正在执行
            </span>
            <span v-else>运行主题分析</span>
          </button>
          <button type="button" class="btn-ghost px-4" @click="resetOptionalFields" :disabled="runState.running">
            清空可选参数
          </button>
          <button type="button" class="btn-ghost px-4 text-muted" @click="resetAll" :disabled="runState.running">
            重置任务
          </button>
        </div>
      </section>

      <!-- Runtime Parameters -->
      <section class="card-surface space-y-4 p-6">
        <div class="flex flex-wrap items-center justify-between gap-3">
          <div class="space-y-1">
            <h3 class="text-base font-semibold text-primary">运行参数配置</h3>
            <p class="text-xs text-secondary">已预填当前默认参数。建议先用默认值跑通，再按数据规模微调。</p>
          </div>
          <div class="flex flex-wrap gap-2">
            <button type="button" class="btn-ghost px-3 py-1.5" @click="showRunParams = !showRunParams">
              {{ showRunParams ? '收起参数' : '展开参数' }}
            </button>
            <button type="button" class="btn-secondary px-3 py-1.5" @click="resetRunParams"
              :disabled="runState.running || bertopicPromptState.saving || bertopicPromptState.loading">
              恢复默认
            </button>
          </div>
        </div>

        <div v-if="showRunParams" class="space-y-5">
          <div class="rounded-xl border border-soft bg-surface-muted/20 p-4">
            <p class="text-xs font-semibold text-primary uppercase tracking-wide mb-3">CountVectorizer</p>
            <div class="grid gap-4 md:grid-cols-4">
              <label class="space-y-1">
                <span class="text-xs text-muted">ngram_min</span>
                <input v-model.number="form.runParams.vectorizer.ngram_min" type="number" min="1" class="input w-full" />
              </label>
              <label class="space-y-1">
                <span class="text-xs text-muted">ngram_max</span>
                <input v-model.number="form.runParams.vectorizer.ngram_max" type="number" min="1" class="input w-full" />
              </label>
              <label class="space-y-1">
                <span class="text-xs text-muted">min_df</span>
                <input v-model.number="form.runParams.vectorizer.min_df" type="number" min="0" step="0.1" class="input w-full" />
              </label>
              <label class="space-y-1">
                <span class="text-xs text-muted">max_df</span>
                <input v-model.number="form.runParams.vectorizer.max_df" type="number" min="0" step="0.1" class="input w-full" />
              </label>
            </div>
          </div>

          <div class="rounded-xl border border-soft bg-surface-muted/20 p-4">
            <p class="text-xs font-semibold text-primary uppercase tracking-wide mb-3">UMAP</p>
            <div class="grid gap-4 md:grid-cols-5">
              <label class="space-y-1">
                <span class="text-xs text-muted">n_neighbors</span>
                <input v-model.number="form.runParams.umap.n_neighbors" type="number" min="2" class="input w-full" />
              </label>
              <label class="space-y-1">
                <span class="text-xs text-muted">n_components</span>
                <input v-model.number="form.runParams.umap.n_components" type="number" min="2" class="input w-full" />
              </label>
              <label class="space-y-1">
                <span class="text-xs text-muted">min_dist</span>
                <input v-model.number="form.runParams.umap.min_dist" type="number" min="0" step="0.05" class="input w-full" />
              </label>
              <label class="space-y-1">
                <span class="text-xs text-muted">metric</span>
                <select v-model="form.runParams.umap.metric" class="input w-full">
                  <option value="cosine">cosine</option>
                  <option value="euclidean">euclidean</option>
                  <option value="manhattan">manhattan</option>
                </select>
              </label>
              <label class="space-y-1">
                <span class="text-xs text-muted">random_state</span>
                <input v-model.number="form.runParams.umap.random_state" type="number" class="input w-full" />
              </label>
            </div>
          </div>

          <div class="rounded-xl border border-soft bg-surface-muted/20 p-4">
            <p class="text-xs font-semibold text-primary uppercase tracking-wide mb-3">HDBSCAN</p>
            <div class="grid gap-4 md:grid-cols-4">
              <label class="space-y-1">
                <span class="text-xs text-muted">min_cluster_size</span>
                <input v-model.number="form.runParams.hdbscan.min_cluster_size" type="number" min="2" class="input w-full" />
              </label>
              <label class="space-y-1">
                <span class="text-xs text-muted">min_samples</span>
                <input v-model.number="form.runParams.hdbscan.min_samples" type="number" min="1" class="input w-full" />
              </label>
              <label class="space-y-1">
                <span class="text-xs text-muted">metric</span>
                <select v-model="form.runParams.hdbscan.metric" class="input w-full">
                  <option value="euclidean">euclidean</option>
                  <option value="manhattan">manhattan</option>
                  <option value="cosine">cosine</option>
                </select>
              </label>
              <label class="space-y-1">
                <span class="text-xs text-muted">cluster_selection_method</span>
                <select v-model="form.runParams.hdbscan.cluster_selection_method" class="input w-full">
                  <option value="eom">eom</option>
                  <option value="leaf">leaf</option>
                </select>
              </label>
            </div>
          </div>

          <div class="rounded-xl border border-soft bg-surface-muted/20 p-4">
            <p class="text-xs font-semibold text-primary uppercase tracking-wide mb-3">BERTopic</p>
            <div class="grid gap-4 md:grid-cols-3">
              <label class="space-y-1">
                <span class="text-xs text-muted">top_n_words</span>
                <input v-model.number="form.runParams.bertopic.top_n_words" type="number" min="5" class="input w-full" />
              </label>
              <label class="inline-flex items-center gap-2 pt-6">
                <input v-model="form.runParams.bertopic.calculate_probabilities" type="checkbox" class="h-4 w-4" />
                <span class="text-xs text-secondary">calculate_probabilities</span>
              </label>
              <label class="inline-flex items-center gap-2 pt-6">
                <input v-model="form.runParams.bertopic.verbose" type="checkbox" class="h-4 w-4" />
                <span class="text-xs text-secondary">verbose</span>
              </label>
            </div>
          </div>
        </div>
      </section>

      <!-- Prompt Configuration -->
      <section class="card-surface space-y-4 p-6">
        <div class="flex flex-wrap items-start justify-between gap-3">
          <div class="space-y-1">
            <h3 class="text-base font-semibold text-primary">BERTopic 提示词配置</h3>
            <p class="text-xs text-secondary">控制大模型再聚类和主题关键词生成逻辑，保存后立即用于本专题分析。</p>
            <p v-if="bertopicPromptState.path" class="text-[11px] text-muted">配置文件：{{ bertopicPromptState.path }}</p>
          </div>
          <div class="flex flex-wrap gap-2">
            <button type="button" class="btn-ghost px-3 py-1.5" :disabled="bertopicPromptState.loading"
              @click="loadBertopicPrompt(form.topic)">
              {{ bertopicPromptState.loading ? '加载中…' : '重新加载' }}
            </button>
            <button type="button" class="btn-secondary px-3 py-1.5" :disabled="!canSavePrompt" @click="handleSavePrompt">
              {{ bertopicPromptState.saving ? '保存中…' : '保存配置' }}
            </button>
          </div>
        </div>

        <div class="grid gap-4 md:grid-cols-3">
          <label class="space-y-2 md:col-span-1">
            <span class="text-xs font-semibold text-muted tracking-wide uppercase">目标主题数 Target Topics</span>
            <input v-model.number="bertopicPromptState.targetTopics" type="number" min="2" max="50" class="input w-full" />
          </label>
          <div class="md:col-span-2 rounded-xl border border-soft bg-surface-muted/20 px-4 py-3 text-xs text-secondary">
            <p class="font-semibold text-primary">模板变量</p>
            <p class="mt-1">{TARGET_TOPICS}、{input_data}、{topic_list}、{topic_stats_json}</p>
            <p class="mt-1 text-muted">关键词模板支持：{cluster_name}、{topics}、{topics_csv}、{topics_json}、{description}</p>
          </div>
        </div>

        <div class="grid gap-4">
          <label class="space-y-2">
            <span class="text-xs font-semibold text-muted tracking-wide uppercase">再聚类 System Prompt</span>
            <textarea v-model="bertopicPromptState.reclusterSystemPrompt" rows="4" class="input w-full resize-y font-mono text-xs"
              placeholder="你是一个专业的文本分析专家..." />
          </label>
          <label class="space-y-2">
            <span class="text-xs font-semibold text-muted tracking-wide uppercase">再聚类 User Prompt</span>
            <textarea v-model="bertopicPromptState.reclusterUserPrompt" rows="10" class="input w-full resize-y font-mono text-xs"
              placeholder="请将以下主题结果合并为 {TARGET_TOPICS} 个类别..." />
          </label>
        </div>

        <div class="rounded-xl border border-soft bg-surface-muted/20 p-4">
          <button type="button" class="inline-flex items-center gap-2 text-xs font-semibold text-primary"
            @click="showAdvancedPrompt = !showAdvancedPrompt">
            <ChevronDownIcon class="h-4 w-4 transition-transform duration-200"
              :class="{ 'rotate-180': showAdvancedPrompt }" />
            关键词生成提示词（高级）
          </button>
          <div v-if="showAdvancedPrompt" class="mt-4 grid gap-4">
            <label class="space-y-2">
              <span class="text-xs font-semibold text-muted tracking-wide uppercase">关键词 System Prompt</span>
              <textarea v-model="bertopicPromptState.keywordSystemPrompt" rows="3"
                class="input w-full resize-y font-mono text-xs" placeholder="你是一个专业的文本分析专家。" />
            </label>
            <label class="space-y-2">
              <span class="text-xs font-semibold text-muted tracking-wide uppercase">关键词 User Prompt</span>
              <textarea v-model="bertopicPromptState.keywordUserPrompt" rows="6"
                class="input w-full resize-y font-mono text-xs"
                placeholder="为以下主题类别生成 5-8 个核心关键词：类别名称：{cluster_name}..." />
            </label>
          </div>
        </div>

        <div v-if="bertopicPromptState.error || bertopicPromptState.message"
          class="rounded-xl border px-4 py-3 text-xs"
          :class="bertopicPromptState.error ? 'border-red-200 bg-red-50 text-red-700' : 'border-emerald-200 bg-emerald-50 text-emerald-700'">
          {{ bertopicPromptState.error || bertopicPromptState.message }}
        </div>
      </section>

      <!-- Logs -->
      <section v-if="logs.length > 0" class="card-surface p-6">
        <h3 class="text-sm font-bold text-muted uppercase tracking-widest mb-4">执行流水线</h3>
        <AnalysisLogList :logs="logs" class="max-h-[300px] overflow-y-auto" empty-label="暂无执行记录" />
      </section>

      <!-- Failure Warning -->
      <section v-if="logs.some(log => log.status === 'error')"
        class="rounded-2xl border border-danger/20 bg-danger/5 p-5 text-danger">
        <div class="flex items-center gap-3">
          <ExclamationCircleIcon class="h-6 w-6" />
          <div>
            <p class="font-bold">分析运行中止</p>
            <p class="text-sm mt-0.5">{{logs.find(log => log.status === 'error')?.message || '发生未知环境或数据错误'}}</p>
          </div>
        </div>
      </section>

      <!-- Results Container -->
      <section v-if="lastResult" class="card-surface p-6 space-y-6">
        <div class="flex items-center gap-4 border-b border-soft pb-4">
          <div
            class="flex h-12 w-12 items-center justify-center rounded-2xl bg-green-50 text-green-600 border border-green-100">
            <CheckBadgeIcon class="h-8 w-8" />
          </div>
          <div>
            <h2 class="text-xl font-bold text-primary">分析成功</h2>
            <p class="text-sm text-secondary">主题建模流水线已顺利完成</p>
          </div>
        </div>

        <div class="grid gap-4 md:grid-cols-2">
          <div class="rounded-xl border border-soft bg-surface-muted/30 p-4">
            <p class="text-[10px] font-black text-muted uppercase tracking-wider mb-2">RUN STATUS</p>
            <p class="text-lg font-bold text-primary">{{ lastResult.status === 'ok' ? '已就绪' : lastResult.status }}</p>
            <p class="text-xs text-secondary mt-1">Operation: {{ lastResult.operation }}</p>
          </div>

          <div class="rounded-xl border border-soft bg-surface-muted/30 p-4">
            <p class="text-[10px] font-black text-muted uppercase tracking-wider mb-2">DATE RANGE</p>
            <p class="text-lg font-bold text-primary">
              {{ lastResult.data?.start_date || lastResult.data?.start || '-' }}
              <span class="text-muted font-normal mx-2">→</span>
              {{ lastResult.data?.end_date || lastResult.data?.end || '-' }}
            </p>
            <p class="text-xs text-secondary mt-1">Topic: {{ lastResult.data?.topic || '-' }}</p>
          </div>
        </div>

        <div class="rounded-2xl border border-brand-soft/30 bg-brand-soft/10 p-5">
          <div class="flex items-center gap-3 mb-4">
            <FolderOpenIcon class="h-5 w-5 text-brand-600" />
            <h3 class="text-base font-bold text-primary">生成的文件资产</h3>
          </div>
          <div class="rounded-xl bg-white/60 border border-white p-3 font-mono text-xs text-brand-700 break-all">
            data/topic/{{ form.topic || lastResult.data?.topic }}/&lt;range&gt;/results.json
          </div>
          <p class="mt-4 text-xs text-secondary flex items-center gap-2">
            <SparklesIcon class="h-3.5 w-3.5 text-amber-500" />
            <span>你可以立即前往结果页查看这些生成的主题维度分析。</span>
          </p>
        </div>
      </section>

      <!-- Debug Payload -->
      <section v-if="lastPayload"
        class="rounded-2xl border border-soft border-dashed p-6 bg-surface-muted/10 transition-colors">
        <div class="flex items-center justify-between cursor-pointer group"
          @click="showRequestPayload = !showRequestPayload">
          <div class="flex items-center gap-3">
            <CommandLineIcon class="h-5 w-5 text-muted group-hover:text-primary" />
            <h2 class="text-sm font-bold text-secondary group-hover:text-primary tracking-tight">最近一次任务请求明细</h2>
          </div>
          <ChevronDownIcon class="h-5 w-5 text-muted transition-transform duration-300"
            :class="{ 'rotate-180': showRequestPayload }" />
        </div>
        <div v-if="showRequestPayload" class="mt-5">
          <pre
            class="rounded-xl bg-gray-950 p-5 text-xs text-gray-300 overflow-x-auto leading-relaxed">{{ formattedPayload }}</pre>
        </div>
      </section>
    </form>
  </div>
</template>

<script setup>
import { computed, watch, onMounted, ref } from 'vue'
import {
  ArrowPathIcon,
  ChevronUpDownIcon,
  ChevronDownIcon,
  CheckBadgeIcon,
  InformationCircleIcon,
  ExclamationTriangleIcon,
  ExclamationCircleIcon,
  FolderOpenIcon,
  SparklesIcon,
  CommandLineIcon
} from '@heroicons/vue/24/solid'
import { useTopicBertopicAnalysis } from '@/composables/useTopicBertopicAnalysis'
import { useActiveProject } from '@/composables/useActiveProject'
import AnalysisLogList from '@/components/analysis/AnalysisLogList.vue'

const {
  topicsState,
  topicOptions,
  form,
  bertopicPromptState,
  hasPromptDraftChanges,
  availableRange,
  runState,
  lastResult,
  lastPayload,
  logs,
  loadTopics,
  loadBertopicPrompt,
  saveBertopicPrompt,
  resetState,
  runBertopicAnalysis,
  resetOptionalFields,
  resetRunParams
} = useTopicBertopicAnalysis()

const { activeProjectName } = useActiveProject()
const showRequestPayload = ref(false)
const showAdvancedPrompt = ref(false)
const showRunParams = ref(false)

onMounted(() => {
  loadTopics(true)
})

watch(
  activeProjectName,
  (value) => {
    if (!value) return
    form.project = value
    if (!form.topic) {
      const matched = topicOptions.value.find(t =>
        t.name === value || t.display_name === value || t.bucket === value
      )
      if (matched) {
        form.topic = matched.bucket
      }
    }
    if (form.topic) {
      loadBertopicPrompt(form.topic)
    }
  },
  { immediate: true }
)

const canSavePrompt = computed(() => {
  return Boolean(
    form.topic.trim() &&
    !bertopicPromptState.loading &&
    !bertopicPromptState.saving
  )
})

const canSubmit = computed(() => {
  return Boolean(
    form.topic.trim() &&
    form.startDate.trim() &&
    !runState.running &&
    !availableRange.loading &&
    !bertopicPromptState.saving &&
    !bertopicPromptState.loading
  )
})

const formattedPayload = computed(() => {
  return JSON.stringify(lastPayload.value, null, 2)
})

const resetAll = () => {
  form.startDate = ''
  form.endDate = ''
  resetOptionalFields()
  resetState()
}

const handleRun = async () => {
  try {
    if (hasPromptDraftChanges.value) {
      await saveBertopicPrompt({ topic: form.topic })
    }

    await runBertopicAnalysis({
      topic: form.topic,
      startDate: form.startDate,
      endDate: form.endDate,
      fetchDir: form.fetchDir,
      userdict: form.userdict,
      stopwords: form.stopwords
    })
  } catch {
    // 错误处理已在日志组件体现
  }
}

const handleTopicChange = () => {
  resetOptionalFields()
}

const handleSavePrompt = async () => {
  try {
    await saveBertopicPrompt({ topic: form.topic })
  } catch {
    // 错误提示由状态区域显示
  }
}
</script>

<style scoped>
/* Removed old custom styles as they are replaced by global utility classes */
</style>
