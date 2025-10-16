<template>
  <div class="grid gap-8 xl:grid-cols-[320px,minmax(0,1fr)]">
    <aside class="card-surface flex flex-col gap-6 p-6">
      <div class="flex items-center justify-between gap-3">
        <div>
          <h2 class="text-lg font-semibold text-slate-900">项目列表</h2>
          <p class="text-sm text-slate-500">选择项目以查看上传的数据集。</p>
        </div>
        <button
          type="button"
          class="inline-flex items-center gap-2 rounded-full border border-slate-200 px-3 py-1.5 text-sm font-medium text-slate-600 transition hover:border-indigo-200 hover:text-indigo-600 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand"
          :disabled="projectLoading"
          @click="fetchProjects"
        >
          {{ projectLoading ? '加载中…' : '刷新' }}
        </button>
      </div>
      <ul class="space-y-3">
        <li
          v-for="project in projects"
          :key="project.name"
          :class="[
            'rounded-2xl border border-transparent bg-slate-50/80 transition hover:-translate-y-0.5 hover:border-indigo-100 hover:bg-white',
            project.name === selectedProject ? 'border-indigo-200 bg-white shadow-md' : ''
          ]"
        >
          <button type="button" class="flex w-full flex-col gap-1 px-4 py-3 text-left" @click="selectProject(project.name)">
            <span class="text-base font-semibold text-slate-900">{{ project.name }}</span>
            <span class="text-xs uppercase tracking-widest text-slate-400">{{ formatTimestamp(project.updated_at) }}</span>
          </button>
        </li>
      </ul>
      <p v-if="!projects.length && !projectLoading" class="rounded-2xl bg-slate-100 px-4 py-3 text-sm text-slate-500">
        暂无项目，请先在项目面板中创建。
      </p>
    </aside>

    <section class="space-y-8">
      <header class="space-y-2">
        <h1 class="text-2xl font-semibold text-slate-900">项目数据归档</h1>
        <p class="text-sm text-slate-500">
          导入 Excel/CSV/JSONL 文件并自动生成 JSONL 与 PKL 存档，全部保存在 backend/data/projects/&lt;project&gt;/uploads 下。
        </p>
      </header>

      <div class="card-surface space-y-6 p-6">
        <div class="flex flex-wrap items-center justify-between gap-4">
          <h2 class="text-lg font-semibold text-slate-900">上传表格</h2>
          <span v-if="selectedProject" class="badge-soft bg-indigo-100 text-indigo-600">当前项目：{{ selectedProject }}</span>
        </div>
        <p class="text-sm text-slate-500">
          支持 .xlsx、.xls、.csv、.jsonl 文件，系统会为每份数据生成同名的 JSONL 与 PKL 文件，方便在后续流程中直接读取。
        </p>
        <form class="space-y-4" @submit.prevent="uploadDataset">
          <label
            class="flex min-h-[160px] cursor-pointer flex-col items-center justify-center gap-2 rounded-3xl border-2 border-dashed border-slate-300 bg-slate-50/70 px-6 text-center text-sm text-slate-500 transition hover:border-indigo-300 hover:bg-indigo-50/40"
            :class="{ 'border-indigo-300 bg-white shadow-inner text-indigo-600': uploadFile }"
          >
            <input ref="fileInput" type="file" class="hidden" accept=".xlsx,.xls,.csv,.jsonl" @change="handleFileChange" />
            <span class="text-sm font-medium">
              {{ uploadFile ? uploadFile.name : '点击或拖拽文件到此处' }}
            </span>
            <span class="text-xs text-slate-400">最大支持 50MB</span>
          </label>
          <div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <button
              type="submit"
              class="inline-flex items-center justify-center rounded-full bg-indigo-600 px-6 py-2 text-sm font-semibold text-white shadow hover:bg-indigo-500 disabled:cursor-not-allowed disabled:bg-slate-300"
              :disabled="uploading"
            >
              {{ uploading ? '上传中…' : '上传并归档' }}
            </button>
            <div class="space-y-1 text-sm">
              <p
                v-if="uploadHelper && !uploadError && !uploadSuccess"
                class="text-slate-500"
              >
                {{ uploadHelper }}
              </p>
              <p v-if="uploadError" class="text-rose-600">{{ uploadError }}</p>
              <p v-if="uploadSuccess" class="text-emerald-600">{{ uploadSuccess }}</p>
            </div>
          </div>
        </form>
      </div>

      <div class="card-surface space-y-6 p-6">
        <div class="flex flex-wrap items-center justify-between gap-4">
          <h2 class="text-lg font-semibold text-slate-900">数据集清单</h2>
          <span v-if="datasets.length" class="badge-soft">共 {{ datasets.length }} 个</span>
        </div>
        <p v-if="!selectedProject" class="rounded-2xl bg-slate-100 px-4 py-3 text-sm text-slate-500">请选择左侧项目以查看归档记录。</p>
        <p v-else-if="datasetLoading" class="rounded-2xl bg-slate-100 px-4 py-3 text-sm text-slate-500">数据加载中…</p>
        <p v-else-if="datasetError" class="rounded-2xl bg-rose-100 px-4 py-3 text-sm text-rose-600">{{ datasetError }}</p>
        <p v-else-if="!datasets.length" class="rounded-2xl bg-slate-100 px-4 py-3 text-sm text-slate-500">尚未上传任何数据集。</p>
        <ul v-else class="space-y-4">
          <li v-for="dataset in datasets" :key="dataset.id" class="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
            <header class="flex flex-wrap items-center justify-between gap-3">
              <h3 class="text-lg font-semibold text-slate-900">{{ dataset.display_name }}</h3>
              <span class="text-sm text-slate-500">{{ formatTimestamp(dataset.stored_at) }}</span>
            </header>
            <dl class="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <div class="space-y-1">
                <dt class="text-xs uppercase tracking-widest text-slate-400">数据行列</dt>
                <dd class="text-sm text-slate-600">{{ dataset.rows }} 行 · {{ dataset.column_count }} 列</dd>
              </div>
              <div class="space-y-1">
                <dt class="text-xs uppercase tracking-widest text-slate-400">源文件</dt>
                <dd class="text-sm text-slate-600">{{ dataset.source_file }}</dd>
              </div>
              <div class="space-y-1">
                <dt class="text-xs uppercase tracking-widest text-slate-400">PKL</dt>
                <dd class="text-sm text-slate-600">{{ dataset.pkl_file }}</dd>
              </div>
              <div class="space-y-1">
                <dt class="text-xs uppercase tracking-widest text-slate-400">JSONL</dt>
                <dd class="text-sm text-slate-600">{{ dataset.jsonl_file }}</dd>
              </div>
              <div class="space-y-1">
                <dt class="text-xs uppercase tracking-widest text-slate-400">Meta JSON</dt>
                <dd class="text-sm text-slate-600">{{ dataset.json_file }}</dd>
              </div>
            </dl>
            <details class="mt-4 rounded-2xl bg-slate-50/80 p-4 text-sm text-slate-600">
              <summary class="cursor-pointer text-sm font-medium text-slate-700">字段预览</summary>
              <p class="mt-2 break-words text-xs text-slate-500">{{ dataset.columns.join(', ') }}</p>
            </details>
          </li>
        </ul>
      </div>
    </section>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useActiveProject } from '../composables/useActiveProject'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api'

