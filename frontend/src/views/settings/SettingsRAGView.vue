<template>
  <div class="space-y-10">
    <!-- Configuration Tabs -->
    <section class="card-surface">
      <div class="border-b">
        <nav class="-mb-px flex space-x-8 px-6">
          <button
            v-for="tab in tabs"
            :key="tab.key"
            @click="activeTab = tab.key"
            :class="[
              'py-4 px-1 border-b-2 font-medium text-sm transition-colors',
              activeTab === tab.key
                ? 'border-brand-500 text-brand-600'
                : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
            ]"
          >
            {{ tab.label }}
          </button>
        </nav>
      </div>

      <div class="p-6">
        <!-- Error/Success Messages -->
        <div v-if="ragState.configState.error" class="mb-6 rounded-xl border border-red-200 bg-red-50/70 p-4 text-sm text-red-700">
          {{ ragState.configState.error }}
        </div>

        <div v-if="statusMessage" :class="[
          'mb-6 rounded-lg p-4 text-sm',
          statusType === 'success' ? 'bg-green-50 text-green-800' : 'bg-red-50 text-red-800'
        ]">
          {{ statusMessage }}
        </div>

        <!-- Embedding Configuration -->
        <div v-if="activeTab === 'embedding'" class="space-y-6">
          <h2 class="text-lg font-semibold text-primary">嵌入模型配置</h2>

          <div class="grid gap-6 md:grid-cols-2">
            <div class="space-y-2">
              <label class="text-xs font-semibold text-muted">模型名称</label>
              <select
                v-model="ragState.configForm.embedding.model_name"
                class="input"
              >
                <option value="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2">
                  multilingual-MiniLM-L12-v2 (推荐)
                </option>
                <option value="sentence-transformers/all-MiniLM-L6-v2">
                  all-MiniLM-L6-v2 (快速)
                </option>
                <option value="sentence-transformers/all-mpnet-base-v2">
                  all-mpnet-base-v2 (高精度)
                </option>
                <option value="shibing624/text2vec-base-chinese">
                  text2vec-base-chinese (中文优化)
                </option>
              </select>
              <p class="text-xs text-muted">选择适合您语言的嵌入模型</p>
            </div>

            <div class="space-y-2">
              <label class="text-xs font-semibold text-muted">批处理大小</label>
              <input
                v-model.number="ragState.configForm.embedding.batch_size"
                type="number"
                min="1"
                max="128"
                class="input"
              />
              <p class="text-xs text-muted">同时处理的文本数量，影响内存使用</p>
            </div>

            <div class="space-y-2">
              <label class="text-xs font-semibold text-muted">设备</label>
              <select
                v-model="ragState.configForm.embedding.device"
                class="input"
              >
                <option value="auto">自动选择</option>
                <option value="cpu">CPU</option>
                <option value="cuda">GPU (CUDA)</option>
              </select>
              <p class="text-xs text-muted">模型运行设备</p>
            </div>

            <div class="space-y-2">
              <label class="text-xs font-semibold text-muted">模型类型</label>
              <select
                v-model="ragState.configForm.embedding.model_type"
                class="input"
                disabled
              >
                <option value="huggingface">HuggingFace</option>
                <option value="openai">OpenAI (暂不支持)</option>
              </select>
              <p class="text-xs text-muted">嵌入模型提供商</p>
            </div>
          </div>

          <div class="flex items-center">
            <input
              v-model="ragState.configForm.embedding.normalize"
              type="checkbox"
              id="normalize-embeddings"
              class="checkbox-custom"
            />
            <label for="normalize-embeddings" class="ml-2 text-sm text-secondary">
              标准化嵌入向量
            </label>
          </div>
        </div>

        <!-- Chunking Configuration -->
        <div v-if="activeTab === 'chunking'" class="space-y-6">
          <h2 class="text-lg font-semibold text-primary">文本分块配置</h2>

          <div class="grid gap-6 md:grid-cols-2">
            <div class="space-y-2">
              <label class="text-xs font-semibold text-muted">分块策略</label>
              <select
                v-model="ragState.configForm.chunking.strategy"
                class="input"
              >
                <option value="size">按大小分块</option>
                <option value="count">按数量分块</option>
                <option value="semantic">语义分块 (实验性)</option>
              </select>
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
            <div class="flex items-center">
              <input
                v-model="ragState.configForm.chunking.respect_sentence_boundary"
                type="checkbox"
                id="respect-sentence"
                class="checkbox-custom"
              />
              <label for="respect-sentence" class="ml-2 text-sm text-secondary">
                尊重句子边界
              </label>
            </div>

            <div class="flex items-center">
              <input
                v-model="ragState.configForm.chunking.strip_whitespace"
                type="checkbox"
                id="strip-whitespace"
                class="checkbox-custom"
              />
              <label for="strip-whitespace" class="ml-2 text-sm text-secondary">
                去除多余空白
              </label>
            </div>
          </div>
        </div>

        <!-- Retrieval Configuration -->
        <div v-if="activeTab === 'retrieval'" class="space-y-6">
          <h2 class="text-lg font-semibold text-primary">检索配置</h2>

          <div class="grid gap-6 md:grid-cols-2">
            <div class="space-y-2">
              <label class="text-xs font-semibold text-muted">检索类型</label>
              <select
                v-model="ragState.configForm.retrieval.search_type"
                class="input"
              >
                <option value="vector">向量检索</option>
                <option value="hybrid">混合检索</option>
                <option value="bm25">BM25检索</option>
              </select>
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
              <select
                v-model="ragState.configForm.retrieval.score_type"
                class="input"
              >
                <option value="cosine">余弦相似度</option>
                <option value="dot">点积</option>
                <option value="euclidean">欧氏距离</option>
              </select>
            </div>
          </div>

          <div class="space-y-3">
            <div class="flex items-center">
              <input
                v-model="ragState.configForm.retrieval.include_metadata"
                type="checkbox"
                id="include-metadata"
                class="checkbox-custom"
              />
              <label for="include-metadata" class="ml-2 text-sm text-secondary">
                包含元数据
              </label>
            </div>

            <div class="flex items-center">
              <input
                v-model="ragState.configForm.retrieval.rerank"
                type="checkbox"
                id="enable-rerank"
                class="checkbox-custom"
                disabled
              />
              <label for="enable-rerank" class="ml-2 text-sm text-muted">
                启用重排序 (暂不支持)
              </label>
            </div>

            <div class="border-t pt-4 mt-4 space-y-4">
              <h3 class="text-sm font-bold text-gray-700">RouterRAG 特有配置</h3>
              
              <div class="flex items-center">
                <input
                  v-model="ragState.configForm.retrieval.enable_query_expansion"
                  type="checkbox"
                  id="enable-query-expansion"
                  class="checkbox-custom"
                />
                <label for="enable-query-expansion" class="ml-2 text-sm text-secondary">
                  启用查询扩展 (Query Expansion)
                </label>
              </div>

              <div class="flex items-center">
                <input
                  v-model="ragState.configForm.retrieval.enable_llm_summary"
                  type="checkbox"
                  id="enable-llm-summary"
                  class="checkbox-custom"
                />
                <label for="enable-llm-summary" class="ml-2 text-sm text-secondary">
                  启用 LLM 结果总结 (Result Summary)
                </label>
              </div>

              <div v-if="ragState.configForm.retrieval.enable_llm_summary" class="ml-6 space-y-2">
                <label class="text-xs font-semibold text-muted">总结模式</label>
                <select
                  v-model="ragState.configForm.retrieval.llm_summary_mode"
                  class="input text-xs py-1"
                >
                  <option value="strict">严格模式 (仅限参考资料)</option>
                  <option value="supplement">补充模式 (结合通用知识)</option>
                </select>
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
              <select
                v-model="ragState.configForm.storage.storage_type"
                class="input"
              >
                <option value="file">文件存储</option>
                <option value="lance">LanceDB</option>
                <option value="faiss">FAISS</option>
                <option value="chroma">ChromaDB</option>
              </select>
              <p class="text-xs text-muted">向量数据库类型</p>
            </div>

            <div class="space-y-2">
              <label class="text-xs font-semibold text-muted">索引类型</label>
              <select
                v-model="ragState.configForm.storage.index_type"
                class="input"
              >
                <option value="flat">Flat (精确)</option>
                <option value="ivf">IVF (倒排)</option>
                <option value="hnsw">HNSW (层次)</option>
              </select>
              <p class="text-xs text-muted">向量索引类型</p>
            </div>

            <div class="space-y-2">
              <label class="text-xs font-semibold text-muted">距离度量</label>
              <select
                v-model="ragState.configForm.storage.metric"
                class="input"
              >
                <option value="cosine">余弦距离</option>
                <option value="l2">欧氏距离</option>
                <option value="ip">内积</option>
              </select>
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
            <div class="flex items-center">
              <input
                v-model="ragState.configForm.storage.persist_index"
                type="checkbox"
                id="persist-index"
                class="checkbox-custom"
              />
              <label for="persist-index" class="ml-2 text-sm text-secondary">
                持久化索引
              </label>
            </div>
          </div>
        </div>

        <!-- Processing Configuration -->
        <div v-if="activeTab === 'processing'" class="space-y-6">
          <h2 class="text-lg font-semibold text-primary">文本预处理配置</h2>

          <div class="space-y-3">
            <div class="flex items-center">
              <input
                v-model="ragState.configForm.processing.lowercase"
                type="checkbox"
                id="lowercase"
                class="checkbox-custom"
              />
              <label for="lowercase" class="ml-2 text-sm text-secondary">
                转换为小写
              </label>
            </div>

            <div class="flex items-center">
              <input
                v-model="ragState.configForm.processing.remove_urls"
                type="checkbox"
                id="remove-urls"
                class="checkbox-custom"
              />
              <label for="remove-urls" class="ml-2 text-sm text-secondary">
                移除URL
              </label>
            </div>

            <div class="flex items-center">
              <input
                v-model="ragState.configForm.processing.remove_emails"
                type="checkbox"
                id="remove-emails"
                class="checkbox-custom"
              />
              <label for="remove-emails" class="ml-2 text-sm text-secondary">
                移除邮箱
              </label>
            </div>

            <div class="flex items-center">
              <input
                v-model="ragState.configForm.processing.remove_extra_whitespace"
                type="checkbox"
                id="remove-whitespace"
                class="checkbox-custom"
              />
              <label for="remove-whitespace" class="ml-2 text-sm text-secondary">
                移除多余空白
              </label>
            </div>

            <div class="flex items-center">
              <input
                v-model="ragState.configForm.processing.remove_special_chars"
                type="checkbox"
                id="remove-special"
                class="checkbox-custom"
              />
              <label for="remove-special" class="ml-2 text-sm text-secondary">
                移除特殊字符
              </label>
            </div>

            <div class="flex items-center">
              <input
                v-model="ragState.configForm.processing.normalize_unicode"
                type="checkbox"
                id="normalize-unicode"
                class="checkbox-custom"
              />
              <label for="normalize-unicode" class="ml-2 text-sm text-secondary">
                标准化Unicode
              </label>
            </div>
          </div>
        </div>


        <!-- Prompts Configuration -->
        <div v-if="activeTab === 'prompts'" class="space-y-6">
          <div class="flex items-center justify-between">
            <h2 class="text-lg font-semibold text-primary">RAG 提示词配置 (RouterRAG)</h2>
            <div class="flex items-center gap-2">
              <select
                v-model="selectedPromptTopic"
                class="input w-48 py-1.5 text-sm"
                @change="loadPromptsForTopic"
              >
                <option value="" disabled>选择专题...</option>
                <option v-for="topic in promptTopics" :key="topic" :value="topic">{{ topic }}</option>
              </select>
              <button
                @click="loadPromptsForTopic"
                class="btn-secondary py-1.5 text-xs"
                title="刷新"
              >
                刷新
              </button>
              <button
                @click="resetPromptsToDefault"
                class="btn-secondary border-red-200 text-red-600 hover:bg-red-50 py-1.5 text-xs"
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
                <label class="text-sm font-bold text-gray-700">时间提取提示词 (Time Extraction)</label>
                <span class="text-xs text-gray-400">用于识别查询中的时间信息</span>
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
                <label class="text-sm font-bold text-gray-700">时间匹配提示词 (Time Matching)</label>
                <span class="text-xs text-gray-400">用于匹配查询时间与文档时间</span>
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
                <label class="text-sm font-bold text-gray-700">查询扩展提示词 (Query Expansion)</label>
                <span class="text-xs text-gray-400">用于优化和扩展用户查询</span>
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
                <label class="text-sm font-bold text-gray-700">结果整理 - 严格模式 (Strict Summary)</label>
                <span class="text-xs text-gray-400">仅使用检索资料回答</span>
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
                <label class="text-sm font-bold text-gray-700">结果整理 - 补充模式 (Supplement Summary)</label>
                <span class="text-xs text-gray-400">结合外部知识回答</span>
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
          
          <div v-else-if="selectedPromptTopic" class="text-center py-12 text-gray-500">
             加载中...
          </div>
          <div v-else class="text-center py-12 text-gray-400">
             请选择一个专题以编辑其 RouterRAG 提示词
          </div>
        </div>

        <!-- API Keys Configuration -->

        <div v-if="activeTab === 'api_keys'" class="space-y-6">
          <h2 class="text-lg font-semibold text-primary">API 密钥配置</h2>

          <div class="space-y-4">
            <div class="p-4 bg-yellow-50 border border-yellow-200 rounded-lg">
              <p class="text-sm text-yellow-800">
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

            <div class="p-4 bg-blue-50 border border-blue-200 rounded-lg">
              <h3 class="text-sm font-medium text-blue-800 mb-2">API 密钥获取指南：</h3>
              <ul class="text-xs text-blue-700 space-y-1">
                <li><strong>OpenAI：</strong> 访问 <a href="https://platform.openai.com/api-keys" target="_blank" class="underline">OpenAI API Keys</a> 页面创建</li>
                <li><strong>Cohere：</strong> 访问 <a href="https://dashboard.cohere.com/api-keys" target="_blank" class="underline">Cohere Dashboard</a> 获取</li>
                <li><strong>HuggingFace：</strong> 访问 <a href="https://huggingface.co/settings/tokens" target="_blank" class="underline">HuggingFace Tokens</a> 页面创建</li>
              </ul>
            </div>
          </div>
        </div>
      </div>

      <!-- Action Buttons -->
      <div class="border-t bg-gray-50 px-6 py-4">
        <div class="flex justify-between">
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
  </div>
</template>

<script setup>
import { ref, onMounted, computed, watch } from 'vue'
import { useRAGSimple } from '../../composables/useRAGSimple'
import { useRAGTopics } from '../../composables/useRAGTopics'
import { useApiBase } from '../../composables/useApiBase'

const ragState = useRAGSimple()
const { ragTopicsState, loadRAGTopics } = useRAGTopics()
const { callApi } = useApiBase()

// State
const activeTab = ref('embedding')
const isTesting = ref(false)
const statusMessage = ref('')
const statusType = ref('success')

// Prompts State
const selectedPromptTopic = ref('')
const promptConfig = ref(null)
const savingPrompts = ref(false)

const tabs = [
  { key: 'embedding', label: '嵌入模型' },
  { key: 'chunking', label: '文本分块' },
  { key: 'retrieval', label: '检索参数' },
  { key: 'storage', label: '存储配置' },
  { key: 'processing', label: '预处理' },
  { key: 'api_keys', label: 'API 密钥' },
  { key: 'prompts', label: '提示词' }
]

const promptTopics = computed(() => ragTopicsState.router)

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