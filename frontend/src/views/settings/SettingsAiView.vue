<template>
  <section class="max-w-5xl mx-auto space-y-8 pb-12">


    <!-- Global Feedback -->
    <div v-if="llmState.error || credentialState.error"
      class="rounded-xl bg-danger-soft p-4 border border-soft flex items-start gap-3 animate-in fade-in slide-in-from-top-2">
      <ExclamationCircleIcon class="w-5 h-5 text-danger shrink-0 mt-0.5" />
      <p class="text-sm text-danger font-medium">{{ llmState.error || credentialState.error }}</p>
    </div>
    <div v-if="llmState.message || credentialState.message"
      class="rounded-xl bg-success-soft p-4 border border-soft flex items-start gap-3 animate-in fade-in slide-in-from-top-2">
      <CheckCircleIcon class="w-5 h-5 text-success shrink-0 mt-0.5" />
      <p class="text-sm text-success font-medium">{{ llmState.message || credentialState.message }}</p>
    </div>

    <!-- Tabs -->
    <div class="flex justify-center">
      <div class="inline-flex rounded-2xl border border-soft bg-base-soft p-1.5">
        <button v-for="tab in aiTabs" :key="tab.key" type="button"
          class="px-6 py-2.5 rounded-xl text-sm font-semibold transition-colors" :class="activeTab === tab.key
            ? 'bg-surface text-primary shadow-sm'
            : 'text-muted hover:text-secondary'" @click="activeTab = tab.key">
          {{ tab.label }}
        </button>
      </div>
    </div>

    <div v-if="activeTab === 'api'" class="space-y-8">
      <!-- API Keys Config -->
      <div class="card-surface">
        <div class="px-6 py-5 border-b border-soft bg-base-soft">
          <h3 class="text-base font-semibold text-primary">API 凭证管理</h3>
          <p class="text-sm text-muted mt-1">集中管理所有模型服务的访问凭证。</p>
        </div>
        <div class="p-6 space-y-6">
          <div class="grid gap-6 md:grid-cols-2">
            <!-- Qwen Key -->
            <div class="space-y-3">
              <label class="block text-sm font-medium text-secondary">DashScope API Key (通义千问)</label>
              <div class="relative">
                <input v-model.trim="credentialState.form.qwen_api_key" type="password" autocomplete="new-password"
                  placeholder="sk-..."
                  class="form-input w-full rounded-xl border-soft focus:border-brand-500 focus:ring-brand-500/20 text-sm py-2.5 transition-shadow bg-surface" />
                <div class="absolute inset-y-0 right-3 flex items-center">
                  <span v-if="credentialState.summary.qwen.configured"
                    class="inline-flex items-center gap-1 rounded-full bg-success-soft px-2 py-0.5 text-xs font-medium text-success">
                    <CheckIcon class="w-3 h-3" />
                    已配置
                  </span>
                  <span v-else
                    class="inline-flex items-center gap-1 rounded-full bg-base-soft px-2 py-0.5 text-xs font-medium text-muted">
                    未配置
                  </span>
                </div>
              </div>
              <div class="flex justify-end" v-if="credentialState.summary.qwen.configured">
                <button type="button" class="text-xs text-muted hover:text-danger transition-colors"
                  @click="clearCredential('qwen')">
                  清除密钥
                </button>
              </div>
            </div>

            <!-- OpenAI Key -->
            <div class="space-y-3">
              <label class="block text-sm font-medium text-secondary">OpenAI API Key (兼容接口)</label>
              <div class="relative">
                <input v-model.trim="credentialState.form.openai_api_key" type="password" autocomplete="new-password"
                  placeholder="sk-..."
                  class="form-input w-full rounded-xl border-soft focus:border-brand-500 focus:ring-brand-500/20 text-sm py-2.5 transition-shadow bg-surface" />
                <div class="absolute inset-y-0 right-3 flex items-center">
                  <span v-if="credentialState.summary.openai.configured"
                    class="inline-flex items-center gap-1 rounded-full bg-success-soft px-2 py-0.5 text-xs font-medium text-success">
                    <CheckIcon class="w-3 h-3" />
                    已配置
                  </span>
                  <span v-else
                    class="inline-flex items-center gap-1 rounded-full bg-base-soft px-2 py-0.5 text-xs font-medium text-muted">
                    未配置
                  </span>
                </div>
              </div>
              <div class="flex justify-end" v-if="credentialState.summary.openai.configured">
                <button type="button" class="text-xs text-muted hover:text-danger transition-colors"
                  @click="clearCredential('openai')">
                  清除密钥
                </button>
              </div>
            </div>
          </div>

          <div class="pt-4 border-t border-soft">
            <label class="block text-sm font-medium text-secondary mb-2">OpenAI Base URL</label>
            <div class="flex gap-4">
              <div class="flex-1">
                <input v-model.trim="credentialState.form.openai_base_url" type="text"
                  placeholder="https://api.openai.com/v1"
                  class="form-input w-full rounded-xl border-soft focus:border-brand-500 focus:ring-brand-500/20 text-sm py-2.5 transition-shadow bg-surface" />
                <p class="mt-2 text-xs text-muted">仅在使用第三方代理或自建服务时需要修改，留空则使用默认地址。</p>
              </div>
              <div class="shrink-0">
                <button type="button" class="btn-primary" :disabled="credentialState.loading"
                  @click="submitCredentials">
                  <span v-if="credentialState.loading">保存中...</span>
                  <span v-else>保存凭证</span>
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Models Configuration Grid -->
      <div class="grid gap-6 lg:grid-cols-2">
        <!-- Chat Model -->
        <section class="card-surface flex flex-col lg:col-span-2">
          <div class="px-6 py-5 border-b border-soft bg-base-soft flex items-center gap-2">
            <ChatBubbleBottomCenterTextIcon class="w-5 h-5 text-brand-600" />
            <div>
              <h3 class="text-base font-semibold text-primary">对话模型</h3>
              <p class="text-xs text-muted">用于 AI 助手问答交互</p>
            </div>
          </div>
          <form @submit.prevent="submitLlmAssistant" class="p-6 space-y-5 flex-1 flex flex-col">
            <div class="space-y-4 flex-1">
              <div class="grid grid-cols-2 gap-4">
                <div class="col-span-2">
                  <label class="block text-xs font-semibold text-muted uppercase tracking-wider mb-2">服务提供方</label>
                  <select v-model="llmState.assistant.provider"
                    class="form-select w-full rounded-xl border-soft focus:border-brand-500 focus:ring-brand-500/20 text-sm py-2.5 bg-surface">
                    <option v-for="opt in providerOptions" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
                  </select>
                </div>

                <div class="col-span-2">
                  <label class="block text-xs font-semibold text-muted uppercase tracking-wider mb-2">模型名称</label>
                  <input v-model.trim="llmState.assistant.model" type="text" :placeholder="assistantModelPlaceholder"
                    class="form-input w-full rounded-xl border-soft focus:border-brand-500 focus:ring-brand-500/20 text-sm py-2.5 bg-surface" />
                </div>

                <div v-if="llmState.assistant.provider === 'openai'" class="col-span-2">
                  <label class="block text-xs font-semibold text-muted uppercase tracking-wider mb-2">Base URL</label>
                  <input v-model.trim="llmState.assistant.base_url" type="text" placeholder="继承全局设置"
                    class="form-input w-full rounded-xl border-soft focus:border-brand-500 focus:ring-brand-500/20 text-sm py-2.5 bg-surface" />
                </div>

                <div class="col-span-2">
                  <label class="block text-xs font-semibold text-muted uppercase tracking-wider mb-2">系统提示词 (System
                    Prompt)</label>
                  <textarea v-model.trim="llmState.assistant.system_prompt" rows="4"
                    placeholder="如：你是一个专业的舆情分析助手，请结合提供的知识库内容回答问题。"
                    class="form-textarea w-full rounded-xl border-soft focus:border-brand-500 focus:ring-brand-500/20 text-sm py-2.5 transition-shadow resize-none bg-surface"></textarea>
                  <p class="mt-1.5 text-xs text-muted">定义 AI 助手的角色、语气 and 基本行为准则。</p>
                </div>

                <div>
                  <label class="block text-xs font-semibold text-muted uppercase tracking-wider mb-2">最大
                    Tokens</label>
                  <input v-model.number="llmState.assistant.max_tokens" type="number"
                    class="form-input w-full rounded-xl border-soft focus:border-brand-500 focus:ring-brand-500/20 text-sm py-2.5 bg-surface" />
                </div>
                <div>
                  <label
                    class="block text-xs font-semibold text-muted uppercase tracking-wider mb-2">Temperature</label>
                  <input v-model.number="llmState.assistant.temperature" type="number" step="0.1"
                    class="form-input w-full rounded-xl border-soft focus:border-brand-500 focus:ring-brand-500/20 text-sm py-2.5 bg-surface" />
                </div>
              </div>
            </div>
            <div class="pt-4 flex justify-end">
              <button type="submit"
                class="rounded-full bg-brand-600 px-5 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:bg-brand-500 hover:shadow disabled:opacity-60 disabled:shadow-none">保存对话配置</button>
            </div>
          </form>
        </section>

        <!-- Knowledge Base Info (New) -->
        <section class="bg-accent-faint rounded-2xl border border-soft p-6 space-y-4 lg:col-span-2">
          <div class="flex items-center gap-2">
            <BookOpenIcon class="w-5 h-5 text-accent" />
            <h3 class="text-base font-semibold text-primary">Markdown 知识库</h3>
          </div>
          <div class="grid md:grid-cols-2 gap-6 items-start">
            <div class="text-sm text-secondary space-y-2">
              <p>系统现在支持自动化的知识库注入。只需将您的研究文档、业务规范或参考资料以 <code>.md</code> 格式放入以下文件夹：</p>
              <div class="bg-surface p-2 rounded-lg border border-soft font-mono text-xs text-primary">
                backend/knowledge_base/
              </div>
              <p class="text-xs text-muted mt-2 italic">提示：后端会自动聚合该目录下所有文档内容并作为上下文提供给对话模型。</p>
            </div>
            <div class="bg-brand rounded-xl p-4 text-white">
              <h4 class="text-xs font-bold uppercase tracking-wider opacity-80 mb-2">生效方式</h4>
              <ul class="text-xs space-y-2 opacity-90">
                <li class="flex gap-2">
                  <span class="font-bold">1.</span>
                  <span>放入文件后立即对下一次对话生效</span>
                </li>
                <li class="flex gap-2">
                  <span class="font-bold">2.</span>
                  <span>建议配合上方“系统提示词”引导 AI 优先参考知识库</span>
                </li>
                <li class="flex gap-2">
                  <span class="font-bold">3.</span>
                  <span>如果文件较多，请注意不要超过模型的 Context Window 限制</span>
                </li>
              </ul>
            </div>
          </div>
        </section>

        <!-- Filter Model -->
        <section class="card-surface flex flex-col">
          <div class="px-6 py-5 border-b border-soft bg-base-soft flex items-center gap-2">
            <FunnelIcon class="w-5 h-5 text-brand-600" />
            <div>
              <h3 class="text-base font-semibold text-primary">筛选模型</h3>
              <p class="text-xs text-muted">用于数据清洗与相关性判断</p>
            </div>
          </div>
          <form @submit.prevent="submitLlmFilter" class="p-6 space-y-5 flex-1 flex flex-col">
            <div class="space-y-4 flex-1">
              <div class="grid grid-cols-2 gap-4">
                <div class="col-span-2">
                  <label class="block text-xs font-semibold text-muted uppercase tracking-wider mb-2">服务提供方</label>
                  <select v-model="llmState.filter.provider"
                    class="form-select w-full rounded-xl border-soft focus:border-brand-500 focus:ring-brand-500/20 text-sm py-2.5 bg-surface">
                    <option v-for="opt in providerOptions" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
                  </select>
                </div>
                <div class="col-span-2">
                  <label class="block text-xs font-semibold text-muted uppercase tracking-wider mb-2">模型名称</label>
                  <input v-model.trim="llmState.filter.model" type="text" :placeholder="filterModelPlaceholder"
                    class="form-input w-full rounded-xl border-soft focus:border-brand-500 focus:ring-brand-500/20 text-sm py-2.5 bg-surface" />
                </div>
                <div v-if="llmState.filter.provider === 'openai'" class="col-span-2">
                  <label class="block text-xs font-semibold text-muted uppercase tracking-wider mb-2">Base URL</label>
                  <input v-model.trim="llmState.filter.base_url" type="text" placeholder="继承全局设置"
                    class="form-input w-full rounded-xl border-soft focus:border-brand-500 focus:ring-brand-500/20 text-sm py-2.5 bg-surface" />
                </div>
                <div>
                  <label class="block text-xs font-semibold text-muted uppercase tracking-wider mb-2">QPS 限制</label>
                  <input v-model.number="llmState.filter.qps" type="number"
                    class="form-input w-full rounded-xl border-soft focus:border-brand-500 focus:ring-brand-500/20 text-sm py-2.5 bg-surface" />
                </div>
                <div>
                  <label class="block text-xs font-semibold text-muted uppercase tracking-wider mb-2">Batch
                    Size</label>
                  <input v-model.number="llmState.filter.batch_size" type="number"
                    class="form-input w-full rounded-xl border-soft focus:border-brand-500 focus:ring-brand-500/20 text-sm py-2.5 bg-surface" />
                </div>
              </div>
            </div>
            <div class="pt-4 flex justify-end">
              <button type="submit"
                class="rounded-full bg-brand-600 px-5 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:bg-brand-500 hover:shadow disabled:opacity-60 disabled:shadow-none">保存筛选配置</button>
            </div>
          </form>
        </section>

        <!-- Embedding Model -->
        <section class="card-surface flex flex-col md:col-span-2 lg:col-span-1">
          <div class="px-6 py-5 border-b border-soft bg-base-soft flex items-center gap-2">
            <CpuChipIcon class="w-5 h-5 text-brand-600" />
            <div>
              <h3 class="text-base font-semibold text-primary">向量模型</h3>
              <p class="text-xs text-muted">用于检索增强生成 (RAG) 与聚类</p>
            </div>
          </div>
          <form @submit.prevent="submitLlmEmbedding" class="p-6 space-y-5 flex-1 flex flex-col">
            <div class="space-y-4 flex-1">
              <div class="grid grid-cols-2 gap-4">
                <div class="col-span-2">
                  <label class="block text-xs font-semibold text-muted uppercase tracking-wider mb-2">服务提供方</label>
                  <select v-model="llmState.embedding.provider"
                    class="form-select w-full rounded-xl border-soft focus:border-brand-500 focus:ring-brand-500/20 text-sm py-2.5 bg-surface">
                    <option v-for="opt in providerOptions" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
                  </select>
                </div>
                <div class="col-span-2">
                  <label class="block text-xs font-semibold text-muted uppercase tracking-wider mb-2">模型名称</label>
                  <input v-model.trim="llmState.embedding.model" type="text" :placeholder="embeddingModelPlaceholder"
                    class="form-input w-full rounded-xl border-soft focus:border-brand-500 focus:ring-brand-500/20 text-sm py-2.5 bg-surface" />
                </div>
                <div v-if="llmState.embedding.provider === 'openai'" class="col-span-2">
                  <label class="block text-xs font-semibold text-muted uppercase tracking-wider mb-2">Base URL</label>
                  <input v-model.trim="llmState.embedding.base_url" type="text" placeholder="继承全局设置"
                    class="form-input w-full rounded-xl border-soft focus:border-brand-500 focus:ring-brand-500/20 text-sm py-2.5 bg-surface" />
                </div>
                <div>
                  <label class="block text-xs font-semibold text-muted uppercase tracking-wider mb-2">向量维度</label>
                  <input v-model.number="llmState.embedding.dimension" type="number"
                    class="form-input w-full rounded-xl border-soft focus:border-brand-500 focus:ring-brand-500/20 text-sm py-2.5 bg-surface" />
                </div>
              </div>
            </div>
            <div class="pt-4 flex justify-end">
              <button type="submit"
                class="rounded-full bg-brand-600 px-5 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:bg-brand-500 hover:shadow disabled:opacity-60 disabled:shadow-none">保存向量配置</button>
            </div>
          </form>
        </section>
      </div>
    </div>

    <div v-else class="space-y-6">
      <section class="card-surface flex flex-col">
        <div class="px-6 py-5 border-b border-soft bg-base-soft flex items-center gap-2">
          <SparklesIcon class="w-5 h-5 text-brand-600" />
          <div>
            <h3 class="text-base font-semibold text-primary">LangChain 配置</h3>
            <p class="text-xs text-muted">用于 Report + Analyze 摘要调用链路（支持回退）</p>
          </div>
        </div>
        <form @submit.prevent="submitLlmLangchain" class="p-6 space-y-5">
          <div class="space-y-4">
            <label class="inline-flex items-center gap-2 text-sm font-medium text-secondary">
              <input v-model="llmState.langchain.enabled" type="checkbox"
                class="h-4 w-4 rounded border-soft text-brand-600 focus:ring-brand-500/30 bg-surface" />
              启用 LangChain（关闭时自动走原有直连调用）
            </label>

            <div class="grid grid-cols-2 gap-4">
              <div class="col-span-2">
                <label class="block text-xs font-semibold text-muted uppercase tracking-wider mb-2">Base URL 预设</label>
                <select v-model="langchainBaseUrlMode"
                  class="form-select w-full rounded-xl border-soft focus:border-brand-500 focus:ring-brand-500/20 text-sm py-2.5 bg-surface">
                  <option value="dashscope">阿里云 DashScope（默认）</option>
                  <option value="openai">OpenAI 官方</option>
                  <option value="custom">自定义</option>
                </select>
              </div>

              <div class="col-span-2">
                <label class="block text-xs font-semibold text-muted uppercase tracking-wider mb-2">默认模型</label>
                <input v-model.trim="llmState.langchain.model" type="text" :placeholder="langchainModelPlaceholder"
                  class="form-input w-full rounded-xl border-soft focus:border-brand-500 focus:ring-brand-500/20 text-sm py-2.5 bg-surface" />
              </div>

              <div>
                <label class="block text-xs font-semibold text-muted uppercase tracking-wider mb-2">Report 模型</label>
                <input v-model.trim="llmState.langchain.report_model" type="text" placeholder="留空则跟随默认模型"
                  class="form-input w-full rounded-xl border-soft focus:border-brand-500 focus:ring-brand-500/20 text-sm py-2.5 bg-surface" />
              </div>
              <div>
                <label class="block text-xs font-semibold text-muted uppercase tracking-wider mb-2">Analyze 摘要模型</label>
                <input v-model.trim="llmState.langchain.analyze_summary_model" type="text" placeholder="留空则跟随默认模型"
                  class="form-input w-full rounded-xl border-soft focus:border-brand-500 focus:ring-brand-500/20 text-sm py-2.5 bg-surface" />
              </div>

              <div class="col-span-2">
                <label class="block text-xs font-semibold text-muted uppercase tracking-wider mb-2">
                  {{ langchainBaseUrlMode === 'custom' ? '自定义 Base URL' : '当前 Base URL' }}
                </label>
                <input v-if="langchainBaseUrlMode === 'custom'" v-model.trim="llmState.langchain.base_url" type="text"
                  placeholder="请输入 OpenAI 兼容接口地址"
                  class="form-input w-full rounded-xl border-soft focus:border-brand-500 focus:ring-brand-500/20 text-sm py-2.5 bg-surface" />
                <input v-else :value="effectiveLangchainBaseUrl" type="text" disabled
                  class="form-input w-full rounded-xl border-soft focus:border-brand-500 focus:ring-brand-500/20 text-sm py-2.5 bg-base-soft text-muted cursor-not-allowed" />
              </div>

              <div>
                <label class="block text-xs font-semibold text-muted uppercase tracking-wider mb-2">Temperature</label>
                <input v-model.number="llmState.langchain.temperature" type="number" step="0.1"
                  class="form-input w-full rounded-xl border-soft focus:border-brand-500 focus:ring-brand-500/20 text-sm py-2.5 bg-surface" />
              </div>
              <div>
                <label class="block text-xs font-semibold text-muted uppercase tracking-wider mb-2">Max Tokens</label>
                <input v-model.number="llmState.langchain.max_tokens" type="number"
                  class="form-input w-full rounded-xl border-soft focus:border-brand-500 focus:ring-brand-500/20 text-sm py-2.5 bg-surface" />
              </div>
              <div>
                <label class="block text-xs font-semibold text-muted uppercase tracking-wider mb-2">超时（秒）</label>
                <input v-model.number="llmState.langchain.timeout" type="number" step="1"
                  class="form-input w-full rounded-xl border-soft focus:border-brand-500 focus:ring-brand-500/20 text-sm py-2.5 bg-surface" />
              </div>
              <div>
                <label class="block text-xs font-semibold text-muted uppercase tracking-wider mb-2">重试次数</label>
                <input v-model.number="llmState.langchain.max_retries" type="number"
                  class="form-input w-full rounded-xl border-soft focus:border-brand-500 focus:ring-brand-500/20 text-sm py-2.5 bg-surface" />
              </div>
            </div>
          </div>
          <div class="pt-4 flex justify-end">
            <button type="submit"
              class="rounded-full bg-brand-600 px-5 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:bg-brand-500 hover:shadow disabled:opacity-60 disabled:shadow-none">
              保存 LangChain 配置
            </button>
          </div>
        </form>
      </section>
    </div>
  </section>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import {
  SparklesIcon,
  CheckBadgeIcon as CheckIcon,
  ExclamationCircleIcon,
  CheckCircleIcon,
  ChatBubbleBottomCenterTextIcon,
  FunnelIcon,
  CpuChipIcon,
  BookOpenIcon
} from '@heroicons/vue/24/outline'
import { useApiBase } from '../../composables/useApiBase'

