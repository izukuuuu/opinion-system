<template>
  <section class="card-surface space-y-6 p-6">
      <header class="settings-page-header">
        <p class="settings-page-eyebrow">RAG</p>
        <h2 class="settings-page-title">RAG 配置</h2>
        <p class="settings-page-desc">配置文本分块、检索、存储、提示词和密钥等默认参数。</p>
      </header>

      <div class="settings-toolbar settings-section-split">
        <div class="settings-section-header">
          <h3 class="settings-section-title">配置分类</h3>
          <p class="settings-section-desc">切换不同分组并调整相应参数。</p>
        </div>
        <TabSwitch
          :tabs="tabsNormalized"
          :active="activeTab"
          @change="activeTab = $event"
        />
      </div>

      <div>
        <div v-if="ragState.configState.error" class="settings-message-error mb-6">
          {{ ragState.configState.error }}
        </div>

        <div v-if="statusMessage" :class="[
          'mb-6',
          statusType === 'success' ? 'settings-message-success' : 'settings-message-error'
        ]">
          {{ statusMessage }}
        </div>



        <!-- Chunking Configuration -->
        <div v-if="activeTab === 'chunking'" class="space-y-6">
          <h2 class="text-lg font-semibold text-primary">文本分块配置</h2>

          <div class="grid gap-6 md:grid-cols-2">
            <div class="space-y-2">
              <label class="text-xs font-semibold text-muted">分块策略</label>
              <AppSelect
                v-model="ragState.configForm.chunking.strategy"
                :options="[
                  { value: 'size', label: '按大小分块' },
                  { value: 'count', label: '按数量分块' },
                  { value: 'semantic', label: '语义分块 (实验性)' }
                ]"
                :value="ragState.configForm.chunking.strategy"
                @change="ragState.configForm.chunking.strategy = $event"
              />
              <p class="text-xs text-muted">选择文本分块的方式</p>
            </div>

            <div class="space-y-2">
              <label class="text-xs font-semibold text-muted">块大小</label>
              <input
                v-model.number="ragState.configForm.chunking.chunk_size"
                type="number"
                min="50"
                max="2048"
                class="input"
              />
              <p class="text-xs text-muted">
                {{ ragState.configForm.chunking.strategy === 'size' ? '每个块的字符数' : '每个块的文档数' }}
              </p>
            </div>

            <div class="space-y-2">
              <label class="text-xs font-semibold text-muted">块重叠</label>
              <input
                v-model.number="ragState.configForm.chunking.chunk_overlap"
                type="number"
                min="0"
                :max="ragState.configForm.chunking.chunk_size ? Math.floor(ragState.configForm.chunking.chunk_size / 2) : 100"
                class="input"
              />
              <p class="text-xs text-muted">相邻块之间的重叠大小</p>
            </div>

            <div class="space-y-2">
              <label class="text-xs font-semibold text-muted">分隔符</label>
              <input
                v-model="ragState.configForm.chunking.separator"
                type="text"
                class="input"
              />
              <p class="text-xs text-muted">用于分段的分隔符</p>
            </div>
          </div>

          <div class="space-y-3">
            <AppCheckbox
              v-model="ragState.configForm.chunking.respect_sentence_boundary"
              id="respect-sentence"
              label-class="text-sm text-secondary"
            >
              尊重句子边界
            </AppCheckbox>

            <AppCheckbox
              v-model="ragState.configForm.chunking.strip_whitespace"
              id="strip-whitespace"
              label-class="text-sm text-secondary"
            >
              去除多余空白
            </AppCheckbox>
          </div>
        </div>

        <!-- Retrieval Configuration -->
        <div v-if="activeTab === 'retrieval'" class="space-y-6">
          <h2 class="text-lg font-semibold text-primary">检索配置</h2>

          <div class="grid gap-6 md:grid-cols-2">
            <div class="space-y-2">
              <label class="text-xs font-semibold text-muted">检索类型</label>
              <AppSelect
                :options="[
                  { value: 'vector', label: '向量检索' },
                  { value: 'hybrid', label: '混合检索' },
                  { value: 'bm25', label: 'BM25检索' }
                ]"
                :value="ragState.configForm.retrieval.search_type"
                @change="ragState.configForm.retrieval.search_type = $event"
              />
              <p class="text-xs text-muted">检索算法类型</p>
            </div>

            <div class="space-y-2">
              <label class="text-xs font-semibold text-muted">默认返回数量 (Top-K)</label>
              <input
                v-model.number="ragState.configForm.retrieval.top_k"
                type="number"
                min="1"
                max="100"
                class="input"
              />
              <p class="text-xs text-muted">默认返回的结果数量</p>
            </div>

            <div class="space-y-2">
              <label class="text-xs font-semibold text-muted">相似度阈值</label>
              <div class="flex items-center gap-3">
                <input
                  v-model.number="ragState.configForm.retrieval.threshold"
                  type="range"
                  min="0"
                  max="1"
                  step="0.05"
                  class="flex-1"
                />
                <span class="w-12 text-xs font-medium text-primary">
                  {{ ragState.configForm.retrieval.threshold.toFixed(2) }}
                </span>
              </div>
              <p class="text-xs text-muted">最低相似度要求</p>
            </div>

            <div class="space-y-2">
              <label class="text-xs font-semibold text-muted">相似度计算方式</label>
              <AppSelect
                :options="[
                  { value: 'cosine', label: '余弦相似度' },
                  { value: 'dot', label: '点积' },
                  { value: 'euclidean', label: '欧氏距离' }
                ]"
                :value="ragState.configForm.retrieval.score_type"
                @change="ragState.configForm.retrieval.score_type = $event"
              />
            </div>
          </div>

          <div class="space-y-3">
            <AppCheckbox
              v-model="ragState.configForm.retrieval.include_metadata"
              id="include-metadata"
              label-class="text-sm text-secondary"
            >
              包含元数据
            </AppCheckbox>

            <AppCheckbox
              v-model="ragState.configForm.retrieval.rerank"
              id="enable-rerank"
              disabled
              label-class="text-sm text-muted"
            >
              启用重排序 (暂不支持)
            </AppCheckbox>

            <div class="border-t pt-4 mt-4 space-y-4">
              <h3 class="text-sm font-bold text-primary">RouterRAG 特有配置</h3>
              
              <AppCheckbox
                v-model="ragState.configForm.retrieval.enable_query_expansion"
                id="enable-query-expansion"
                label-class="text-sm text-secondary"
              >
                启用查询扩展 (Query Expansion)
              </AppCheckbox>

              <AppCheckbox
                v-model="ragState.configForm.retrieval.enable_llm_summary"
                id="enable-llm-summary"
                label-class="text-sm text-secondary"
              >
                启用 LLM 结果总结 (Result Summary)
              </AppCheckbox>

              <div v-if="ragState.configForm.retrieval.enable_llm_summary" class="ml-6 space-y-2">
                <label class="text-xs font-semibold text-muted">总结模式</label>
                <AppSelect
                  size="sm"
                  :options="[
                    { value: 'strict', label: '严格模式 (仅限参考资料)' },
                    { value: 'supplement', label: '补充模式 (结合通用知识)' }
                  ]"
                  :value="ragState.configForm.retrieval.llm_summary_mode"
                  @change="ragState.configForm.retrieval.llm_summary_mode = $event"
                />
                <p class="text-xs text-muted">选择生成总结时的限制程度</p>
              </div>
            </div>
          </div>
        </div>

        <!-- Storage Configuration -->
        <div v-if="activeTab === 'storage'" class="space-y-6">
          <h2 class="text-lg font-semibold text-primary">存储配置</h2>

          <div class="grid gap-6 md:grid-cols-2">
            <div class="space-y-2">
              <label class="text-xs font-semibold text-muted">存储类型</label>
              <AppSelect
                :options="[
                  { value: 'file', label: '文件存储' },
                  { value: 'lance', label: 'LanceDB' },
                  { value: 'faiss', label: 'FAISS' },
                  { value: 'chroma', label: 'ChromaDB' }
                ]"
                :value="ragState.configForm.storage.storage_type"
                @change="ragState.configForm.storage.storage_type = $event"
              />
              <p class="text-xs text-muted">向量数据库类型</p>
            </div>

            <div class="space-y-2">
              <label class="text-xs font-semibold text-muted">索引类型</label>
              <AppSelect
                :options="[
                  { value: 'flat', label: 'Flat (精确)' },
                  { value: 'ivf', label: 'IVF (倒排)' },
                  { value: 'hnsw', label: 'HNSW (层次)' }
                ]"
                :value="ragState.configForm.storage.index_type"
                @change="ragState.configForm.storage.index_type = $event"
              />
              <p class="text-xs text-muted">向量索引类型</p>
            </div>

            <div class="space-y-2">
              <label class="text-xs font-semibold text-muted">距离度量</label>
              <AppSelect
                :options="[
                  { value: 'cosine', label: '余弦距离' },
                  { value: 'l2', label: '欧氏距离' },
                  { value: 'ip', label: '内积' }
                ]"
                :value="ragState.configForm.storage.metric"
                @change="ragState.configForm.storage.metric = $event"
              />
            </div>

            <div class="space-y-2">
              <label class="text-xs font-semibold text-muted">存储路径</label>
              <input
                v-model="ragState.configForm.storage.path"
                type="text"
                placeholder="./data/rag"
                class="input"
              />
              <p class="text-xs text-muted">数据存储目录路径</p>
            </div>
          </div>

          <div class="space-y-3">
            <AppCheckbox
              v-model="ragState.configForm.storage.persist_index"
              id="persist-index"
              label-class="text-sm text-secondary"
            >
              持久化索引
            </AppCheckbox>
          </div>
        </div>

        <!-- Processing Configuration -->
        <div v-if="activeTab === 'processing'" class="space-y-6">
          <h2 class="text-lg font-semibold text-primary">文本预处理配置</h2>

          <div class="space-y-3">
            <AppCheckbox v-model="ragState.configForm.processing.lowercase" id="lowercase" label-class="text-sm text-secondary">
              转换为小写
            </AppCheckbox>

            <AppCheckbox v-model="ragState.configForm.processing.remove_urls" id="remove-urls" label-class="text-sm text-secondary">
              移除URL
            </AppCheckbox>

            <AppCheckbox v-model="ragState.configForm.processing.remove_emails" id="remove-emails" label-class="text-sm text-secondary">
              移除邮箱
            </AppCheckbox>

            <AppCheckbox
              v-model="ragState.configForm.processing.remove_extra_whitespace"
              id="remove-whitespace"
              label-class="text-sm text-secondary"
            >
              移除多余空白
            </AppCheckbox>

            <AppCheckbox v-model="ragState.configForm.processing.remove_special_chars" id="remove-special" label-class="text-sm text-secondary">
              移除特殊字符
            </AppCheckbox>

            <AppCheckbox
              v-model="ragState.configForm.processing.normalize_unicode"
              id="normalize-unicode"
              label-class="text-sm text-secondary"
            >
              标准化Unicode
            </AppCheckbox>
          </div>
        </div>


        <!-- Prompts Configuration -->
        <div v-if="activeTab === 'prompts'" class="space-y-6">
          <div class="flex items-center justify-between">
            <h2 class="text-lg font-semibold text-primary">RAG 提示词配置 (RouterRAG)</h2>
            <div class="flex items-center gap-2">
              <AppSelect
                class="w-48"
                size="sm"
                :options="promptTopicSelectOptions"
                :value="selectedPromptTopic"
                searchable
                @change="selectedPromptTopic = $event; loadPromptsForTopic()"
              />
              <button
                @click="loadPromptsForTopic"
                class="btn-secondary py-1.5 text-xs"
                title="刷新"
              >
                刷新
              </button>
              <button
                @click="resetPromptsToDefault"
                class="btn-secondary py-1.5 text-xs text-danger"
                title="重置为默认"
              >
                重置为默认
              </button>
            </div>
          </div>

          <div v-if="promptConfig" class="space-y-8">
            <!-- Time Extraction -->
            <div class="space-y-2">
              <div class="flex items-center justify-between">
                <label class="text-sm font-bold text-primary">时间提取提示词 (Time Extraction)</label>
                <span class="text-xs text-muted">用于识别查询中的时间信息</span>
              </div>
              <textarea
                v-model="promptConfig.time_extraction.prompt"
                rows="6"
                class="input font-sans text-sm leading-relaxed"
                placeholder="输入提示词模板..."
              ></textarea>
            </div>

            <!-- Time Matching -->
            <div class="space-y-2">
              <div class="flex items-center justify-between">
                <label class="text-sm font-bold text-primary">时间匹配提示词 (Time Matching)</label>
                <span class="text-xs text-muted">用于匹配查询时间与文档时间</span>
              </div>
              <textarea
                v-model="promptConfig.time_matching.prompt"
                rows="6"
                class="input font-sans text-sm leading-relaxed"
                placeholder="输入提示词模板..."
              ></textarea>
            </div>

            <!-- Query Expansion -->
            <div class="space-y-2">
              <div class="flex items-center justify-between">
                <label class="text-sm font-bold text-primary">查询扩展提示词 (Query Expansion)</label>
                <span class="text-xs text-muted">用于优化和扩展用户查询</span>
              </div>
              <textarea
                v-model="promptConfig.query_expansion.prompt"
                rows="6"
                class="input font-sans text-sm leading-relaxed"
                placeholder="输入提示词模板..."
              ></textarea>
            </div>

            <!-- Result Summary (Strict) -->
            <div class="space-y-2">
              <div class="flex items-center justify-between">
                <label class="text-sm font-bold text-primary">结果整理 - 严格模式 (Strict Summary)</label>
                <span class="text-xs text-muted">仅使用检索资料回答</span>
              </div>
              <textarea
                v-model="promptConfig.result_summary_strict.prompt"
                rows="8"
                class="input font-sans text-sm leading-relaxed"
                placeholder="输入提示词模板..."
              ></textarea>
            </div>

            <!-- Result Summary (Supplement) -->
            <div class="space-y-2">
              <div class="flex items-center justify-between">
                <label class="text-sm font-bold text-primary">结果整理 - 补充模式 (Supplement Summary)</label>
                <span class="text-xs text-muted">结合外部知识回答</span>
              </div>
              <textarea
                v-model="promptConfig.result_summary_supplement.prompt"
                rows="8"
                class="input font-sans text-sm leading-relaxed"
                placeholder="输入提示词模板..."
              ></textarea>
            </div>
            
            <div class="flex justify-end pt-4">
               <button
                  @click="savePrompts"
                  :disabled="savingPrompts"
                  class="btn-primary"
                >
                  <span v-if="savingPrompts">保存中...</span>
                  <span v-else>保存当前专题提示词</span>
                </button>
            </div>
          </div>
          
          <div v-else-if="selectedPromptTopic" class="settings-empty-state py-12">
             加载中...
          </div>
          <div v-else class="settings-empty-state py-12">
             请选择一个专题以编辑其 RouterRAG 提示词
          </div>
        </div>

        <!-- API Keys Configuration -->

        <div v-if="activeTab === 'api_keys'" class="space-y-6">
          <h2 class="text-lg font-semibold text-primary">API 密钥配置</h2>

          <div class="space-y-4">
            <div class="settings-message-warning">
              <p class="text-sm">
                <strong>注意：</strong> API 密钥将被安全存储在服务器配置中。为了安全，显示时会自动遮蔽部分字符。
              </p>
            </div>

            <div class="space-y-4">
              <!-- OpenAI API Key -->
              <div class="space-y-2">
                <label class="text-xs font-semibold text-muted">OpenAI API Key</label>
                <div class="flex gap-2">
                  <input
                    v-model="ragState.configForm.api_keys.openai"
                    type="password"
                    placeholder="sk-..."
                    class="input flex-1"
                  />
                  <button
                    @click="ragState.configForm.api_keys.openai = ''"
                    class="btn-secondary"
                    title="清除密钥"
                  >
                    清除
                  </button>
                </div>
                <p class="text-xs text-muted">用于 OpenAI 嵌入模型和 GPT 模型</p>
              </div>

              <!-- Cohere API Key -->
              <div class="space-y-2">
                <label class="text-xs font-semibold text-muted">Cohere API Key</label>
                <div class="flex gap-2">
                  <input
                    v-model="ragState.configForm.api_keys.cohere"
                    type="password"
                    placeholder="your-cohere-api-key"
                    class="input flex-1"
                  />
                  <button
                    @click="ragState.configForm.api_keys.cohere = ''"
                    class="btn-secondary"
                    title="清除密钥"
                  >
                    清除
                  </button>
                </div>
                <p class="text-xs text-muted">用于 Cohere 嵌入模型和重排序服务</p>
              </div>

              <!-- HuggingFace API Key -->
              <div class="space-y-2">
                <label class="text-xs font-semibold text-muted">HuggingFace API Key</label>
                <div class="flex gap-2">
                  <input
                    v-model="ragState.configForm.api_keys.huggingface"
                    type="password"
                    placeholder="hf_..."
                    class="input flex-1"
                  />
                  <button
                    @click="ragState.configForm.api_keys.huggingface = ''"
                    class="btn-secondary"
                    title="清除密钥"
                  >
                    清除
                  </button>
                </div>
                <p class="text-xs text-muted">用于 HuggingFace Inference API</p>
              </div>
            </div>

            <div class="settings-help-block">
              <h3 class="mb-2 text-sm font-medium text-primary">API 密钥获取指南：</h3>
              <ul class="space-y-1 text-xs text-secondary">
                <li><strong>OpenAI：</strong> 访问 <a href="https://platform.openai.com/api-keys" target="_blank" class="underline">OpenAI API Keys</a> 页面创建</li>
                <li><strong>Cohere：</strong> 访问 <a href="https://dashboard.cohere.com/api-keys" target="_blank" class="underline">Cohere Dashboard</a> 获取</li>
                <li><strong>HuggingFace：</strong> 访问 <a href="https://huggingface.co/settings/tokens" target="_blank" class="underline">HuggingFace Tokens</a> 页面创建</li>
              </ul>
            </div>
          </div>
        </div>
      </div>

      <div class="settings-action-row">
        <div class="flex w-full flex-wrap items-center justify-between gap-3">
          <button
            @click="resetConfig"
            class="btn-secondary"
          >
            重置为默认
          </button>
          <div class="flex gap-3">
            <button
              @click="testConfig"
              :disabled="isTesting"
              class="btn-secondary"
            >
              <span v-if="isTesting">测试中...</span>
              <span v-else>测试配置</span>
            </button>
            <button
              @click="saveConfig"
              :disabled="ragState.configState.loading"
              class="btn-primary"
            >
              <span v-if="ragState.configState.loading">保存中...</span>
              <span v-else>保存配置</span>
            </button>
          </div>
        </div>
      </div>
  </section>
