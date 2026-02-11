<template>
  <div class="space-y-10">
    <section class="card-surface">
      <div class="border-b px-6 py-4">
        <h2 class="text-lg font-semibold text-primary">BERTopic 全局配置</h2>
        <p class="text-sm text-secondary mt-1">配置 BERTopic 主题分析使用的嵌入模型和运行参数。</p>
      </div>

      <div class="p-6">
        <div v-if="configState.error" class="mb-6 rounded-xl border border-red-200 bg-red-50/70 p-4 text-sm text-red-700">
          {{ configState.error }}
        </div>

        <div
          v-if="statusMessage"
          :class="[
            'mb-6 rounded-lg p-4 text-sm',
            statusType === 'success' ? 'bg-green-50 text-green-800' : 'bg-red-50 text-red-800'
          ]"
        >
          {{ statusMessage }}
        </div>

        <div v-if="configState.loading && !configForm.embedding.model_name" class="py-8 text-center text-gray-500">
          加载中...
        </div>

        <div v-else class="space-y-6">
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
                常用模型列表由后端接口提供，失败时自动回退到内置推荐列表。
              </p>
              <p v-if="embeddingModelState.loading" class="text-xs text-muted">正在刷新模型列表...</p>
              <p v-else-if="embeddingModelState.error" class="text-xs text-amber-700">
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
      </div>

      <div class="border-t bg-gray-50 px-6 py-4">
        <div class="flex justify-between">
          <button @click="resetConfig" class="btn-secondary">重置为默认</button>
          <button @click="saveConfig" :disabled="!canSave" class="btn-primary">
            <span v-if="configState.loading">保存中...</span>
            <span v-else>保存配置</span>
          </button>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useBertopicConfig } from '../../composables/useBertopicConfig'

const CUSTOM_MODEL_OPTION = '__custom_model__'

const {
  configForm,
  configState,
  embeddingModelState,
  embeddingModelOptions,
  loadConfig,
  loadEmbeddingModels,
  saveConfig: saveApi,
  resetConfigForm
} = useBertopicConfig()

const statusMessage = ref('')
const statusType = ref('success')
const selectedModelOption = ref(CUSTOM_MODEL_OPTION)

const normalizedModelName = computed(() => String(configForm.embedding.model_name || '').trim())
const isCustomModelSelected = computed(() => selectedModelOption.value === CUSTOM_MODEL_OPTION)
const canSave = computed(() => !configState.loading && normalizedModelName.value.length > 0)

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
  await Promise.allSettled([loadConfig(), loadEmbeddingModels()])
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
</script>