const { ensureApiBase } = useApiBase()
const buildApiUrl = async (path) => {
  const baseUrl = await ensureApiBase()
  return `${baseUrl}${path}`
}
const providerOptions = [
  { label: '阿里通义千问（DashScope）', value: 'qwen' },
  { label: 'OpenAI / 兼容 API', value: 'openai' }
]
const LANGCHAIN_DASHSCOPE_BASE_URL = 'https://dashscope.aliyuncs.com/compatible-mode/v1'
const LANGCHAIN_OPENAI_BASE_URL = 'https://api.openai.com/v1'
const aiTabs = [
  { key: 'api', label: 'AI API 配置' },
  { key: 'langchain', label: 'LangChain 配置' }
]
const activeTab = ref('api')
const langchainBaseUrlMode = ref('dashscope')

const llmState = reactive({
  filter: {
    provider: 'qwen',
    model: '',
    qps: 0,
    batch_size: 1,
    truncation: 0,
    base_url: ''
  },
  assistant: {
    provider: 'qwen',
    model: '',
    max_tokens: 0,
    temperature: 0,
    base_url: '',
    system_prompt: ''
  },
  embedding: {
    provider: 'qwen',
    model: '',
    dimension: 0,
    base_url: ''
  },
  langchain: {
    enabled: false,
    provider: 'qwen',
    model: '',
    report_model: '',
    analyze_summary_model: '',
    base_url: '',
    temperature: 0.3,
    max_tokens: 3000,
    timeout: 120,
    max_retries: 2
  },
  loading: false,
  error: '',
  message: ''
})

