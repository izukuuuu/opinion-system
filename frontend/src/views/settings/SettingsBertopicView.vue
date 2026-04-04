<template>
  <section class="card-surface space-y-6 p-6">
      <header class="settings-page-header">
        <p class="settings-page-eyebrow">BERTopic</p>
        <h2 class="settings-page-title">BERTopic 配置</h2>
        <p class="settings-page-desc">配置主题分析使用的嵌入模型和停用词。</p>
      </header>

      <div class="settings-toolbar settings-section-split">
        <div class="settings-section-header">
          <h3 class="settings-section-title">配置项</h3>
          <p class="settings-section-desc">在嵌入配置和停用词之间切换。</p>
        </div>
        <div class="settings-tabbar">
          <button
            type="button"
            class="settings-tab"
            :class="activeTab === 'embedding' ? 'settings-tab-active' : ''"
            @click="activeTab = 'embedding'"
          >
            嵌入配置
          </button>
          <button
            type="button"
            class="settings-tab"
            :class="activeTab === 'stopwords' ? 'settings-tab-active' : ''"
            @click="activeTab = 'stopwords'"
          >
            停用词
          </button>
        </div>
      </div>

      <div>
        <div v-if="configState.error" class="settings-message-error mb-6">
          {{ configState.error }}
        </div>

        <div
          v-if="statusMessage"
          :class="[
            'mb-6',
            statusType === 'success' ? 'settings-message-success' : 'settings-message-error'
          ]"
        >
          {{ statusMessage }}
        </div>

        <div v-if="configState.loading && !configForm.embedding.model_name" class="settings-empty-state py-8">
          加载中...
        </div>

        <div v-else class="space-y-6">
          <div v-if="activeTab === 'embedding'" class="space-y-6">
            <div class="settings-help-block border-brand-soft bg-brand-soft text-primary">
              <p class="font-semibold">当前建议</p>
              <p class="mt-1 leading-6">
                对 8GB 级别 GPU，默认推荐 `moka-ai/m3e-base + auto + batch_size=32`。
                如果切到 `BAAI/bge-large-zh-v1.5`，建议先把批大小降到 `8` 或更低。
              </p>
            </div>

            <div class="grid gap-6 md:grid-cols-2">
              <div class="space-y-2 md:col-span-2">
                <label class="text-xs font-semibold text-muted">嵌入模型 (Embedding Model)</label>
                <select v-model="selectedModelOption" class="input">
                  <option v-for="option in embeddingModelOptions" :key="option.value" :value="option.value">
                    {{ option.label }}
                  </option>
                  <option :value="CUSTOM_MODEL_OPTION">自定义模型 (手动输入)</option>
                </select>
                <p class="text-xs text-muted">
                  常用模型列表由后端接口提供，失败时自动回退到内置推荐列表。BERTopic 实际运行会读取这里保存的全局配置。
                </p>
                <p v-if="embeddingModelState.loading" class="text-xs text-muted">正在刷新模型列表...</p>
                <p v-else-if="embeddingModelState.error" class="text-xs text-warning">
                  模型列表加载失败，已使用内置列表：{{ embeddingModelState.error }}
                </p>
              </div>

              <div v-if="isCustomModelSelected" class="space-y-2 md:col-span-2">
                <label class="text-xs font-semibold text-muted">自定义模型名称</label>
                <input
                  v-model.trim="configForm.embedding.model_name"
                  type="text"
                  class="input"
                  placeholder="例如 sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
                />
                <p class="text-xs text-muted">填写 HuggingFace 模型名，运行时将自动下载并加载。</p>
              </div>

              <div class="space-y-2">
                <label class="text-xs font-semibold text-muted">运行设备 (Device)</label>
                <select v-model="configForm.embedding.device" class="input">
                  <option value="cpu">CPU (通用)</option>
                  <option value="cuda">GPU (CUDA)</option>
                  <option value="auto">自动选择</option>
                </select>
                <p class="text-xs text-muted">指定模型运行的硬件设备。</p>
              </div>

              <div class="space-y-2">
                <label class="text-xs font-semibold text-muted">批处理大小 (Batch Size)</label>
                <input
                  v-model.number="configForm.embedding.batch_size"
                  type="number"
                  min="1"
                  max="256"
                  class="input"
                />
                <p class="text-xs text-muted">仅在某些嵌入流程中生效。</p>
              </div>
            </div>
          </div>

          <div v-else class="space-y-5">
            <div class="settings-message-warning">
              <p class="font-semibold">编辑说明</p>
              <p class="mt-1 leading-6">
                一行一个停用词，保存后会直接写入 `configs/stopwords.txt`，后续 BERTopic 分词会读取这份文件。
              </p>
            </div>

            <div class="flex flex-wrap items-center gap-4 text-xs text-secondary">
              <span>文件路径：{{ stopwordsForm.path || 'configs/stopwords.txt' }}</span>
              <span>当前行数：{{ currentStopwordCount }}</span>
            </div>

            <div v-if="stopwordsState.error" class="settings-message-error">
              {{ stopwordsState.error }}
            </div>

            <textarea
              v-model="stopwordsForm.content"
              rows="22"
              class="input min-h-[520px] w-full resize-y font-mono text-sm leading-6"
              placeholder="一行一个停用词"
            />
          </div>
        </div>
      </div>

      <div class="settings-action-row">
        <div class="flex w-full flex-wrap items-center justify-between gap-3">
          <template v-if="activeTab === 'embedding'">
            <button @click="resetConfig" class="btn-secondary">重置为默认</button>
            <button @click="saveConfig" :disabled="!canSave" class="btn-primary">
              <span v-if="configState.loading">保存中...</span>
              <span v-else>保存配置</span>
            </button>
          </template>
          <template v-else>
            <button @click="reloadStopwords" class="btn-secondary" :disabled="stopwordsState.loading || stopwordsState.saving">
              重新加载
            </button>
            <button @click="saveStopwords" :disabled="stopwordsState.loading || stopwordsState.saving" class="btn-primary">
              <span v-if="stopwordsState.saving">保存中...</span>
              <span v-else>保存停用词</span>
            </button>
          </template>
        </div>
      </div>
  </section>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useBertopicConfig } from '../../composables/useBertopicConfig'

