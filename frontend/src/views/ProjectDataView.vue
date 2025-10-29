<template>
  <div>
    <section v-if="isPreviewMode" class="space-y-6">
      <div v-if="selectedDataset" class="space-y-6">
        <header class="flex flex-wrap items-center justify-between gap-4 rounded-3xl border border-slate-200 bg-white/90 p-6 shadow-sm">
          <div class="flex flex-wrap items-center gap-3">
            <button
              type="button"
              class="inline-flex items-center gap-2 rounded-full border border-slate-200 px-3 py-1.5 text-sm font-medium text-slate-600 transition hover:border-indigo-200 hover:text-indigo-600 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand"
              @click="closePreview"
            >
              <ChevronLeftIcon class="h-4 w-4" />
              返回数据集列表
            </button>
            <span class="inline-flex items-center gap-2 rounded-full bg-indigo-100 px-3 py-1 text-xs font-semibold text-indigo-600">
              Excel 预览
            </span>
          </div>
          <div class="text-sm text-slate-500">
            共 {{ previewTotalRows }} 行 · 每页 {{ previewPageSize }} 行
          </div>
        </header>

        <section class="card-surface space-y-4 p-6">
          <header class="space-y-1">
            <h1 class="text-2xl font-semibold text-slate-900">{{ selectedDataset.display_name }}</h1>
            <p class="text-sm text-slate-500">
              数据集 ID：{{ selectedDataset.id }} · 专题：{{ selectedDataset.project }} · 更新于 {{ formatTimestamp(selectedDataset.stored_at) }}
            </p>
          </header>
          <dl class="grid gap-4 text-sm text-slate-600 sm:grid-cols-2 lg:grid-cols-3">
            <div class="space-y-1">
              <dt class="text-xs uppercase tracking-widest text-slate-400">文件大小</dt>
              <dd class="text-sm text-slate-600">{{ formatFileSize(selectedDataset.file_size) }}</dd>
            </div>
            <div class="space-y-1">
              <dt class="text-xs uppercase tracking-widest text-slate-400">数据行列</dt>
              <dd class="text-sm text-slate-600">{{ selectedDataset.rows }} 行 · {{ selectedDataset.column_count }} 列</dd>
            </div>
            <div class="space-y-1">
              <dt class="text-xs uppercase tracking-widest text-slate-400">字段列表</dt>
              <dd class="text-sm text-slate-600 break-words">{{ selectedDataset.columns.join(', ') }}</dd>
            </div>
            <div class="space-y-1">
              <dt class="text-xs uppercase tracking-widest text-slate-400">源文件</dt>
              <dd class="text-sm text-slate-600 truncate" :title="selectedDataset.source_file">{{ selectedDataset.source_file }}</dd>
            </div>
            <div class="space-y-1">
              <dt class="text-xs uppercase tracking-widest text-slate-400">JSONL</dt>
              <dd class="text-sm text-slate-600 truncate" :title="selectedDataset.jsonl_file">{{ selectedDataset.jsonl_file }}</dd>
            </div>
            <div class="space-y-1">
              <dt class="text-xs uppercase tracking-widest text-slate-400">PKL</dt>
              <dd class="text-sm text-slate-600 truncate" :title="selectedDataset.pkl_file">{{ selectedDataset.pkl_file }}</dd>
            </div>
          </dl>
        </section>

        <section class="card-surface space-y-6 p-6">
          <header class="flex flex-wrap items-center justify-between gap-4">
            <div>
              <h2 class="text-lg font-semibold text-slate-900">表格预览</h2>
              <p class="text-sm text-slate-500">实时从 JSONL 中按页读取数据</p>
            </div>
            <div class="flex items-center gap-3">
              <label class="text-xs font-medium text-slate-500">
                每页
                <select
                  class="ml-1 rounded-full border border-slate-200 bg-white px-3 py-1 text-sm text-slate-600 shadow-sm focus:border-indigo-300 focus:outline-none focus:ring-2 focus:ring-indigo-200"
                  :value="previewPageSize"
                  @change="changePreviewPageSize($event.target.value)"
                >
                  <option v-for="size in previewPageSizeOptions" :key="size" :value="size">{{ size }}</option>
                </select>
              </label>
              <button
                type="button"
                class="inline-flex items-center gap-1 rounded-full border border-slate-200 px-3 py-1 text-sm font-medium text-slate-600 transition hover:border-indigo-200 hover:text-indigo-600 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand"
                :disabled="previewLoading"
                @click="refreshDatasetPreview"
              >
                {{ previewLoading ? '刷新中…' : '刷新' }}
              </button>
            </div>
          </header>

          <div v-if="previewLoading" class="rounded-2xl bg-slate-50 px-4 py-6 text-sm text-slate-500">
            表格加载中…
          </div>
          <div v-else-if="previewError" class="rounded-2xl bg-rose-100 px-4 py-6 text-sm text-rose-600">
            {{ previewError }}
          </div>
          <div v-else class="space-y-4">
            <div v-if="!previewRows.length" class="rounded-2xl bg-slate-50 px-4 py-6 text-sm text-slate-500">
              当前页没有数据，请调整分页或重新导入。
            </div>
            <div v-else class="overflow-x-auto rounded-2xl border border-slate-200">
              <table class="min-w-full table-fixed divide-y divide-slate-200 text-sm text-slate-700">
                <thead class="bg-slate-50">
                  <tr v-for="headerGroup in previewTable.getHeaderGroups()" :key="headerGroup.id">
                    <th
                      v-for="header in headerGroup.headers"
                      :key="header.id"
                      class="px-4 py-2 text-left text-xs font-semibold uppercase tracking-wider text-slate-500"
                    >
                      <span v-if="!header.isPlaceholder">
                        <FlexRender :render="header.column.columnDef.header" :props="header.getContext()" />
                      </span>
                    </th>
                  </tr>
                </thead>
                <tbody class="divide-y divide-slate-100 bg-white">
                  <tr v-for="row in previewTable.getRowModel().rows" :key="row.id" class="hover:bg-indigo-50/40">
                    <td
                      v-for="cell in row.getVisibleCells()"
                      :key="cell.id"
                      class="px-4 py-2 align-top text-sm text-slate-700"
                    >
                      <div class="max-w-[320px] truncate text-ellipsis" :title="cell.getValue?.() ?? ''">
                        <FlexRender :render="cell.column.columnDef.cell" :props="cell.getContext()" />
                      </div>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>

            <div class="flex flex-wrap items-center justify-between gap-3 text-sm text-slate-500">
              <span>第 {{ previewCurrentPageDisplay }} / {{ previewTotalPagesDisplay }} 页 · 合计 {{ previewTotalRows }} 行</span>
              <div class="inline-flex items-center gap-2">
                <button
                  type="button"
                  class="rounded-full border border-slate-200 px-3 py-1 text-sm font-medium text-slate-600 transition hover:border-indigo-200 hover:text-indigo-600 disabled:cursor-not-allowed disabled:border-slate-100 disabled:text-slate-300"
                  :disabled="previewPage <= 1 || previewLoading"
                  @click="goToPreviewPage(previewPage - 1)"
                >
                  上一页
                </button>
                <button
                  type="button"
                  class="rounded-full border border-slate-200 px-3 py-1 text-sm font-medium text-slate-600 transition hover:border-indigo-200 hover:text-indigo-600 disabled:cursor-not-allowed disabled:border-slate-100 disabled:text-slate-300"
                  :disabled="previewPage >= previewTotalPages || previewLoading"
                  @click="goToPreviewPage(previewPage + 1)"
                >
                  下一页
                </button>
              </div>
            </div>
          </div>
        </section>
      </div>

      <div v-else class="rounded-3xl border border-slate-200 bg-white p-6 text-sm text-slate-500 shadow-sm">
        正在加载数据集详情…
      </div>
    </section>

    <div v-else class="grid gap-8 xl:grid-cols-[320px,minmax(0,1fr)]">
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
              'rounded-2xl border transition focus-within:ring-2 focus-within:ring-indigo-200 focus-within:ring-offset-2',
              project.name === selectedProject
                ? 'border-brand bg-brand text-white'
                : 'border-transparent bg-surface-muted hover:border-brand-soft hover:bg-brand-soft-muted'
            ]"
          >
            <button
              type="button"
              class="flex w-full flex-col gap-1.5 px-4 py-3 text-left transition"
              @click="selectProject(project.name)"
            >
              <span
                :class="[
                  'text-base font-semibold transition-colors',
                  project.name === selectedProject ? 'text-white' : 'text-slate-800'
                ]"
              >
                {{ project.name }}
              </span>
              <span
                v-if="project.description"
                :class="[
                  'text-sm transition-colors',
                  project.name === selectedProject ? 'text-white/80' : 'text-slate-600'
                ]"
              >
                {{ project.description }}
              </span>
              <span
                :class="[
                  'text-xs transition-colors',
                  project.name === selectedProject ? 'text-white/70' : 'text-slate-500'
                ]"
              >
                更新时间：{{ formatTimestamp(project.updated_at) }}
              </span>
              <span
                :class="[
                  'text-[11px] transition-colors',
                  project.name === selectedProject ? 'text-white/70' : 'text-slate-400'
                ]"
              >
                目录：{{ getUploadDirectory(project.slug) }}
              </span>
            </button>
          </li>
        </ul>
        <p
          v-if="projectError"
          class="rounded-2xl bg-rose-100 px-4 py-3 text-sm text-rose-600"
        >
          {{ projectError }}
        </p>
        <p
          v-else-if="!projects.length && !projectLoading"
          class="rounded-2xl bg-slate-100 px-4 py-3 text-sm text-slate-500"
        >
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
            <div class="space-y-1">
              <h2 class="text-lg font-semibold text-slate-900">数据集清单</h2>
              <p v-if="selectedProjectMeta" class="text-xs text-slate-400">
                存储目录：{{ getUploadDirectory(selectedProjectMeta.slug) }}
              </p>
            </div>
            <span v-if="datasets.length" class="badge-soft">共 {{ datasets.length }} 个</span>
          </div>
          <p v-if="!selectedProject" class="rounded-2xl bg-slate-100 px-4 py-3 text-sm text-slate-500">请选择左侧项目以查看归档记录。</p>
          <p v-else-if="datasetLoading" class="rounded-2xl bg-slate-100 px-4 py-3 text-sm text-slate-500">数据加载中…</p>
          <p v-else-if="datasetError" class="rounded-2xl bg-rose-100 px-4 py-3 text-sm text-rose-600">{{ datasetError }}</p>
          <p v-else-if="!datasets.length" class="rounded-2xl bg-slate-100 px-4 py-3 text-sm text-slate-500">尚未上传任何数据集。</p>
          <div v-else class="space-y-4">
            <p class="rounded-2xl bg-slate-50 px-4 py-3 text-sm text-slate-500">
              点击任何数据集卡片会在新的预览子页面中打开 Excel 的表格预览。
            </p>
            <ul class="space-y-4">
              <li
                v-for="dataset in datasets"
                :key="dataset.id"
                class="rounded-3xl border border-slate-200 bg-white shadow-sm transition hover:border-indigo-200 hover:shadow focus-within:ring-2 focus-within:ring-indigo-200"
              >
                <button
                  type="button"
                  class="flex w-full flex-col gap-4 p-5 text-left"
                  @click="setActiveDataset(dataset.id)"
                >
                  <header class="flex flex-wrap items-center justify-between gap-3">
                    <h3 class="text-lg font-semibold text-slate-900">{{ dataset.display_name }}</h3>
                    <span class="text-sm text-slate-500">{{ formatTimestamp(dataset.stored_at) }}</span>
                  </header>
                  <dl class="grid gap-4 text-sm text-slate-600 sm:grid-cols-2 lg:grid-cols-3">
                    <div class="space-y-1">
                      <dt class="text-xs uppercase tracking-widest text-slate-400">数据集 ID</dt>
                      <dd class="text-sm text-slate-600">{{ dataset.id }}</dd>
                    </div>
                    <div class="space-y-1">
                      <dt class="text-xs uppercase tracking-widest text-slate-400">专题名称</dt>
                      <dd class="text-sm text-slate-600">{{ dataset.project }}</dd>
                    </div>
                    <div class="space-y-1">
                      <dt class="text-xs uppercase tracking-widest text-slate-400">数据行列</dt>
                      <dd class="text-sm text-slate-600">{{ dataset.rows }} 行 · {{ dataset.column_count }} 列</dd>
                    </div>
                    <div class="space-y-1">
                      <dt class="text-xs uppercase tracking-widest text-slate-400">文件大小</dt>
                      <dd class="text-sm text-slate-600">{{ formatFileSize(dataset.file_size) }}</dd>
                    </div>
                    <div class="space-y-1">
                      <dt class="text-xs uppercase tracking-widest text-slate-400">存储目录</dt>
                      <dd class="text-sm text-slate-600 truncate max-w-xs sm:max-w-sm lg:max-w-md" :title="getUploadDirectory(dataset.project_slug)">{{ getUploadDirectory(dataset.project_slug) }}</dd>
                    </div>
                    <div class="space-y-1">
                      <dt class="text-xs uppercase tracking-widest text-slate-400">源文件</dt>
                      <dd class="text-sm text-slate-600 truncate max-w-xs sm:max-w-sm lg:max-w-md" :title="dataset.source_file">{{ dataset.source_file }}</dd>
                    </div>
                    <div class="space-y-1">
                      <dt class="text-xs uppercase tracking-widest text-slate-400">PKL</dt>
                      <dd class="text-sm text-slate-600 truncate max-w-xs sm:max-w-sm lg:max-w-md" :title="dataset.pkl_file">{{ dataset.pkl_file }}</dd>
                    </div>
                    <div class="space-y-1">
                      <dt class="text-xs uppercase tracking-widest text-slate-400">JSONL</dt>
                      <dd class="text-sm text-slate-600 truncate max-w-xs sm:max-w-sm lg:max-w-md" :title="dataset.jsonl_file">{{ dataset.jsonl_file }}</dd>
                    </div>
                    <div class="space-y-1">
                      <dt class="text-xs uppercase tracking-widest text-slate-400">Meta JSON</dt>
                      <dd class="text-sm text-slate-600 truncate max-w-xs sm:max-w-sm lg:max-w-md" :title="dataset.json_file">{{ dataset.json_file }}</dd>
                    </div>
                  </dl>
                  <p class="text-xs text-slate-500">字段：{{ dataset.columns.join(', ') }}</p>
                  <div class="flex flex-wrap items-center gap-2 text-xs text-slate-500">
                    <span class="rounded-full bg-slate-100 px-2 py-1 font-medium text-slate-600">
                      点击进入预览页
                    </span>
                  </div>
                </button>
              </li>
            </ul>
          </div>
        </div>
      </section>
    </div>
  </div>