const credentialState = reactive({
  summary: {
    qwen: { configured: false, last_four: '' },
    openai: { configured: false, last_four: '' },
    openai_base_url: ''
  },
  form: {
    qwen_api_key: '',
    openai_api_key: '',
    openai_base_url: ''
  },
  loading: false,
  error: '',
  message: ''
})

const filterModelPlaceholder = computed(() =>
  llmState.filter.provider === 'openai' ? '如：gpt-3.5-turbo' : '如：qwen-plus'
)
const assistantModelPlaceholder = computed(() =>
  llmState.assistant.provider === 'openai' ? '如：gpt-4o-mini' : '如：qwen-turbo'
)
const embeddingModelPlaceholder = computed(() =>
  llmState.embedding.provider === 'openai' ? '如：text-embedding-3-small' : '如：text-embedding-v4'
)
const langchainModelPlaceholder = computed(() =>
  llmState.langchain.provider === 'openai' ? '如：gpt-4o-mini' : '如：qwen-plus'
)
const effectiveLangchainBaseUrl = computed(() => {
  const raw = (llmState.langchain.base_url || '').trim()
  if (langchainBaseUrlMode.value === 'dashscope') {
    return raw || LANGCHAIN_DASHSCOPE_BASE_URL
  }
  if (langchainBaseUrlMode.value === 'openai') {
    return raw || LANGCHAIN_OPENAI_BASE_URL
  }
  return raw
})