const CUSTOM_MODEL_OPTION = '__custom_model__'

const {
  configForm,
  configState,
  stopwordsForm,
  stopwordsState,
  embeddingModelState,
  embeddingModelOptions,
  loadConfig,
  loadStopwords,
  loadEmbeddingModels,
  saveConfig: saveApi,
  saveStopwords: saveStopwordsApi,
  resetConfigForm
} = useBertopicConfig()

const statusMessage = ref('')
const statusType = ref('success')
const selectedModelOption = ref(CUSTOM_MODEL_OPTION)
const activeTab = ref('embedding')

const normalizedModelName = computed(() => String(configForm.embedding.model_name || '').trim())
const isCustomModelSelected = computed(() => selectedModelOption.value === CUSTOM_MODEL_OPTION)
const canSave = computed(() => !configState.loading && normalizedModelName.value.length > 0)
const currentStopwordCount = computed(() =>
  String(stopwordsForm.content || '')
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
    .length
)

const syncSelectedModel = () => {
  const modelName = normalizedModelName.value
  if (!modelName) {
    selectedModelOption.value = CUSTOM_MODEL_OPTION
    return
  }

  selectedModelOption.value = embeddingModelOptions.value.some((option) => option.value === modelName)
    ? modelName
    : CUSTOM_MODEL_OPTION
}

watch([() => configForm.embedding.model_name, () => embeddingModelOptions.value], syncSelectedModel, { immediate: true })

watch(selectedModelOption, (value) => {
  if (value && value !== CUSTOM_MODEL_OPTION) {
    configForm.embedding.model_name = value
  }
})

onMounted(async () => {
  await Promise.allSettled([loadConfig(), loadEmbeddingModels(), loadStopwords()])
  syncSelectedModel()
})

const saveConfig = async () => {
  if (!normalizedModelName.value) {
    statusMessage.value = '请先填写嵌入模型名称'
    statusType.value = 'error'
    return
  }

  try {
    await saveApi()
    statusMessage.value = 'BERTopic 配置保存成功'
    statusType.value = 'success'
    setTimeout(() => {
      statusMessage.value = ''
    }, 3000)
  } catch (error) {
    statusMessage.value = error instanceof Error ? error.message : '保存失败'
    statusType.value = 'error'
  }
}

const resetConfig = () => {
  if (!confirm('确定要重置配置吗？')) return
  resetConfigForm()
  syncSelectedModel()
  statusMessage.value = '已重置为默认值，请点击“保存配置”生效。'
  statusType.value = 'success'
}

const saveStopwords = async () => {
  try {
    await saveStopwordsApi()
    statusMessage.value = '停用词保存成功'
    statusType.value = 'success'
    setTimeout(() => {
      statusMessage.value = ''
    }, 3000)
  } catch (error) {
    statusMessage.value = error instanceof Error ? error.message : '停用词保存失败'
    statusType.value = 'error'
  }
}

const reloadStopwords = async () => {
  try {
    await loadStopwords()
    statusMessage.value = '已重新加载停用词文件'
    statusType.value = 'success'
    setTimeout(() => {
      statusMessage.value = ''
    }, 3000)
  } catch (error) {
    statusMessage.value = error instanceof Error ? error.message : '重新加载停用词失败'
    statusType.value = 'error'
  }
}
</script>