</template>


<script setup>
import { FlexRender, getCoreRowModel, useVueTable } from '@tanstack/vue-table'
import { ChevronLeftIcon } from '@heroicons/vue/24/outline'
import { computed, onMounted, ref, watch } from 'vue'
import { useActiveProject } from '../composables/useActiveProject'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api'

const projects = ref([])
const projectLoading = ref(false)
const projectError = ref('')

const datasets = ref([])
const datasetLoading = ref(false)
const datasetError = ref('')

const activeDatasetId = ref('')
const previewRequestToken = ref(null)
const previewRows = ref([])
const previewColumns = ref([])
const previewLoading = ref(false)
const previewError = ref('')
const previewPage = ref(1)
const previewPageSize = ref(20)
const previewTotalRows = ref(0)
const previewTotalPages = ref(0)
const previewPageSizeOptions = [20, 50, 100]

const fileInput = ref(null)
const uploadFile = ref(null)
const uploading = ref(false)
const uploadError = ref('')
const uploadSuccess = ref('')

const { activeProject, activeProjectName, setActiveProject, clearActiveProject } = useActiveProject()
const selectedProject = computed(() => activeProjectName.value)
const selectedProjectMeta = computed(() =>
  activeProjectName.value
    ? projects.value.find((project) => project.name === activeProjectName.value) || null
    : null
)
const selectedDataset = computed(() =>
  activeDatasetId.value
    ? datasets.value.find((dataset) => dataset.id === activeDatasetId.value) || null
    : null
)
const isPreviewMode = computed(() => Boolean(activeDatasetId.value))
const previewTotalPagesDisplay = computed(() => previewTotalPages.value || 1)
const previewCurrentPageDisplay = computed(() =>
  Math.min(previewPage.value || 1, previewTotalPagesDisplay.value || 1)
)