const inferLangchainProvider = (url) => {
  const normalized = String(url || '').toLowerCase()
  return normalized.includes('dashscope.aliyuncs.com') ? 'qwen' : 'openai'
}

const syncLangchainBaseUrlModeFromState = () => {
  const provider = String(llmState.langchain.provider || '').toLowerCase()
  const baseUrl = String(llmState.langchain.base_url || '').trim()

  if (!baseUrl) {
    langchainBaseUrlMode.value = provider === 'openai' ? 'openai' : 'dashscope'
    if (langchainBaseUrlMode.value === 'dashscope') {
      llmState.langchain.provider = 'qwen'
    } else {
      llmState.langchain.provider = 'openai'
    }
    return
  }

  if (baseUrl === LANGCHAIN_DASHSCOPE_BASE_URL) {
    langchainBaseUrlMode.value = 'dashscope'
    llmState.langchain.provider = 'qwen'
    return
  }

  if (baseUrl === LANGCHAIN_OPENAI_BASE_URL) {
    langchainBaseUrlMode.value = 'openai'
    llmState.langchain.provider = 'openai'
    return
  }

  langchainBaseUrlMode.value = 'custom'
  llmState.langchain.provider = inferLangchainProvider(baseUrl)
}

watch(
  () => llmState.filter.provider,
  (provider) => {
    if (provider !== 'openai') {
      llmState.filter.base_url = ''
    }
  }
)

