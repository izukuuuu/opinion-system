<template>
  <div class="pt-0 pb-12 space-y-6">
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
                :disabled="topicsState.loading || topicOptions.length === 0" required>
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
            <button type="button" class="btn btn-ghost text-muted hover:text-primary" @click="resetAll"
              :disabled="runState.running">
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

      <!-- Custom Filters -->
      <section class="card-surface p-6 space-y-5">
        <div class="space-y-1">
          <h3 class="text-sm font-bold text-primary flex items-center gap-2">
            <FunnelIcon class="h-4 w-4 text-muted" />
            <span>自定义筛选规则</span>
          </h3>
          <p class="text-xs text-secondary">
            设置排除规则，分析时将自动过滤匹配的主题类别（如明星八卦、广告推广等无关内容）。
          </p>
        </div>

        <!-- Filter list -->
        <div v-if="bertopicPromptState.customFilters.length > 0"
          class="rounded-2xl border border-soft bg-surface-muted/20 divide-y divide-soft overflow-hidden">
          <div v-for="(filter, index) in bertopicPromptState.customFilters" :key="index"
            class="flex items-center gap-3 px-4 py-3 group transition-colors">
            <div class="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-brand-50 text-brand-600">
              <XCircleIcon class="h-4 w-4" />
            </div>
            <div class="flex-1 min-w-0 space-y-0.5">
              <p class="text-sm font-semibold text-primary truncate">{{ filter.category || '未命名类别' }}</p>
              <p v-if="filter.description" class="text-xs text-secondary truncate">{{ filter.description }}</p>
            </div>
            <button type="button"
              class="opacity-0 group-hover:opacity-100 transition-opacity p-1.5 rounded-xl text-muted hover:text-red-500 hover:bg-red-50"
              @click="removeFilter(index)" title="移除此规则">
              <TrashIcon class="h-4 w-4" />
            </button>
          </div>
        </div>

        <!-- Empty state -->
        <div v-else
          class="rounded-2xl border border-dashed border-soft bg-surface-muted/10 p-8 text-center space-y-2">
          <FunnelIcon class="h-8 w-8 mx-auto text-muted/40" />
          <p class="text-sm text-muted">尚未添加筛选规则</p>
          <p class="text-xs text-muted/60">添加规则后，分析时将自动排除匹配的主题</p>
        </div>

        <!-- Add filter form -->
        <div class="flex items-end gap-3">
          <div class="flex-1 space-y-1.5">
            <label class="text-xs font-bold text-muted uppercase tracking-wider">类别名称 *</label>
            <input v-model.trim="newFilterCategory" type="text"
              class="input w-full"
              placeholder="如：明星八卦、广告推广" />
          </div>
          <div class="flex-[2] space-y-1.5">
            <label class="text-xs font-bold text-muted uppercase tracking-wider">主题描述 *</label>
            <input v-model.trim="newFilterDescription" type="text"
              class="input w-full"
              placeholder="如：包含明星、校庆、修图等娱乐生活类内容"
              @keyup.enter="addFilter" />
          </div>
          <button type="button" class="btn btn-primary shrink-0 h-[42px] px-5"
            :disabled="!newFilterCategory"
            @click="addFilter">
            <PlusIcon class="h-4 w-4 mr-1" />
            添加
          </button>
        </div>
      </section>

      <section class="card-surface p-6 space-y-5">
        <div class="flex items-start justify-between gap-3">
          <div class="space-y-1">
            <h3 class="text-sm font-bold text-primary flex items-center gap-2">
              <ChatBubbleLeftRightIcon class="h-4 w-4 text-muted" />
              <span>LLM 再聚类与 Drop 提示词</span>
            </h3>
            <p class="text-xs text-secondary">
              这里可以快速补充再聚类与 drop 判定信息；系统会自动注入到最终提示词并随专题保存。
            </p>
          </div>
          <div class="flex items-center gap-2 shrink-0">
            <button type="button" class="btn btn-ghost btn-sm whitespace-nowrap"
              :disabled="bertopicPromptState.loading" @click="loadBertopicPrompt(form.topic)">
              {{ bertopicPromptState.loading ? '加载中…' : '重载配置' }}
            </button>
            <button type="button" class="btn btn-secondary btn-sm whitespace-nowrap" :disabled="!canSavePrompt"
              @click="handleSavePrompt">
              {{ bertopicPromptState.saving ? '保存中…' : '保存修改' }}
            </button>
          </div>
        </div>

        <div class="rounded-lg border border-soft bg-surface-muted/20 px-3 py-2 text-xs text-secondary">
          <p>
            配置文件位置：
            <span class="font-mono text-primary">{{ bertopicPromptState.path || '选择专题后自动生成' }}</span>
          </p>
          <p class="mt-1 text-muted">
            每个专题（项目）独立保存，后端会读取该文件参与后续 BERTopic 重分类。
          </p>
        </div>

        <label class="block">
          <span class="text-xs font-bold text-muted uppercase tracking-wider">最大主题数 Max Topics</span>
          <input v-model.number="bertopicPromptState.maxTopics" type="number" min="3" max="50"
            class="input w-full mt-1.5" />
          <span class="text-[11px] text-muted mt-1 block">AI 会自动推断合理的主题数量（最少 3 个），此值为上限约束</span>
        </label>

        <div class="grid gap-4 xl:grid-cols-2">
          <article class="rounded-xl border border-soft bg-surface p-4 space-y-3">
            <div class="flex items-center justify-between gap-2">
              <p class="text-sm font-semibold text-primary">LLM 再聚类 User Prompt 主体</p>
            </div>
            <p class="text-xs text-secondary">
              提供给模型的再聚类具体指令和输入数据（JSON）。您可以规定特定主题必须保留，或自定义主题分类的偏好。
            </p>
            <textarea
              v-model="bertopicPromptState.reclusterUserPrompt"
              rows="8"
              class="input w-full resize-y font-mono text-xs leading-relaxed"
              placeholder="再聚类 User Prompt 主体（包含 {input_data} 等变量）"
            />
            <label class="block mt-4">
              <span class="text-[11px] font-bold text-muted uppercase tracking-wider">System Prompt (可选)</span>
              <textarea
                v-model="bertopicPromptState.reclusterSystemPrompt"
                rows="2"
                class="input w-full mt-1.5 resize-y font-mono text-xs leading-relaxed"
                placeholder="系统级预设，如：你是一个专业的数据归类助手"
              />
            </label>
          </article>

          <article class="rounded-xl border border-soft bg-surface p-4 space-y-3">
            <div class="flex items-center justify-between gap-2">
              <p class="text-sm font-semibold text-primary">无关主题 Drop 规则</p>
              <div class="flex items-center gap-2">
                <button
                  type="button"
                  class="text-xs text-brand-600 hover:text-brand-700"
                  :disabled="bertopicPromptState.loading || bertopicPromptState.saving"
                  @click="restoreDefaultDropRulePrompt"
                >
                  恢复通用模板
                </button>
              </div>
            </div>
            <p class="text-xs text-secondary mb-1">
              定义哪些内容应被丢弃。这将被注入到模型的判定环节，请务必保留对 <code class="font-mono">drop</code> 参数的约束说明。
            </p>
            <textarea
              v-model="bertopicPromptState.dropRulePrompt"
              rows="10"
              class="input w-full resize-y font-mono text-xs leading-relaxed"
              placeholder="输入无关主题丢弃判定规则参数及说明"
            />
            <p class="text-[11px] text-muted -mt-1">
              可用变量：<span class="font-mono">{FOCUS_TOPIC}</span>
            </p>
          </article>
        </div>

        <div class="grid gap-4 md:grid-cols-2">
          <label class="block">
            <span class="text-xs font-bold text-muted uppercase tracking-wider">关键词 System Prompt</span>
            <textarea v-model="bertopicPromptState.keywordSystemPrompt" rows="3"
              class="input w-full mt-1.5 resize-y font-mono text-xs leading-relaxed" />
          </label>
          <label class="block">
            <span class="text-xs font-bold text-muted uppercase tracking-wider">关键词 User Prompt</span>
            <textarea v-model="bertopicPromptState.keywordUserPrompt" rows="3"
              class="input w-full mt-1.5 resize-y font-mono text-xs leading-relaxed" />
          </label>
        </div>

        <div class="bg-surface-muted/30 rounded-lg p-3 text-xs text-secondary space-y-1">
          <p class="font-semibold">再聚类模板变量：</p>
          <p class="font-mono opacity-80">{TARGET_TOPICS}, {input_data}, {topic_list}, {topic_stats_json}, {FOCUS_TOPIC}</p>
          <p class="font-semibold mt-2">关键词模板变量：</p>
          <p class="font-mono opacity-80">{cluster_name}, {topics}, {topics_csv}, {topics_json}, {description}</p>
        </div>

        <div v-if="bertopicPromptState.error || bertopicPromptState.message"
          class="rounded-xl border px-4 py-3 text-xs"
          :class="bertopicPromptState.error ? 'border-red-200 bg-red-50 text-red-700' : 'border-emerald-200 bg-emerald-50 text-emerald-700'">
          {{ bertopicPromptState.error || bertopicPromptState.message }}
        </div>
      </section>

      <!-- Advanced Configuration (Collapsible) -->
      <div v-show="showAdvancedSettings" class="space-y-6 animate-in slide-in-from-top-2 duration-200">

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
                  <input v-model.number="form.runParams.vectorizer.ngram_min" type="number" min="1"
                    class="input w-full" />
                </label>
                <label class="space-y-1.5">
                  <span class="block text-sm font-medium text-primary">最大词组长度</span>
                  <span class="block text-[10px] text-muted font-mono">ngram_max</span>
                  <input v-model.number="form.runParams.vectorizer.ngram_max" type="number" min="1"
                    class="input w-full" />
                </label>
                <label class="space-y-1.5">
                  <span class="block text-sm font-medium text-primary">最小词频过滤</span>
                  <span class="block text-[10px] text-muted font-mono">min_df</span>
                  <input v-model.number="form.runParams.vectorizer.min_df" type="number" min="0" step="0.1"
                    class="input w-full" />
                </label>
                <label class="space-y-1.5">
                  <span class="block text-sm font-medium text-primary">最大词频过滤</span>
                  <span class="block text-[10px] text-muted font-mono">max_df</span>
                  <input v-model.number="form.runParams.vectorizer.max_df" type="number" min="0" step="0.1"
                    class="input w-full" />
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
                  <input v-model.number="form.runParams.umap.min_dist" type="number" min="0" step="0.05"
                    class="input w-full" />
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
                  <input v-model.number="form.runParams.hdbscan.min_cluster_size" type="number" min="2"
                    class="input w-full" />
                </label>
                <label class="space-y-1.5">
                  <span class="block text-sm font-medium text-primary">核心点邻域样本</span>
                  <span class="block text-[10px] text-muted font-mono">min_samples</span>
                  <input v-model.number="form.runParams.hdbscan.min_samples" type="number" min="1"
                    class="input w-full" />
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
                  <input v-model.number="form.runParams.bertopic.top_n_words" type="number" min="5"
                    class="input w-full" />
                </label>
                <label class="space-y-1.5">
                  <span class="block text-sm font-medium text-primary mb-1">计算文档-主题概率</span>
                  <span class="block text-[10px] text-muted font-mono mb-2">calculate_probabilities</span>
                  <div class="flex items-center gap-2 pt-1">
                    <input v-model="form.runParams.bertopic.calculate_probabilities" type="checkbox"
                      class="h-4 w-4 rounded border-gray-300 text-brand-600 focus:ring-brand-500" />
                    <span class="text-xs text-secondary">启用</span>
                  </div>
                </label>
                <label class="space-y-1.5">
                  <span class="block text-sm font-medium text-primary mb-1">输出详细日志</span>
                  <span class="block text-[10px] text-muted font-mono mb-2">verbose</span>
                  <div class="flex items-center gap-2 pt-1">
                    <input v-model="form.runParams.bertopic.verbose" type="checkbox"
                      class="h-4 w-4 rounded border-gray-300 text-brand-600 focus:ring-brand-500" />
                    <span class="text-xs text-secondary">启用</span>
                  </div>
                </label>
              </div>
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
      <section v-if="lastResult"
        class="rounded-2xl border border-green-200 bg-green-50/50 p-6 animate-in slide-in-from-bottom-2">
        <div class="flex items-center gap-5">
          <div
            class="flex h-14 w-14 items-center justify-center rounded-full bg-green-100 text-green-600 border border-green-200 shadow-sm">
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
  CheckBadgeIcon,
  InformationCircleIcon,
  ExclamationTriangleIcon,
  ExclamationCircleIcon,
  AdjustmentsHorizontalIcon,
  ArrowRightIcon,
  CpuChipIcon,
  ChatBubbleLeftRightIcon,
  FunnelIcon,
  XCircleIcon,
  TrashIcon,
  PlusIcon
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
  logs,
  loadTopics,
  loadBertopicPrompt,
  saveBertopicPrompt,
  resetState,
  runBertopicAnalysis,
  resetRunParams
} = useTopicBertopicAnalysis()

const { activeProjectName } = useActiveProject()
const showAdvancedSettings = ref(false)
const newFilterCategory = ref('')
const newFilterDescription = ref('')

const addFilter = () => {
  const cat = (newFilterCategory.value || '').trim()
  if (!cat) return
  bertopicPromptState.customFilters.push({
    category: cat,
    description: (newFilterDescription.value || '').trim()
  })
  newFilterCategory.value = ''
  newFilterDescription.value = ''
}

const removeFilter = (index) => {
  bertopicPromptState.customFilters.splice(index, 1)
}



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
      endDate: form.endDate
    })
  } catch {
    // 错误处理已在日志组件体现
  }
}

const handleSavePrompt = async () => {
  try {
    await saveBertopicPrompt({ topic: form.topic })
  } catch {
    // 错误提示由状态区域显示
  }
}

const restoreDefaultDropRulePrompt = () => {
  bertopicPromptState.dropRulePrompt = String(
    bertopicPromptState.defaultDropRulePrompt || ''
  ).trim()
}
</script>

<style scoped>
/* Removed old custom styles as they are replaced by global utility classes */
</style>