const previewTableColumns = computed(() => {
  const dynamicColumns = previewColumns.value
    .filter((column) => column && column !== '__row_index')
    .map((column) => ({
      accessorKey: column,
      header: column,
      cell: ({ getValue }) => getValue?.() ?? '',
    }))
  return [
    {
      accessorKey: '__row_index',
      header: '#',
      cell: ({ getValue }) => getValue?.() ?? '',
    },
    ...dynamicColumns,
  ]
})

const previewTable = useVueTable({
  get data() {
    return previewRows.value
  },
  get columns() {
    return previewTableColumns.value
  },
  getCoreRowModel: getCoreRowModel(),
})

const normaliseProjectName = (value) => {
  if (!value) return 'project'
  return value
    .toString()
    .replace(/[^A-Za-z0-9._-]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .toLowerCase() || 'project'
}

const getUploadDirectory = (slug) => {
  if (!slug) return '—'
  return `backend/data/projects/${slug}/uploads`
}

const toNumber = (value) => {
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : 0
}

const formatFileSize = (size) => {
  const value = toNumber(size)
  if (!value) return '—'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let current = value
  let unitIndex = 0
  while (current >= 1024 && unitIndex < units.length - 1) {
    current /= 1024
    unitIndex += 1
  }
  const precision = current >= 100 || unitIndex === 0 ? 0 : current >= 10 ? 1 : 2
  return `${current.toFixed(precision)} ${units[unitIndex]}`
}

const normalizeProject = (project) => {
  if (!project || typeof project !== 'object') return null
  const name = project.name || ''
  const slug = normaliseProjectName(name)
  return {
    description: '',
    metadata: {},
    ...project,
    name,
    slug
  }
}

const normalizeDataset = (dataset) => {
  if (!dataset || typeof dataset !== 'object') return null
  const projectName = dataset.project || activeProjectName.value || ''
  const projectSlug = dataset.project_slug || normaliseProjectName(projectName)
  const displayName =
    dataset.display_name ||
    dataset.source_file?.split('/')?.pop() ||
    dataset.jsonl_file?.split('/')?.pop() ||
    dataset.id ||
    '数据集'

  return {
    id: dataset.id || '',
    project: projectName || '—',
    project_slug: projectSlug,
    display_name: displayName,
    stored_at: dataset.stored_at || '',
    rows: toNumber(dataset.rows),
    column_count: toNumber(dataset.column_count),
    columns: Array.isArray(dataset.columns)
      ? dataset.columns.map((column) => column.toString())
      : [],
    file_size: toNumber(dataset.file_size),
    source_file: dataset.source_file || '',
    pkl_file: dataset.pkl_file || '',
    jsonl_file: dataset.jsonl_file || '',
    json_file: dataset.json_file || ''
  }
}

const stringifyPreviewCell = (value) => {
  if (value === null || value === undefined) return ''
  if (typeof value === 'object') {
    try {
      return JSON.stringify(value)
    } catch (err) {
      return String(value)
    }
  }
  return String(value)
}

const resetPreviewState = () => {
  previewRows.value = []
  previewColumns.value = []
  previewTotalRows.value = 0
  previewTotalPages.value = 0
  previewError.value = ''
}

const clearActiveDatasetSelection = () => {
  activeDatasetId.value = ''
  previewPage.value = 1
  previewLoading.value = false
  previewRequestToken.value = null
  resetPreviewState()
}

const closePreview = () => {
  clearActiveDatasetSelection()
}

const fetchDatasetPreview = async (datasetId, pageArg = previewPage.value, pageSizeArg = previewPageSize.value) => {
  if (!activeProjectName.value || !datasetId) return
  const token = Symbol('preview')
  previewRequestToken.value = token
  previewLoading.value = true
  previewError.value = ''

  try {
    const params = new URLSearchParams({
      page: String(pageArg),
      page_size: String(pageSizeArg)
    })
    const response = await fetch(
      `${API_BASE_URL}/projects/${encodeURIComponent(activeProjectName.value)}/datasets/${encodeURIComponent(datasetId)}/preview?${params.toString()}`
    )
    const payload = await response.json().catch(() => null)
    if (!response.ok || !payload || payload.status !== 'ok') {
      const message = payload?.message || '无法加载数据集预览'
      throw new Error(message)
    }
    const data = payload.preview || {}
    if (previewRequestToken.value !== token || activeDatasetId.value !== datasetId) {
      return
    }
    previewColumns.value = Array.isArray(data.columns)
      ? data.columns.map((column) => column.toString())
      : []
    previewRows.value = Array.isArray(data.rows)
      ? data.rows.map((row) => {
          if (!row || typeof row !== 'object') return {}
          const entries = Object.entries(row).map(([key, value]) => [key, stringifyPreviewCell(value)])
          return Object.fromEntries(entries)
        })
      : []
    previewPage.value = Number(data.page) || pageArg
    previewPageSize.value = Number(data.page_size) || pageSizeArg
    const totalRows = Number(data.total_rows) || 0
    const totalPages = Number(data.total_pages) || 0
    previewTotalRows.value = totalRows
    previewTotalPages.value = totalRows > 0 ? Math.max(totalPages, 1) : totalPages
  } catch (err) {
    if (previewRequestToken.value === token) {
      resetPreviewState()
      previewError.value = err instanceof Error ? err.message : '无法加载数据集预览'
    }
  } finally {
    if (previewRequestToken.value === token) {
      previewLoading.value = false
      previewRequestToken.value = null
    }
  }
}

const setActiveDataset = (datasetId) => {
  if (!datasetId) {
    clearActiveDatasetSelection()
    return
  }
  const exists = datasets.value.some((dataset) => dataset.id === datasetId)
  if (!exists) return
  if (activeDatasetId.value === datasetId) return
  activeDatasetId.value = datasetId
  previewPage.value = 1
  resetPreviewState()
  if (typeof window !== 'undefined') {
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }
  fetchDatasetPreview(datasetId, 1, previewPageSize.value)
}

const refreshDatasetPreview = () => {
  if (!activeDatasetId.value) return
  fetchDatasetPreview(activeDatasetId.value, previewPage.value, previewPageSize.value)
}

const changePreviewPageSize = (value) => {
  const next = Number(value) || previewPageSize.value
  if (next === previewPageSize.value) return
  previewPageSize.value = next
  previewPage.value = 1
  if (activeDatasetId.value) {
    fetchDatasetPreview(activeDatasetId.value, 1, next)
  }
}

const goToPreviewPage = (targetPage) => {
  if (!activeDatasetId.value) return
  const total = previewTotalPages.value || 1
  const next = Math.min(Math.max(targetPage, 1), total)
  if (next === previewPage.value) return
  previewPage.value = next
  fetchDatasetPreview(activeDatasetId.value, next, previewPageSize.value)
}

const uploadHelper = computed(() => {
  if (uploading.value) return ''
  if (!activeProjectName.value) return '请先在左侧选择一个项目'
  if (!uploadFile.value) return '请选择需要上传的表格文件'
  return ''
})

const fetchProjects = async () => {
  projectLoading.value = true
  projectError.value = ''
  try {
    const response = await fetch(`${API_BASE_URL}/projects`)
    const payload = await response.json().catch(() => null)
    if (!response.ok || !payload || payload.status !== 'ok') {
      const message = payload?.message || '项目列表获取失败'
      throw new Error(message)
    }
    const list = Array.isArray(payload.projects) ? payload.projects : []
    projects.value = list
      .map(normalizeProject)
      .filter(Boolean)
    if (!projects.value.length) {
      clearActiveProject()
      clearActiveDatasetSelection()
      return
    }
    const currentName = activeProjectName.value
    const matched = currentName
      ? projects.value.find((project) => project.name === currentName)
      : null
    const targetProject = matched || projects.value[0]
    setActiveProject(targetProject)
  } catch (err) {
    console.error(err)
    projectError.value = err instanceof Error ? err.message : '项目列表获取失败'
    projects.value = []
    clearActiveProject()
    clearActiveDatasetSelection()
  } finally {
    projectLoading.value = false
  }
}

const fetchDatasets = async (projectName) => {
  if (!projectName) {
    datasets.value = []
    clearActiveDatasetSelection()
    return
  }
  datasetLoading.value = true
  datasetError.value = ''
  try {
    const response = await fetch(`${API_BASE_URL}/projects/${encodeURIComponent(projectName)}/datasets`)
    const payload = await response.json().catch(() => null)
    if (!response.ok || !payload || payload.status !== 'ok') {
      const message = payload?.message || '读取数据集失败'
      throw new Error(message)
    }
    const list = Array.isArray(payload.datasets) ? payload.datasets : []
    datasets.value = list
      .map(normalizeDataset)
      .filter(Boolean)
    if (!datasets.value.length) {
      clearActiveDatasetSelection()
      return
    }
    if (activeDatasetId.value) {
      const exists = datasets.value.some((dataset) => dataset.id === activeDatasetId.value)
      if (exists) {
        fetchDatasetPreview(activeDatasetId.value, previewPage.value, previewPageSize.value)
      } else {
        clearActiveDatasetSelection()
      }
    }
  } catch (err) {
    datasetError.value = err instanceof Error ? err.message : '读取数据集失败'
    datasets.value = []
    clearActiveDatasetSelection()
  } finally {
    datasetLoading.value = false
  }
}

const selectProject = async (projectName) => {
  if (activeProjectName.value === projectName) return
  const project = projects.value.find((item) => item.name === projectName)
  clearActiveDatasetSelection()
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

    const payload = await response.json().catch(() => null)
    if (!response.ok || !payload || payload.status !== 'ok') {
      const message = payload?.message || '上传失败'
      throw new Error(message)
    }

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
      clearActiveDatasetSelection()
    }
  },
  { immediate: true }
)
</script>