watch(
  () => llmState.assistant.provider,
  (provider) => {
    if (provider !== 'openai') {
      llmState.assistant.base_url = ''
    }
  }
)

watch(
  () => llmState.embedding.provider,
  (provider) => {
    if (provider !== 'openai') {
      llmState.embedding.base_url = ''
    }
  }
)

watch(
  () => langchainBaseUrlMode.value,
  (mode) => {
    if (mode === 'dashscope') {
      llmState.langchain.provider = 'qwen'
      llmState.langchain.base_url = LANGCHAIN_DASHSCOPE_BASE_URL
      return
    }
    if (mode === 'openai') {
      llmState.langchain.provider = 'openai'
      llmState.langchain.base_url = LANGCHAIN_OPENAI_BASE_URL
      return
    }
    llmState.langchain.provider = inferLangchainProvider(llmState.langchain.base_url)
  }
)

watch(
  () => llmState.langchain.base_url,
  (url) => {
    if (langchainBaseUrlMode.value !== 'custom') {
      return
    }
    llmState.langchain.provider = inferLangchainProvider(url)
  }
)

const applyCredentialResult = (result) => {
  const qwenSummary = result && typeof result === 'object' && typeof result.qwen === 'object' ? result.qwen : {}
  const openaiSummary = result && typeof result === 'object' && typeof result.openai === 'object' ? result.openai : {}
  credentialState.summary.qwen.configured = Boolean(qwenSummary.configured)
  credentialState.summary.qwen.last_four = qwenSummary.last_four || ''
  credentialState.summary.openai.configured = Boolean(openaiSummary.configured)
  credentialState.summary.openai.last_four = openaiSummary.last_four || ''
  credentialState.summary.openai_base_url = typeof result.openai_base_url === 'string' ? result.openai_base_url : ''
  credentialState.form.openai_base_url = credentialState.summary.openai_base_url
  credentialState.form.qwen_api_key = ''
  credentialState.form.openai_api_key = ''
}