const projects = ref([])
const projectLoading = ref(false)

const datasets = ref([])
const datasetLoading = ref(false)
const datasetError = ref('')

const fileInput = ref(null)
const uploadFile = ref(null)
const uploading = ref(false)
const uploadError = ref('')
const uploadSuccess = ref('')

const { activeProject, activeProjectName, setActiveProject, clearActiveProject } = useActiveProject()
const selectedProject = computed(() => activeProjectName.value)

const uploadHelper = computed(() => {
  if (uploading.value) return ''
  if (!activeProjectName.value) return '请先在左侧选择一个项目'
  if (!uploadFile.value) return '请选择需要上传的表格文件'
  return ''
})

const fetchProjects = async () => {
  projectLoading.value = true
  try {
    const response = await fetch(`${API_BASE_URL}/projects`)
    if (!response.ok) {
      throw new Error('项目列表获取失败')
    }
    const data = await response.json()
    projects.value = Array.isArray(data.projects) ? data.projects : []
    if (!projects.value.length) {
      clearActiveProject()
    } else {
      const currentName = activeProjectName.value
      const matched = currentName
        ? projects.value.find((project) => project.name === currentName)
        : null
      const targetProject = matched || projects.value[0]
      setActiveProject(targetProject)
    }
  } catch (err) {
    console.error(err)
    projects.value = []
    clearActiveProject()
  } finally {
    projectLoading.value = false
  }
}

const fetchDatasets = async (projectName) => {
  if (!projectName) return
  datasetLoading.value = true
  datasetError.value = ''
  try {
    const response = await fetch(`${API_BASE_URL}/projects/${encodeURIComponent(projectName)}/datasets`)
    if (!response.ok) {
      throw new Error('读取数据集失败')
    }
    const data = await response.json()
    datasets.value = Array.isArray(data.datasets) ? data.datasets : []
  } catch (err) {
    datasetError.value = err instanceof Error ? err.message : '读取数据集失败'
    datasets.value = []
  } finally {
    datasetLoading.value = false
  }
}

const selectProject = async (projectName) => {
  if (activeProjectName.value === projectName) return
  const project = projects.value.find((item) => item.name === projectName)
  setActiveProject(project || projectName)
}

const handleFileChange = (event) => {
  uploadSuccess.value = ''
  uploadError.value = ''
  const [file] = event.target.files || []
  uploadFile.value = file || null
}

const uploadDataset = async () => {
  if (!activeProjectName.value) {
    uploadError.value = '请选择一个项目'
    return
  }

  if (!uploadFile.value) {
    uploadError.value = '请选择需要上传的文件'
    return
  }

  uploading.value = true
  uploadError.value = ''
  uploadSuccess.value = ''

  try {
    const formData = new FormData()
    formData.append('file', uploadFile.value)

    const response = await fetch(
      `${API_BASE_URL}/projects/${encodeURIComponent(activeProjectName.value)}/datasets`,
      {
        method: 'POST',
        body: formData
      }
    )

    if (!response.ok) {
      const payload = await response.json().catch(() => ({}))
      throw new Error(payload.message || '上传失败')
    }

    await response.json()
    uploadSuccess.value = '上传成功，已生成对应的 JSONL 与 PKL 文件。'
    uploadFile.value = null
    if (fileInput.value) {
      fileInput.value.value = ''
    }
    await fetchDatasets(activeProjectName.value)
  } catch (err) {
    uploadError.value = err instanceof Error ? err.message : '上传失败'
  } finally {
    uploading.value = false
  }
}

const formatTimestamp = (timestamp) => {
  if (!timestamp) return '未知时间'
  try {
    return new Date(timestamp).toLocaleString()
  } catch (err) {
    return timestamp
  }
}

onMounted(fetchProjects)

watch(
  activeProject,
  async (project) => {
    if (project?.name) {
      await fetchDatasets(project.name)
    } else {
      datasets.value = []
    }
  },
  { immediate: true }
)
</script>