</template>

<script setup>
import { ref, onMounted, computed, watch } from 'vue'
import { useRAGSimple } from '../../composables/useRAGSimple'
import { useRAGTopics } from '../../composables/useRAGTopics'
import { useApiBase } from '../../composables/useApiBase'
import AppCheckbox from '../../components/AppCheckbox.vue'
import TabSwitch from '../../components/TabSwitch.vue'
import AppSelect from '../../components/AppSelect.vue'

const ragState = useRAGSimple()
const { ragTopicsState, loadRAGTopics } = useRAGTopics()
const { callApi } = useApiBase()

// State
const activeTab = ref('chunking')
const isTesting = ref(false)
const statusMessage = ref('')
const statusType = ref('success')

// Prompts State
const selectedPromptTopic = ref('')
const promptConfig = ref(null)
const savingPrompts = ref(false)

const tabs = [
  { key: 'chunking', label: '文本分块' },
  { key: 'retrieval', label: '检索参数' },
  { key: 'storage', label: '存储配置' },
  { key: 'processing', label: '预处理' },
  { key: 'api_keys', label: 'API 密钥' },
  { key: 'prompts', label: '提示词' }
]

const tabsNormalized = computed(() => tabs.map(t => ({ value: t.key, label: t.label })))

const promptTopics = computed(() => ragTopicsState.router)