const fetchLlmCredentials = async () => {
  credentialState.loading = true
  credentialState.error = ''
  credentialState.message = ''
  try {
    const endpoint = await buildApiUrl('/settings/llm/credentials')
    const response = await fetch(endpoint)
    if (!response.ok) {
      throw new Error('读取 API 凭证失败')
    }
    const payload = await response.json()
    const result = payload && typeof payload === 'object' ? payload.data ?? {} : {}
    applyCredentialResult(result)
  } catch (err) {
    credentialState.error = err instanceof Error ? err.message : '读取 API 凭证失败'
  } finally {
    credentialState.loading = false
  }
}

const updateCredentials = async (payload, successMessage = 'API 凭证已更新') => {
  if (!payload || Object.keys(payload).length === 0) {
    return
  }
  credentialState.loading = true
  credentialState.error = ''
  credentialState.message = ''
  try {
    const endpoint = await buildApiUrl('/settings/llm/credentials')
    const response = await fetch(endpoint, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    })
    if (!response.ok) {
      throw new Error('保存 API 凭证失败')
    }
    const payloadResult = await response.json()
    const result = payloadResult && typeof payloadResult === 'object' ? payloadResult.data ?? {} : {}
    applyCredentialResult(result)
    credentialState.message = successMessage
  } catch (err) {
    credentialState.error = err instanceof Error ? err.message : '保存 API 凭证失败'
  } finally {
    credentialState.loading = false
  }
}

