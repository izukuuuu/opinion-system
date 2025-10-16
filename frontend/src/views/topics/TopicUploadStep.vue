<template>
  <div class="space-y-8">
    <header class="flex flex-wrap items-center justify-between gap-3">
      <div class="space-y-1">
        <h1 class="text-2xl font-semibold text-primary">上传原始数据</h1>
        <p class="text-sm text-secondary">创建专题并上传 Excel/CSV 文件，生成标准化存档。</p>
      </div>
      <div class="flex items-center gap-2 rounded-full bg-brand-soft px-3 py-1 text-xs font-semibold text-brand-600">
        <CloudArrowUpIcon class="h-4 w-4" />
        <span>步骤 1 · 上传</span>
      </div>
    </header>

    <section class="card-surface space-y-6 p-6">
      <header class="space-y-2">
        <h2 class="text-xl font-semibold text-primary">创建专题</h2>
        <p class="text-sm text-secondary">填写专题名称后创建记录，系统将用于跟踪后续流程。</p>
      </header>
      <form class="grid gap-4 sm:grid-cols-[minmax(0,320px)] lg:grid-cols-[minmax(0,400px),1fr]" @submit.prevent="createTopic">
        <div class="space-y-4">
          <label class="space-y-1 text-sm">
            <span class="font-medium text-secondary">专题名称</span>
            <input
              v-model.trim="topicName"
              type="text"
              required
              class="w-full rounded-2xl border border-soft px-4 py-2 text-sm shadow-sm transition focus:border-brand-soft focus:outline-none focus:ring-2 focus:ring-brand-200"
              placeholder="例如：2024-两会舆情"
            />
          </label>
          <label class="space-y-1 text-sm">
            <span class="font-medium text-secondary">专题说明（可选）</span>
            <textarea
              v-model.trim="topicDescription"
              rows="3"
              class="w-full rounded-2xl border border-soft px-4 py-2 text-sm shadow-sm transition focus:border-brand-soft focus:outline-none focus:ring-2 focus:ring-brand-200"
              placeholder="补充专题背景、抓取渠道等信息。"
            ></textarea>
          </label>
          <button
            type="submit"
            class="inline-flex w-full items-center justify-center gap-2 rounded-full bg-brand-600 px-5 py-2 text-sm font-semibold text-white shadow transition hover:bg-brand-500 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-600 disabled:cursor-not-allowed disabled:bg-brand-300 disabled:text-white/70"
            :disabled="creating || !topicName"
          >
            <span v-if="creating">创建中…</span>
            <span v-else>创建专题</span>
          </button>
        </div>
        <div class="rounded-3xl border border-dashed border-brand-soft bg-surface-muted p-4 text-sm text-secondary">
          <h3 class="text-sm font-semibold text-primary">提示</h3>
          <ul class="mt-2 space-y-2 text-xs leading-relaxed text-secondary">
            <li>专题名称将作为后续 API 调用的参数，建议使用字母、数字与短横线组合。</li>
            <li>可先创建专题再上传数据，也可直接上传，系统会在需要时自动创建专题。</li>
            <li>描述信息用于团队协作记录，可随时在设置中更新。</li>
          </ul>
        </div>
      </form>
      <p v-if="createError" class="rounded-2xl bg-rose-100 px-4 py-2 text-sm text-rose-600">{{ createError }}</p>
      <p v-if="createSuccess" class="rounded-2xl bg-emerald-100 px-4 py-2 text-sm text-emerald-600">{{ createSuccess }}</p>
    </section>

    <section class="card-surface space-y-6 p-6">
      <header class="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 class="text-xl font-semibold text-primary">上传原始表格</h2>
          <p class="text-sm text-secondary">
            支持 .xlsx、.xls、.csv、.jsonl 文件。系统会自动生成 JSONL、PKL 与 Meta 清单。
          </p>
        </div>
        <span v-if="topicName" class="badge-soft rounded-full px-3 py-1 text-xs font-semibold text-secondary">
          当前专题：{{ topicName }}
        </span>
      </header>

      <form class="space-y-5" @submit.prevent="uploadDataset">
        <div
          class="flex min-h-[200px] cursor-pointer flex-col items-center justify-center gap-2 rounded-3xl border-2 border-dashed border-brand-soft bg-surface-muted px-6 text-center text-sm text-secondary transition hover:border-brand hover:bg-brand-soft hover:text-brand-600"
          :class="{ 'border-brand bg-surface text-brand-600 shadow-inner': uploadFile }"
        >
          <input
            ref="fileInput"
            type="file"
            class="hidden"
            accept=".xlsx,.xls,.csv,.jsonl"
            @change="handleFileChange"
          />
          <button type="button" class="flex flex-col items-center gap-2 text-sm" @click="fileInput?.click()">
            <DocumentArrowUpIcon class="h-10 w-10 text-slate-300" />
            <span class="font-medium">
              {{ uploadFile ? uploadFile.name : '点击或拖拽文件到此处' }}
            </span>
            <span class="text-xs text-slate-400">最大支持 50MB</span>
          </button>
        </div>
        <div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <button type="submit" class="inline-flex items-center justify-center rounded-full bg-brand-600 px-6 py-2 text-sm font-semibold text-white shadow transition hover:bg-brand-500 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-600 disabled:cursor-not-allowed disabled:bg-brand-300 disabled:text-white/70" :disabled="uploading">
            {{ uploading ? '上传中…' : '上传并生成存档' }}
          </button>
          <div class="space-y-1 text-sm">
            <p v-if="uploadHelper && !uploadError && !uploadSuccess" class="text-secondary">
              {{ uploadHelper }}
            </p>
            <p v-if="uploadError" class="text-rose-600">{{ uploadError }}</p>
            <p v-if="uploadSuccess" class="text-emerald-600">{{ uploadSuccess }}</p>
          </div>
        </div>
      </form>
    </section>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { CloudArrowUpIcon, DocumentArrowUpIcon } from '@heroicons/vue/24/outline'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api'