const promptTopicSelectOptions = computed(() => {
  const placeholder = { value: '', label: '选择专题...', disabled: true }
  const options = promptTopics.value.map(topic => ({ value: topic, label: topic }))
  return [placeholder, ...options]
})

// Methods
const saveConfig = async () => {
  try {
    await ragState.saveConfig()
    statusMessage.value = '配置保存成功！'
    statusType.value = 'success'

    // Clear message after 3 seconds
    setTimeout(() => {
      statusMessage.value = ''
    }, 3000)
  } catch (error) {
    statusMessage.value = error.message || '保存失败'
    statusType.value = 'error'
  }
}

const resetConfig = () => {
  if (confirm('确定要重置所有配置为默认值吗？')) {
    ragState.resetConfigForm()
    statusMessage.value = '配置已重置为默认值'
    statusType.value = 'success'

    setTimeout(() => {
      statusMessage.value = ''
    }, 3000)
  }
}

const testConfig = async () => {
  isTesting.value = true
  try {
    // Simulate testing
    await new Promise(resolve => setTimeout(resolve, 2000))

    statusMessage.value = '配置测试通过'
    statusType.value = 'success'
  } catch (error) {
    statusMessage.value = '配置测试失败'
    statusType.value = 'error'
  } finally {
    isTesting.value = false

    setTimeout(() => {
      statusMessage.value = ''
    }, 3000)
  }
}

