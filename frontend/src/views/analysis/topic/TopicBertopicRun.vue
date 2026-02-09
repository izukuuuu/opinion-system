<template>
  <div class="mx-auto max-w-4xl pt-0 pb-12 space-y-6">
    <form class="space-y-6" @submit.prevent="handleRun">
      <!-- Main Configuration -->
      <section class="card-surface p-6">
        <div class="mb-6 flex items-center justify-between">
          <h2 class="text-lg font-semibold text-primary">新建分析任务</h2>
          <button type="button"
            class="flex items-center gap-1.5 text-xs font-medium text-brand-600 hover:text-brand-700 disabled:opacity-50 transition-colors"
            :disabled="topicsState.loading" @click="loadTopics(true)">
            <ArrowPathIcon class="h-3.5 w-3.5" :class="{ 'animate-spin': topicsState.loading }" />
            {{ topicsState.loading ? '同步中...' : '刷新专题列表' }}
          </button>
        </div>

        <div class="grid gap-6 md:grid-cols-2">
          <!-- Topic Selection -->
          <div class="space-y-2">
            <label class="text-xs font-bold text-muted uppercase tracking-wider">专题 Topic *</label>
            <div class="relative">
              <select v-model="form.topic" class="input w-full appearance-none pr-10"
                :disabled="topicsState.loading || topicOptions.length === 0" required @change="handleTopicChange">
                <option value="" disabled>请选择分析专题</option>
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
              <label class="text-xs font-bold text-muted uppercase tracking-wider">开始日期 Start *</label>
              <input v-model.trim="form.startDate" type="date" class="input w-full" required
                :disabled="availableRange.loading" />
            </div>
            <div class="space-y-2">
              <label class="text-xs font-bold text-muted uppercase tracking-wider">结束日期 End</label>
              <input v-model.trim="form.endDate" type="date" class="input w-full" :disabled="availableRange.loading"
                :min="form.startDate" />
            </div>
          </div>
        </div>

        <!-- Data Availability Hint -->
        <div v-if="availableRange.start || availableRange.error" class="mt-6 rounded-xl border p-4 text-sm"
          :class="availableRange.error ? 'border-red-200 bg-red-50 text-red-700' : 'border-blue-100 bg-blue-50/50 text-blue-700'">
          <div class="flex items-start gap-3">
            <InformationCircleIcon v-if="!availableRange.error" class="h-5 w-5 shrink-0 text-blue-500" />
            <ExclamationTriangleIcon v-else class="h-5 w-5 shrink-0 text-red-500" />
            <div class="space-y-1">
              <p class="font-bold text-primary">数据可用性检查</p>
              <p class="text-xs opacity-90">
                {{ availableRange.error || `当前专题数据覆盖范围：${availableRange.start} ~ ${availableRange.end}` }}
              </p>
            </div>
          </div>
        </div>

        <div class="mt-8 flex items-center justify-between border-t border-soft pt-6">
          <div class="flex items-center gap-4">
             <button type="button" 
              class="flex items-center gap-2 text-sm font-medium text-secondary hover:text-primary transition-colors"
              @click="showAdvancedSettings = !showAdvancedSettings">
              <AdjustmentsHorizontalIcon class="h-5 w-5" />
              <span>{{ showAdvancedSettings ? '隐藏高级设置' : '显示高级设置' }}</span>
            </button>
          </div>
          
          <div class="flex items-center gap-3">
             <button type="button" class="btn btn-ghost text-muted hover:text-primary" @click="resetAll" :disabled="runState.running">
              重置
            </button>
            <button type="submit" class="btn btn-primary min-w-[140px]" :disabled="!canSubmit">
              <span v-if="runState.running" class="flex items-center gap-2">
                <ArrowPathIcon class="h-4 w-4 animate-spin" />
                <span>分析中...</span>
              </span>
              <span v-else>开始分析</span>
            </button>
          </div>
        </div>
      </section>

      <!-- Advanced Configuration (Collapsible) -->
      <div v-show="showAdvancedSettings" class="space-y-6 animate-in slide-in-from-top-2 duration-200">
        
        <!-- Optional Paths -->
        <section class="card-surface p-6">
          <h3 class="text-sm font-bold text-primary mb-4 flex items-center gap-2">
            <FolderOpenIcon class="h-4 w-4 text-muted" />
            <span>路径配置 (可选)</span>
          </h3>
          <div class="grid gap-6 md:grid-cols-3">
            <div class="space-y-2">
              <label class="text-xs font-bold text-muted uppercase tracking-wider">Fetch 目录</label>
              <input v-model.trim="form.fetchDir" type="text" placeholder="默认自动推断" class="input w-full" />
            </div>
            <div class="space-y-2">
              <label class="text-xs font-bold text-muted uppercase tracking-wider">自定义 Userdict</label>
              <input v-model.trim="form.userdict" type="text" placeholder="configs/userdict.txt" class="input w-full" />
            </div>
            <div class="space-y-2">
              <label class="text-xs font-bold text-muted uppercase tracking-wider">自定义 Stopwords</label>
              <input v-model.trim="form.stopwords" type="text" placeholder="configs/stopwords.txt" class="input w-full" />
            </div>
          </div>
        </section>

        <!-- Runtime Parameters -->
        <section class="card-surface p-6">
           <div class="flex items-center justify-between mb-4">
            <h3 class="text-sm font-bold text-primary flex items-center gap-2">
              <CpuChipIcon class="h-4 w-4 text-muted" />
              <span>算法参数配置</span>
            </h3>
            <button type="button" class="text-xs text-brand-600 hover:text-brand-700" @click="resetRunParams"
              :disabled="runState.running">
              恢复默认值
            </button>
          </div>
          
          <div class="space-y-8">
            <!-- CountVectorizer -->
            <div>
              <h4 class="text-xs font-bold text-muted uppercase tracking-wider mb-3">CountVectorizer (词向量化)</h4>
              <div class="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
                <label class="space-y-1.5">
                  <span class="block text-sm font-medium text-primary">最小词组长度</span>
                  <span class="block text-[10px] text-muted font-mono">ngram_min</span>
                  <input v-model.number="form.runParams.vectorizer.ngram_min" type="number" min="1" class="input w-full" />
                </label>
                <label class="space-y-1.5">
                  <span class="block text-sm font-medium text-primary">最大词组长度</span>
                  <span class="block text-[10px] text-muted font-mono">ngram_max</span>
                  <input v-model.number="form.runParams.vectorizer.ngram_max" type="number" min="1" class="input w-full" />
                </label>
                <label class="space-y-1.5">
                  <span class="block text-sm font-medium text-primary">最小词频过滤</span>
                  <span class="block text-[10px] text-muted font-mono">min_df</span>
                  <input v-model.number="form.runParams.vectorizer.min_df" type="number" min="0" step="0.1" class="input w-full" />
                </label>
                <label class="space-y-1.5">
                  <span class="block text-sm font-medium text-primary">最大词频过滤</span>
                  <span class="block text-[10px] text-muted font-mono">max_df</span>
                  <input v-model.number="form.runParams.vectorizer.max_df" type="number" min="0" step="0.1" class="input w-full" />
                </label>
              </div>
            </div>

            <!-- UMAP -->
            <div>
              <h4 class="text-xs font-bold text-muted uppercase tracking-wider mb-3">UMAP (降维)</h4>
              <div class="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                <label class="space-y-1.5">
                  <span class="block text-sm font-medium text-primary">近邻数量</span>
                  <span class="block text-[10px] text-muted font-mono">n_neighbors</span>
                  <input v-model.number="form.runParams.umap.n_neighbors" type="number" min="2" class="input w-full" />
                </label>
                <label class="space-y-1.5">
                  <span class="block text-sm font-medium text-primary">降维目标维度</span>
                  <span class="block text-[10px] text-muted font-mono">n_components</span>
                  <input v-model.number="form.runParams.umap.n_components" type="number" min="2" class="input w-full" />
                </label>
                <label class="space-y-1.5">
                  <span class="block text-sm font-medium text-primary">点间最小距离</span>
                  <span class="block text-[10px] text-muted font-mono">min_dist</span>
                  <input v-model.number="form.runParams.umap.min_dist" type="number" min="0" step="0.05" class="input w-full" />
                </label>
                <label class="space-y-1.5">
                  <span class="block text-sm font-medium text-primary">距离度量</span>
                  <span class="block text-[10px] text-muted font-mono">metric</span>
                  <select v-model="form.runParams.umap.metric" class="input w-full">
                    <option value="cosine">cosine</option>
                    <option value="euclidean">euclidean</option>
                    <option value="manhattan">manhattan</option>
                  </select>
                </label>
                <label class="space-y-1.5">
                  <span class="block text-sm font-medium text-primary">随机种子</span>
                  <span class="block text-[10px] text-muted font-mono">random_state</span>
                  <input v-model.number="form.runParams.umap.random_state" type="number" class="input w-full" />
                </label>
              </div>
            </div>

            <!-- HDBSCAN -->
            <div>
              <h4 class="text-xs font-bold text-muted uppercase tracking-wider mb-3">HDBSCAN (聚类)</h4>
              <div class="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
                <label class="space-y-1.5">
                  <span class="block text-sm font-medium text-primary">最小聚类规模</span>
                  <span class="block text-[10px] text-muted font-mono">min_cluster_size</span>
                  <input v-model.number="form.runParams.hdbscan.min_cluster_size" type="number" min="2" class="input w-full" />
                </label>
                <label class="space-y-1.5">
                  <span class="block text-sm font-medium text-primary">核心点邻域样本</span>
                  <span class="block text-[10px] text-muted font-mono">min_samples</span>
                  <input v-model.number="form.runParams.hdbscan.min_samples" type="number" min="1" class="input w-full" />
                </label>
                <label class="space-y-1.5">
                  <span class="block text-sm font-medium text-primary">距离度量</span>
                  <span class="block text-[10px] text-muted font-mono">metric</span>
                  <select v-model="form.runParams.hdbscan.metric" class="input w-full">
                    <option value="euclidean">euclidean</option>
                    <option value="manhattan">manhattan</option>
                    <option value="cosine">cosine</option>
                  </select>
                </label>
                <label class="space-y-1.5">
                  <span class="block text-sm font-medium text-primary">簇选择算法</span>
                  <span class="block text-[10px] text-muted font-mono">selection_method</span>
                  <select v-model="form.runParams.hdbscan.cluster_selection_method" class="input w-full">
                    <option value="eom">eom (叶节点过多时合并)</option>
                    <option value="leaf">leaf (保留所有叶节点)</option>
                  </select>
                </label>
              </div>
            </div>

            <!-- BERTopic -->
            <div>
              <h4 class="text-xs font-bold text-muted uppercase tracking-wider mb-3">BERTopic (主题建模)</h4>
              <div class="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                <label class="space-y-1.5">
                  <span class="block text-sm font-medium text-primary">主题词展示数</span>
                  <span class="block text-[10px] text-muted font-mono">top_n_words</span>
                  <input v-model.number="form.runParams.bertopic.top_n_words" type="number" min="5" class="input w-full" />
                </label>
                <label class="space-y-1.5">
                  <span class="block text-sm font-medium text-primary mb-1">计算文档-主题概率</span>
                  <span class="block text-[10px] text-muted font-mono mb-2">calculate_probabilities</span>
                  <div class="flex items-center gap-2 pt-1">
                    <input v-model="form.runParams.bertopic.calculate_probabilities" type="checkbox" class="h-4 w-4 rounded border-gray-300 text-brand-600 focus:ring-brand-500" />
                    <span class="text-xs text-secondary">启用</span>
                  </div>
                </label>
                <label class="space-y-1.5">
                  <span class="block text-sm font-medium text-primary mb-1">输出详细日志</span>
                  <span class="block text-[10px] text-muted font-mono mb-2">verbose</span>
                  <div class="flex items-center gap-2 pt-1">
                    <input v-model="form.runParams.bertopic.verbose" type="checkbox" class="h-4 w-4 rounded border-gray-300 text-brand-600 focus:ring-brand-500" />
                    <span class="text-xs text-secondary">启用</span>
                  </div>
                </label>
              </div>
            </div>
          </div>
        </section>

        <!-- Prompt Configuration -->
        <section class="card-surface p-6">
          <div class="flex items-start justify-between gap-3 mb-6">
            <div class="space-y-1">
              <h3 class="text-sm font-bold text-primary flex items-center gap-2">
                <ChatBubbleLeftRightIcon class="h-4 w-4 text-muted" />
                <span>LLM 提示词配置</span>
              </h3>
              <p class="text-xs text-secondary">
                配置大模型重聚类（Re-clustering）与命名生成逻辑。
              </p>
            </div>
            <div class="flex items-center gap-2 shrink-0">
               <button type="button" class="btn btn-ghost btn-sm whitespace-nowrap" :disabled="bertopicPromptState.loading"
                @click="loadBertopicPrompt(form.topic)">
                {{ bertopicPromptState.loading ? '加载中…' : '重载配置' }}
              </button>
              <button type="button" class="btn btn-secondary btn-sm whitespace-nowrap" :disabled="!canSavePrompt" @click="handleSavePrompt">
                {{ bertopicPromptState.saving ? '保存中…' : '保存修改' }}
              </button>
            </div>
          </div>

          <div class="space-y-4">
             <label class="block">
              <span class="text-xs font-bold text-muted uppercase tracking-wider">目标主题数 Target Topics</span>
              <input v-model.number="bertopicPromptState.targetTopics" type="number" min="2" max="50" class="input w-full mt-1.5" />
            </label>

            <div class="grid gap-4 md:grid-cols-2">
              <label class="block">
                <span class="text-xs font-bold text-muted uppercase tracking-wider">再聚类 System Prompt</span>
                <textarea v-model="bertopicPromptState.reclusterSystemPrompt" rows="4" class="input w-full mt-1.5 resize-y font-mono text-xs leading-relaxed" />
              </label>
               <label class="block">
                <span class="text-xs font-bold text-muted uppercase tracking-wider">再聚类 User Prompt</span>
                <textarea v-model="bertopicPromptState.reclusterUserPrompt" rows="4" class="input w-full mt-1.5 resize-y font-mono text-xs leading-relaxed" />
              </label>
            </div>
            
            <div class="bg-surface-muted/30 rounded-lg p-3 text-xs text-secondary space-y-1">
              <p class="font-semibold">可用变量：</p>
              <p class="font-mono opacity-80">{TARGET_TOPICS}, {input_data}, {topic_list}, {topic_stats_json}</p>
            </div>

            <div class="grid gap-4 md:grid-cols-2">
              <label class="block">
                <span class="text-xs font-bold text-muted uppercase tracking-wider">关键词 System Prompt</span>
                <textarea v-model="bertopicPromptState.keywordSystemPrompt" rows="3" class="input w-full mt-1.5 resize-y font-mono text-xs leading-relaxed" />
              </label>
              <label class="block">
                <span class="text-xs font-bold text-muted uppercase tracking-wider">关键词 User Prompt</span>
                <textarea v-model="bertopicPromptState.keywordUserPrompt" rows="3" class="input w-full mt-1.5 resize-y font-mono text-xs leading-relaxed" />
              </label>
            </div>

            <div class="bg-surface-muted/30 rounded-lg p-3 text-xs text-secondary space-y-1">
              <p class="font-semibold">关键词模板变量：</p>
              <p class="font-mono opacity-80">{cluster_name}, {topics}, {topics_csv}, {topics_json}, {description}</p>
            </div>

            <div v-if="bertopicPromptState.error || bertopicPromptState.message"
              class="rounded-xl border px-4 py-3 text-xs"
              :class="bertopicPromptState.error ? 'border-red-200 bg-red-50 text-red-700' : 'border-emerald-200 bg-emerald-50 text-emerald-700'">
              {{ bertopicPromptState.error || bertopicPromptState.message }}
            </div>
          </div>
        </section>
      </div>

      <!-- Logs -->
      <section v-if="logs.length > 0" class="card-surface p-6">
        <h3 class="text-sm font-bold text-muted uppercase tracking-widest mb-4">运行日志</h3>
        <AnalysisLogList :logs="logs" class="max-h-[300px] overflow-y-auto" empty-label="等待执行..." />
      </section>

      <!-- Failure Warning -->
      <section v-if="logs.some(log => log.status === 'error')"
        class="rounded-xl border border-red-200 bg-red-50 p-5 text-red-700 animate-in slide-in-from-top-1">
        <div class="flex items-start gap-3">
          <ExclamationCircleIcon class="h-6 w-6 shrink-0" />
          <div>
            <p class="font-bold">任务执行中断</p>
            <p class="text-sm mt-1">{{logs.find(log => log.status === 'error')?.message || '发生未知错误'}}</p>
          </div>
        </div>
      </section>

      <!-- Success Result -->
      <section v-if="lastResult" class="rounded-2xl border border-green-200 bg-green-50/50 p-6 animate-in slide-in-from-bottom-2">
        <div class="flex items-center gap-5">
          <div class="flex h-14 w-14 items-center justify-center rounded-full bg-green-100 text-green-600 border border-green-200 shadow-sm">
            <CheckBadgeIcon class="h-8 w-8" />
          </div>
          <div class="space-y-1">
            <h2 class="text-xl font-bold text-gray-900">分析完成</h2>
            <p class="text-sm text-gray-600">主题模型已成功构建，相关数据资产已生成。</p>
          </div>
          <div class="ml-auto">
             <router-link :to="`/analysis/topic/bertopic/results`" class="btn btn-primary drop-shadow-sm">
              查看分析报告
              <ArrowRightIcon class="h-4 w-4 ml-1" />
            </router-link>
          </div>
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
  AdjustmentsHorizontalIcon,
  ArrowRightIcon,
  CpuChipIcon,
  ChatBubbleLeftRightIcon
} from '@heroicons/vue/24/outline'
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
const showAdvancedSettings = ref(false)
const showAdvancedPrompt = ref(false)

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