const submitCredentials = async () => {
  credentialState.message = ''
  credentialState.error = ''
  const payload = {}
  const qwenInput = (credentialState.form.qwen_api_key || '').trim()
  const openaiInput = (credentialState.form.openai_api_key || '').trim()
  const baseUrlInput = (credentialState.form.openai_base_url || '').trim()
  const currentBaseUrl = credentialState.summary.openai_base_url || ''

  if (qwenInput) {
    payload.qwen_api_key = qwenInput
  }
  if (openaiInput) {
    payload.openai_api_key = openaiInput
  }
  if (baseUrlInput !== currentBaseUrl) {
    payload.openai_base_url = baseUrlInput
  }

  if (Object.keys(payload).length === 0) {
    credentialState.error = '请填写需要更新的字段'
    return
  }

  await updateCredentials(payload)
}

const clearCredential = async (provider) => {
  credentialState.error = ''
  credentialState.message = ''
  if (provider === 'qwen') {
    await updateCredentials({ qwen_api_key: '' }, '千问 API Key 已清空')
  } else if (provider === 'openai') {
    await updateCredentials({ openai_api_key: '' }, 'OpenAI API Key 已清空')
  }
}

const submitLlmFilter = async () => {
  llmState.message = ''
  llmState.error = ''
  try {
    const endpoint = await buildApiUrl('/settings/llm/filter')
    const response = await fetch(endpoint, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(llmState.filter)
    })
    if (!response.ok) {
      throw new Error('保存筛选配置失败')
    }
    llmState.message = '筛选配置已保存'
  } catch (err) {
    llmState.error = err instanceof Error ? err.message : '保存筛选配置失败'
  }
}