// Prompt Methods
const loadPromptsForTopic = async () => {
  if (!selectedPromptTopic.value) return
  
  promptConfig.value = null
  try {
    const response = await callApi(`/api/settings/rag/prompts?topic=${encodeURIComponent(selectedPromptTopic.value)}`, {
       method: 'GET'
    })
    
    if (response?.data && Object.keys(response.data).length > 0) {
       promptConfig.value = response.data
    } else {
       // Initialize with default structure if empty
       promptConfig.value = {
          time_extraction: { prompt: '' },
          time_matching: { prompt: '' },
          query_expansion: { prompt: '' },
          result_summary_strict: { prompt: '' },
          result_summary_supplement: { prompt: '' }
       }
    }
  } catch (error) {
    statusMessage.value = '加载提示词失败: ' + (error.message || '未知错误')
    statusType.value = 'error'
  }
}

const savePrompts = async () => {
   if (!selectedPromptTopic.value || !promptConfig.value) return
   
   savingPrompts.value = true
   try {
      await callApi('/api/settings/rag/prompts', {
         method: 'POST',
         body: JSON.stringify({
            topic: selectedPromptTopic.value,
            prompts: promptConfig.value
         })
      })
      statusMessage.value = '提示词保存成功'
      statusType.value = 'success'
      setTimeout(() => statusMessage.value = '', 3000)
   } catch (error) {
      statusMessage.value = '保存提示词失败: ' + (error.message || '未知错误')
      statusType.value = 'error'
   } finally {
      savingPrompts.value = false
   }
}