const topicName = ref('')
const topicDescription = ref('')

const creating = ref(false)
const createError = ref('')
const createSuccess = ref('')

const fileInput = ref(null)
const uploadFile = ref(null)
const uploading = ref(false)
const uploadError = ref('')
const uploadSuccess = ref('')

const uploadHelper = computed(() => {
  if (uploading.value) return ''
  if (!topicName.value) return '请先填写专题名称'
  if (!uploadFile.value) return '请选择需要上传的文件'
  return ''
})

const createTopic = async () => {
  if (!topicName.value) return
  creating.value = true
  createError.value = ''
  createSuccess.value = ''

  try {
    const response = await fetch(`${API_BASE_URL}/projects`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        name: topicName.value,
        description: topicDescription.value || undefined
      })
    })

    const result = await response.json()
    if (!response.ok || result.status !== 'ok') {
      throw new Error(result.message || '专题创建失败')
    }
    createSuccess.value = '专题创建成功，可以继续上传数据。'
  } catch (err) {
    createError.value = err instanceof Error ? err.message : '专题创建失败'
  } finally {
    creating.value = false
  }
}

const handleFileChange = (event) => {
  const [file] = event.target.files || []
  uploadFile.value = file || null
  uploadError.value = ''
  uploadSuccess.value = ''
}

const uploadDataset = async () => {
  if (!topicName.value) {
    uploadError.value = '请填写专题名称后再上传'
    return
  }
  if (!uploadFile.value) {
    uploadError.value = '请选择需要上传的文件'
    return
  }

  uploading.value = true
  uploadError.value = ''
  uploadSuccess.value = ''

  const formData = new FormData()
  formData.append('file', uploadFile.value)

  try {
    const response = await fetch(`${API_BASE_URL}/projects/${encodeURIComponent(topicName.value)}/datasets`, {
      method: 'POST',
      body: formData
    })
    const result = await response.json()
    if (!response.ok || result.status !== 'ok') {
      throw new Error(result.message || '上传失败')
    }
    uploadSuccess.value = '上传成功，已生成 JSONL 与 PKL 存档。'
    uploadFile.value = null
    if (fileInput.value) {
      fileInput.value.value = ''
    }
  } catch (err) {
    uploadError.value = err instanceof Error ? err.message : '上传失败'
  } finally {
    uploading.value = false
  }
}
</script>