const submitLlmAssistant = async () => {
  llmState.message = ''
  llmState.error = ''
  try {
    const endpoint = await buildApiUrl('/settings/llm/assistant')
    const response = await fetch(endpoint, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(llmState.assistant)
    })
    if (!response.ok) {
      throw new Error('保存对话配置失败')
    }
    llmState.message = '对话配置已保存'
  } catch (err) {
    llmState.error = err instanceof Error ? err.message : '保存对话配置失败'
  }
}

const submitLlmEmbedding = async () => {
  llmState.message = ''
  llmState.error = ''
  try {
    const endpoint = await buildApiUrl('/settings/llm/embedding')
    const response = await fetch(endpoint, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(llmState.embedding)
    })
    if (!response.ok) {
      throw new Error('保存向量化配置失败')
    }
    llmState.message = '向量化配置已保存'
  } catch (err) {
    llmState.error = err instanceof Error ? err.message : '保存向量化配置失败'
  }
}

const submitLlmLangchain = async () => {
  llmState.message = ''
  llmState.error = ''
  try {
    const endpoint = await buildApiUrl('/settings/llm/langchain')
    const response = await fetch(endpoint, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(llmState.langchain)
    })
    if (!response.ok) {
      throw new Error('保存 LangChain 配置失败')
    }
    llmState.message = 'LangChain 配置已保存'
  } catch (err) {
    llmState.error = err instanceof Error ? err.message : '保存 LangChain 配置失败'
  }
}

const fetchLlmSettings = async () => {
  llmState.loading = true
  llmState.error = ''
  try {
    const endpoint = await buildApiUrl('/settings/llm')
    const response = await fetch(endpoint)
    if (!response.ok) {
      throw new Error('读取模型配置失败')
    }
    const payload = await response.json()
    const result = payload && typeof payload === 'object' ? payload.data ?? {} : {}
    const filterConfig =
      result && typeof result === 'object'
        ? (result.filter_llm && typeof result.filter_llm === 'object'
          ? result.filter_llm
          : result.filter && typeof result.filter === 'object'
            ? result.filter
            : {})
        : {}
    if (filterConfig && typeof filterConfig === 'object') {
      Object.assign(llmState.filter, filterConfig)
    }
    if (!llmState.filter.provider) {
      llmState.filter.provider = 'qwen'
    }
    if (result.assistant && typeof result.assistant === 'object') {
      Object.assign(llmState.assistant, result.assistant)
    }
    if (!llmState.assistant.provider) {
      llmState.assistant.provider = 'qwen'
    }
    if (result.embedding_llm && typeof result.embedding_llm === 'object') {
      Object.assign(llmState.embedding, result.embedding_llm)
    } else if (result.embedding && typeof result.embedding === 'object') {
      Object.assign(llmState.embedding, result.embedding)
    }
    if (!llmState.embedding.provider) {
      llmState.embedding.provider = 'qwen'
    }
    if (result.langchain && typeof result.langchain === 'object') {
      Object.assign(llmState.langchain, result.langchain)
    }
    if (!llmState.langchain.provider) {
      llmState.langchain.provider = 'qwen'
    }
    llmState.langchain.enabled = Boolean(llmState.langchain.enabled)
    syncLangchainBaseUrlModeFromState()
  } catch (err) {
    llmState.error = err instanceof Error ? err.message : '读取模型配置失败'
  } finally {
    llmState.loading = false
  }
}

onMounted(() => {
  fetchLlmSettings()
  fetchLlmCredentials()
})
</script>