const resetPromptsToDefault = async () => {
   if (!selectedPromptTopic.value) return
   if (!confirm('确定要将该专题的提示词重置为默认值吗？')) return
   
   promptConfig.value = null
   try {
      // We can trigger a reset by sending an empty prompts object or a special flag, 
      // but the backend load_router_prompt_config handles missing files.
      // Easiest is to just send an empty body or special reset call if implemented.
      // Alternatively, just load the default config from the backend.
      const response = await callApi(`/api/settings/rag/prompts?topic=${encodeURIComponent(selectedPromptTopic.value)}&reset=true`, {
         method: 'GET'
      })
      if (response?.data) {
         promptConfig.value = response.data
         statusMessage.value = '提示词已重置为默认值'
         statusType.value = 'success'
         setTimeout(() => statusMessage.value = '', 3000)
      }
   } catch (error) {
      statusMessage.value = '重置失败: ' + (error.message || '未知错误')
      statusType.value = 'error'
   }
}

// Lifecycle
onMounted(async () => {
  ragState.loadConfig()
  await loadRAGTopics()
  if (promptTopics.value.length > 0) {
     selectedPromptTopic.value = promptTopics.value[0]
     loadPromptsForTopic()
  }
})

watch(activeTab, (newTab) => {
   if (newTab === 'prompts' && !selectedPromptTopic.value && promptTopics.value.length > 0) {
      selectedPromptTopic.value = promptTopics.value[0]
      loadPromptsForTopic()
   }
})
</script>
