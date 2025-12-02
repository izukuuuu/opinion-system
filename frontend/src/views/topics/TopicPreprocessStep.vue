<template>
  <div class="space-y-8">
    <header class="flex flex-wrap items-center justify-between gap-3">
      <div class="space-y-1">
        <h1 class="text-2xl font-semibold text-primary">数据预处理</h1>
        <p class="text-sm text-secondary">按日期依次执行 Merge、Clean，生成标准化结果。</p>
      </div>
      <div class="flex items-center gap-2 rounded-full bg-brand-soft px-3 py-1 text-xs font-semibold text-brand-600">
        <FunnelIcon class="h-4 w-4" />
        <span>步骤 2 · 预处理</span>
      </div>
    </header>

<section class="card-surface space-y-6 p-6">
  <header class="space-y-2">
    <h2 class="text-xl font-semibold text-primary">选择数据集</h2>
    <p class="text-sm text-secondary">
      请选择需要预处理的数据集，系统会自动使用当前项目名称与处理日期执行任务。
    </p>
  </header>
  <form class="space-y-4">
    <label class="space-y-1 text-sm">
      <span class="font-medium text-secondary">选择项目</span>
      <div class="flex flex-wrap items-center gap-3">
        <select
          v-if="projectOptions.length"
          v-model="selectedProjectName"
          class="inline-flex min-w-[220px] items-center rounded-2xl border border-soft bg-white px-3 py-2 text-sm text-secondary shadow-sm transition focus:border-brand-soft focus:outline-none focus:ring-2 focus:ring-brand-200"
          :disabled="projectsLoading"
        >
          <option disabled value="">请选择项目</option>
          <option v-for="option in projectOptions" :key="option.value" :value="option.value">
            {{ option.label }}
          </option>
        </select>
        <span v-else class="text-xs text-muted">
          暂无项目，请先在“项目数据”模块创建。
        </span>
        <button
          type="button"
          class="inline-flex items-center gap-1 rounded-full border border-soft px-3 py-1.5 text-xs font-semibold text-secondary transition hover:border-brand-soft hover:text-brand-600 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand disabled:cursor-not-allowed disabled:opacity-60"
          :disabled="projectsLoading"
          @click.prevent="refreshProjects"
        >
          {{ projectsLoading ? '加载中…' : '刷新项目' }}
        </button>
      </div>
      <p v-if="projectsError" class="mt-2 rounded-2xl bg-rose-50 px-3 py-1 text-xs text-rose-600">
        {{ projectsError }}
      </p>
    </label>
    <label class="space-y-1 text-sm">
      <span class="font-medium text-secondary">选择数据集</span>
      <div class="flex flex-col gap-2">
        <div class="flex flex-wrap items-center gap-3">
          <select
            v-if="datasetOptions.length"
            v-model="selectedDatasetIds"
            multiple
            class="inline-flex min-w-[260px] max-w-md items-center rounded-2xl border border-soft bg-white px-3 py-2 text-sm text-secondary shadow-sm transition focus:border-brand-soft focus:outline-none focus:ring-2 focus:ring-brand-200"
            :size="Math.min(datasetOptions.length, 6)"
            :disabled="datasetsLoading"
          >
            <option v-for="option in datasetOptions" :key="option.id" :value="option.id">
              {{ option.label }}
            </option>
          </select>
          <span v-else class="text-xs text-muted">
            当前项目暂无可用数据集，请先在“项目数据”页面完成上传。
          </span>
          <button
            type="button"
            class="inline-flex items-center gap-1 rounded-full border border-soft px-3 py-1.5 text-xs font-semibold text-secondary transition hover:border-brand-soft hover:text-brand-600 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand disabled:cursor-not-allowed disabled:opacity-60"
            :disabled="datasetsLoading"
            @click="refreshDatasets"
          >
            {{ datasetsLoading ? '加载中…' : '刷新数据集' }}
          </button>
        </div>
        <p v-if="datasetOptions.length" class="text-xs text-muted">
          可多选数据集，系统会按所选顺序依次执行 Merge / Clean。建议确保这些数据集字段一致。
        </p>
      </div>
      <p v-if="datasetsError" class="mt-2 rounded-2xl bg-rose-50 px-3 py-1 text-xs text-rose-600">
        {{ datasetsError }}
      </p>
    </label>
    <label class="space-y-1 text-sm">
      <span class="font-medium text-secondary">选择 Merge 存档日期</span>
      <div class="flex flex-col gap-2">
        <div class="flex flex-wrap items-center gap-3">
          <select
            v-if="rawArchiveOptions.length"
            v-model="archiveSelection.mergeDate"
            class="inline-flex min-w-[260px] items-center rounded-2xl border border-soft bg-white px-3 py-2 text-sm text-secondary shadow-sm transition focus:border-brand-soft focus:outline-none focus:ring-2 focus:ring-brand-200"
            :disabled="archivesState.loading"
          >
            <option disabled value="">请选择原始存档</option>
            <option v-for="option in rawArchiveOptions" :key="option.value" :value="option.value">
              {{ option.label }}
            </option>
          </select>
          <template v-else>
            <input
              v-model="archiveSelection.mergeDate"
              type="text"
              inputmode="numeric"
              class="inline-flex min-w-[220px] items-center rounded-2xl border border-soft bg-white px-3 py-2 text-sm text-secondary shadow-sm transition focus:border-brand-soft focus:outline-none focus:ring-2 focus:ring-brand-200"
              placeholder="例如 20251202"
            />
            <button
              v-if="mergeDateSuggestion"
              type="button"
              class="inline-flex items-center gap-1 rounded-full border border-soft px-3 py-1.5 text-xs font-semibold text-secondary transition hover:border-brand-soft hover:text-brand-600 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand"
              @click="useMergeDateSuggestion"
            >
              使用 {{ mergeDateSuggestion }} 日期
            </button>
          </template>
          <button
            type="button"
            class="inline-flex items-center gap-1 rounded-full border border-soft px-3 py-1.5 text-xs font-semibold text-secondary transition hover:border-brand-soft hover:text-brand-600 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand disabled:cursor-not-allowed disabled:opacity-60"
            :disabled="archivesState.loading || !currentProjectName"
            @click="fetchProjectArchives({ force: true })"
          >
            {{ archivesState.loading ? '刷新中…' : '刷新存档' }}
          </button>
        </div>
        <p class="text-xs text-muted">
          <template v-if="rawArchiveOptions.length">
            请选择需要 Merge 的历史 RAW 存档日期，系统会沿用该批次的原始文件。
          </template>
          <template v-else>
            未找到 RAW 存档，可直接输入本次 Merge 的处理日期，系统会按该日期创建新的原始目录。
            <span v-if="mergeDateSuggestion" class="ml-1">建议使用最近上传日期 {{ mergeDateSuggestion }}。</span>
          </template>
        </p>
      </div>
    </label>
    <label class="space-y-1 text-sm">
      <span class="font-medium text-secondary">选择 Clean 存档来源</span>
      <div class="flex flex-wrap items-center gap-3">
        <select
          v-if="mergeArchiveOptions.length"
          v-model="archiveSelection.cleanDate"
          class="inline-flex min-w-[260px] items-center rounded-2xl border border-soft bg-white px-3 py-2 text-sm text-secondary shadow-sm transition focus:border-brand-soft focus:outline-none focus:ring-2 focus:ring-brand-200"
          :disabled="archivesState.loading"
        >
          <option disabled value="">请选择 Merge 存档</option>
          <option v-for="option in mergeArchiveOptions" :key="option.value" :value="option.value">
            {{ option.label }}
          </option>
        </select>
        <span v-else class="text-xs text-muted">
          {{ archivesState.loading ? '存档加载中…' : '未找到 Merge 存档，请先执行 Merge。' }}
        </span>
      </div>
    </label>
  </form>
  <p v-if="parameterError" class="rounded-2xl bg-rose-100 px-4 py-2 text-sm text-rose-600">{{ parameterError }}</p>
</section>

    <section class="card-surface space-y-5 p-6">
      <header class="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 class="text-xl font-semibold text-primary">存档管理</h2>
          <p class="text-sm text-secondary">系统会列出 Raw、Merge、Clean 三个阶段的历史存档，供后续步骤复用。</p>
        </div>
        <button
          type="button"
          class="inline-flex items-center gap-1 rounded-full border border-soft px-3 py-1.5 text-xs font-semibold text-secondary transition hover:border-brand-soft hover:text-brand-600 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand disabled:cursor-not-allowed disabled:opacity-60"
          :disabled="archivesState.loading"
          @click="fetchProjectArchives({ force: true })"
        >
          {{ archivesState.loading ? '刷新中…' : '刷新存档' }}
        </button>
      </header>
      <p v-if="archivesState.error" class="rounded-2xl bg-rose-100 px-4 py-2 text-sm text-rose-600">
        {{ archivesState.error }}
      </p>
      <div class="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        <!-- RAW 原始数据存档 -->
        <article class="card-surface flex flex-col space-y-4 p-5 shadow-sm transition hover:shadow-md">
          <header class="flex items-start justify-between gap-3">
            <div class="min-w-0 flex-1 space-y-1.5">
              <p class="text-xs uppercase tracking-[0.2em] text-muted">RAW</p>
              <h3 class="text-base font-semibold leading-tight text-primary">原始数据存档</h3>
              <p class="text-xs leading-relaxed text-secondary">请选择需要执行 Merge 的日期。</p>
            </div>
            <span class="flex-shrink-0 whitespace-nowrap text-xs font-medium text-muted">
              {{ archivesState.data.raw.length ? `共 ${archivesState.data.raw.length} 份` : '暂无' }}
            </span>
          </header>
          <div class="flex-1">
            <div v-if="archivesState.loading" class="flex items-center justify-center rounded-xl bg-surface-muted px-4 py-8 text-xs text-muted">
              存档加载中…
            </div>
            <p v-else-if="!archivesState.data.raw.length" class="flex items-center justify-center rounded-xl bg-surface-muted px-4 py-8 text-xs leading-relaxed text-muted">
              暂未找到原始数据存档，请先上传或刷新后重试。
            </p>
            <div v-else class="flex flex-wrap gap-2">
              <div
                v-for="archive in archivesState.data.raw"
                :key="archive.date"
                class="group relative inline-flex min-w-0 flex-1 flex-col gap-1.5 rounded-xl border p-0"
                :class="archiveSelection.mergeDate === archive.date
                  ? 'border-brand bg-brand-soft/50 text-brand-700'
                  : 'border-soft bg-surface text-secondary hover:border-brand-soft hover:bg-brand-soft/30'"
              >
                <button
                  type="button"
                  class="flex-1 rounded-xl px-3 py-2.5 text-left transition focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand"
                  @click="archiveSelection.mergeDate = archive.date"
                >
                  <span class="break-words text-sm font-semibold text-primary">{{ archive.date }}</span>
                  <span class="text-xs leading-snug text-muted">
                    {{ archive.file_count || 0 }} 文件 · 更新于 {{ archive.updated_at?.slice(0, 19) || '—' }}
                  </span>
                  <span
                    v-if="archive.matches_dataset"
                    class="inline-flex w-fit items-center gap-1 rounded-full bg-emerald-50 px-2 py-0.5 text-[11px] font-medium text-emerald-700"
                  >
                    匹配当前数据集
                  </span>
                </button>
                <div class="flex border-t border-soft">
                  <button
                    type="button"
                    class="flex-1 rounded-bl-xl px-3 py-1.5 text-xs text-red-600 transition hover:bg-red-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-red-600"
                    :disabled="deleteArchiveState.deleting"
                    @click="confirmDeleteArchive('raw', archive.date)"
                  >
                    {{ deleteArchiveState.deleting ? '删除中…' : '删除' }}
                  </button>
                </div>
              </div>
            </div>
          </div>
        </article>

        <!-- MERGE 输出存档 -->
        <article class="card-surface flex flex-col space-y-4 p-5 shadow-sm transition hover:shadow-md">
          <header class="flex items-start justify-between gap-3">
            <div class="min-w-0 flex-1 space-y-1.5">
              <p class="text-xs uppercase tracking-[0.2em] text-muted">MERGE</p>
              <h3 class="text-base font-semibold leading-tight text-primary">Merge 输出存档</h3>
              <p class="text-xs leading-relaxed text-secondary">选择需要进行 Clean 的 Merge 存档。</p>
            </div>
            <span class="flex-shrink-0 whitespace-nowrap text-xs font-medium text-muted">
              {{ archivesState.data.merge.length ? `共 ${archivesState.data.merge.length} 份` : '暂无' }}
            </span>
          </header>
          <div class="flex-1">
            <div v-if="archivesState.loading" class="flex items-center justify-center rounded-xl bg-surface-muted px-4 py-8 text-xs text-muted">
              存档加载中…
            </div>
            <p v-else-if="!archivesState.data.merge.length" class="flex items-center justify-center rounded-xl bg-surface-muted px-4 py-8 text-xs leading-relaxed text-muted">
              暂未找到 Merge 存档，请先执行 Merge。
            </p>
            <div v-else class="flex flex-wrap gap-2">
              <div
                v-for="archive in archivesState.data.merge"
                :key="archive.date"
                class="group relative inline-flex min-w-0 flex-1 flex-col gap-1.5 rounded-xl border p-0"
                :class="archiveSelection.cleanDate === archive.date
                  ? 'border-brand bg-brand-soft/50 text-brand-700'
                  : 'border-soft bg-surface text-secondary hover:border-brand-soft hover:bg-brand-soft/30'"
              >
                <button
                  type="button"
                  class="flex-1 rounded-xl px-3 py-2.5 text-left transition focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand"
                  @click="archiveSelection.cleanDate = archive.date"
                >
                  <span class="break-words text-sm font-semibold text-primary">{{ archive.date }}</span>
                  <span class="text-xs leading-snug text-muted">
                    {{ archive.channels?.length || 0 }} 渠道 · 更新于 {{ archive.updated_at?.slice(0, 19) || '—' }}
                  </span>
                </button>
                <div class="flex border-t border-soft">
                  <button
                    type="button"
                    class="flex-1 rounded-bl-xl px-3 py-1.5 text-xs text-red-600 transition hover:bg-red-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-red-600"
                    :disabled="deleteArchiveState.deleting"
                    @click="confirmDeleteArchive('merge', archive.date)"
                  >
                    {{ deleteArchiveState.deleting ? '删除中…' : '删除' }}
                  </button>
                </div>
              </div>
            </div>
          </div>
        </article>

        <!-- CLEAN 输出存档 -->
        <article class="card-surface flex flex-col space-y-4 p-5 shadow-sm transition hover:shadow-md">
          <header class="flex items-start justify-between gap-3">
            <div class="min-w-0 flex-1 space-y-1.5">
              <p class="text-xs uppercase tracking-[0.2em] text-muted">CLEAN</p>
              <h3 class="text-base font-semibold leading-tight text-primary">Clean 输出存档</h3>
              <p class="text-xs leading-relaxed text-secondary">供筛选步骤使用，当前页面仅展示概览。</p>
            </div>
            <span class="flex-shrink-0 whitespace-nowrap text-xs font-medium text-muted">
              {{ archivesState.data.clean.length ? `共 ${archivesState.data.clean.length} 份` : '暂无' }}
            </span>
          </header>
          <div class="flex-1">
            <div v-if="archivesState.loading" class="flex items-center justify-center rounded-xl bg-surface-muted px-4 py-8 text-xs text-muted">
              存档加载中…
            </div>
            <p v-else-if="!archivesState.data.clean.length" class="flex items-center justify-center rounded-xl bg-surface-muted px-4 py-8 text-xs leading-relaxed text-muted">
              暂未找到 Clean 存档。
            </p>
            <div v-else class="flex flex-wrap gap-2">
              <div
                v-for="archive in archivesState.data.clean"
                :key="`clean-${archive.date}`"
                class="group relative inline-flex min-w-0 flex-1 flex-col gap-1.5 rounded-xl border p-0 border-soft bg-surface hover:border-brand-soft hover:bg-brand-soft/20"
              >
                <div class="rounded-xl px-3 py-2.5">
                  <p class="break-words text-sm font-semibold text-primary">{{ archive.date }}</p>
                  <p class="mt-1 text-xs leading-snug text-muted">
                    {{ archive.channels?.length || 0 }} 渠道 · 更新于 {{ archive.updated_at?.slice(0, 19) || '—' }}
                  </p>
                </div>
                <div class="flex border-t border-soft">
                  <button
                    type="button"
                    class="flex-1 rounded-bl-xl px-3 py-1.5 text-xs text-red-600 transition hover:bg-red-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-red-600"
                    :disabled="deleteArchiveState.deleting"
                    @click="confirmDeleteArchive('clean', archive.date)"
                  >
                    {{ deleteArchiveState.deleting ? '删除中…' : '删除' }}
                  </button>
                </div>
              </div>
            </div>
          </div>
        </article>
      </div>
    </section>

    <section class="space-y-5">
      <div class="card-surface flex flex-wrap items-center justify-between gap-3 p-6">
        <div class="space-y-1">
          <h2 class="text-xl font-semibold text-primary">预处理执行</h2>
          <p class="text-sm text-secondary">可单独运行每个步骤，或使用一键执行快速完成 Merge 与 Clean。</p>
        </div>
        <button
          type="button"
          class="inline-flex items-center gap-2 rounded-full border border-brand-soft px-4 py-2 text-sm font-semibold text-brand-600 transition hover:bg-brand-soft focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-600 disabled:cursor-not-allowed disabled:opacity-60"
          :disabled="pipeline.running"
          @click="runPipeline"
        >
          <SparklesIcon class="h-4 w-4" />
          <span>{{ pipeline.running ? '执行中…' : '一键执行' }}</span>
        </button>
      </div>

      <div class="space-y-5">
        <article
          v-for="operation in operations"
          :key="operation.key"
          class="card-surface space-y-4 p-6"
        >
          <header class="flex items-center gap-3">
            <span class="flex h-10 w-10 items-center justify-center rounded-2xl bg-brand-soft text-brand-600">
              <component :is="operation.icon" class="h-5 w-5" />
            </span>
            <div>
              <p class="text-xs uppercase tracking-[0.2em] text-muted">{{ operation.subtitle }}</p>
              <h3 class="text-base font-semibold text-primary">{{ operation.title }}</h3>
            </div>
          </header>
          <p class="text-sm leading-relaxed text-secondary">
            {{ operation.description }}
          </p>
          <div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <button
              type="button"
              class="btn-base btn-tone-primary px-4 py-1.5"
              :disabled="statuses[operation.key].running"
              @click="runOperation(operation.key)"
            >
              <span v-if="statuses[operation.key].running">执行中…</span>
              <span v-else>执行 {{ operation.label }}</span>
            </button>
            <p
              v-if="statuses[operation.key].message"
              :class="[
                'text-sm rounded-2xl px-3 py-1.5',
                statuses[operation.key].success ? 'bg-emerald-100 text-emerald-600' : 'bg-rose-100 text-rose-600'
              ]"
            >
              {{ statuses[operation.key].message }}
            </p>
          </div>
        </article>
      </div>

      <p v-if="pipeline.message" :class="[
        'rounded-2xl px-4 py-2 text-sm',
          pipeline.success ? 'bg-emerald-100 text-emerald-600' : 'bg-rose-100 text-rose-600'
      ]">
        {{ pipeline.message }}
      </p>
    </section>

    <!-- 删除确认对话框 -->
    <div
      v-if="deleteArchiveState.deleteConfirm.show"
      class="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
      @click.self="closeDeleteConfirm"
    >
      <div class="mx-4 max-w-md rounded-xl bg-white p-6 shadow-xl">
        <div class="mb-4">
          <h3 class="text-lg font-semibold text-red-600">确认删除存档</h3>
          <p class="mt-2 text-sm text-secondary">
            您确定要删除 <span class="font-mono font-semibold">{{ deleteArchiveState.deleteConfirm.layer.toUpperCase() }}</span>
            存档 <span class="font-mono font-semibold">{{ deleteArchiveState.deleteConfirm.date }}</span> 吗？
          </p>
          <p v-if="deleteArchiveState.deleteConfirm.error" class="mt-3 text-sm text-red-600">
            {{ deleteArchiveState.deleteConfirm.error }}
          </p>
        </div>

        <div class="mb-4 rounded-lg bg-amber-50 p-3">
          <p class="text-sm text-amber-800">
            <strong>警告：</strong>此操作不可撤销，删除后将无法恢复。
          </p>
        </div>

        <div class="flex justify-end gap-3">
          <button
            type="button"
            class="rounded-lg border border-soft px-4 py-2 text-sm font-medium text-secondary transition hover:bg-surface disabled:opacity-60"
            :disabled="deleteArchiveState.deleting"
            @click="closeDeleteConfirm"
          >
            取消
          </button>
          <button
            type="button"
            class="rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-red-700 disabled:opacity-60"
            :disabled="deleteArchiveState.deleting"
            @click="executeDeleteArchive"
          >
            {{ deleteArchiveState.deleting ? '删除中…' : '确认删除' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useApiBase } from '../../composables/useApiBase'
import {
  FunnelIcon,
  ArrowPathRoundedSquareIcon,
  TrashIcon,
  SparklesIcon
} from '@heroicons/vue/24/outline'
import { useTopicCreationProject } from '../../composables/useTopicCreationProject'

const { ensureApiBase } = useApiBase()

const parameterError = ref('')
const {
  projectOptions,
  projectsLoading,
  projectsError,
  selectedProjectName,
  loadProjects,
  refreshProjects
} = useTopicCreationProject()
const datasets = ref([])
const datasetsLoading = ref(false)
const datasetsError = ref('')
const selectedDatasetIds = ref([])
const lastFetchedProjectName = ref('')

const datasetTimestampFormatter = new Intl.DateTimeFormat('zh-CN', {
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit'
})

const buildApiUrl = async (path) => {
  const baseUrl = await ensureApiBase()
  return `${baseUrl}${path}`
}

const operations = [
  {
    key: 'merge',
    label: 'Merge',
    title: '合并 Merge',
    subtitle: 'Step 01',
    description: '整合 TRS 导出的多份原始 Excel，生成标准化的主题数据表。',
    path: '/merge',
    icon: ArrowPathRoundedSquareIcon
  },
  {
    key: 'clean',
    label: 'Clean',
    title: '清洗 Clean',
    subtitle: 'Step 02',
    description: '执行数据清洗，补齐字段与格式，移除重复与异常值，为下一步筛选做好准备。',
    path: '/clean',
    icon: TrashIcon
  }
]

const statuses = reactive(
  operations.reduce((acc, operation) => {
    acc[operation.key] = { running: false, success: null, message: '' }
    return acc
  }, {})
)

const pipeline = reactive({
  running: false,
  success: null,
  message: ''
})

const deleteArchiveState = reactive({
  deleting: false,
  deleteConfirm: {
    show: false,
    layer: '',
    date: '',
    error: ''
  }
})

const archivesState = reactive({
  loading: false,
  error: '',
  data: {
    raw: [],
    merge: [],
    clean: []
  },
  latest: {
    raw: '',
    merge: '',
    clean: ''
  },
  lastProject: '',
  lastDataset: ''
})

const archiveSelection = reactive({
  mergeDate: '',
  cleanDate: ''
})

const currentProjectName = computed(() => selectedProjectName.value || '')
const archiveDatasetId = computed(() => (selectedDatasetIds.value.length === 1 ? selectedDatasetIds.value[0] : ''))
const datasetOptions = computed(() =>
  datasets.value.map((item) => {
    const name = item.display_name || item.id
    const timestamp = formatTimestamp(item.stored_at)
    const parts = [name]
    if (item.topic_label) {
      parts.push(`专题：${item.topic_label}`)
    }
    if (timestamp && timestamp !== '—') {
      parts.push(`更新于 ${timestamp}`)
    }
    return {
      id: item.id,
      label: parts.join(' · '),
      raw: item
    }
  })
)
const mergeDateSuggestion = computed(() => {
  if (!selectedDatasetIds.value.length) return ''
  const [firstId] = selectedDatasetIds.value
  const found = datasets.value.find((item) => item.id === firstId)
  if (!found) return ''
  return formatDateKey(found.stored_at || found.created_at || '')
})
const rawArchiveOptions = computed(() => {
  const records = Array.isArray(archivesState.data.raw) ? archivesState.data.raw : []
  return records
    .map((archive) => {
      const date = typeof archive.date === 'string' ? archive.date : ''
      if (!date) return null
      const parts = [date]
      const fileCount = typeof archive.file_count === 'number' ? archive.file_count : null
      const updated = typeof archive.updated_at === 'string' ? archive.updated_at.slice(0, 16) : ''
      const meta = []
      if (fileCount) meta.push(`${fileCount} 文件`)
      if (archive.matches_dataset) meta.push('匹配当前数据集')
      if (updated) meta.push(`更新于 ${updated}`)
      if (meta.length) {
        parts.push(meta.join(' · '))
      }
      return {
        value: date,
        label: parts.join(' · ')
      }
    })
    .filter(Boolean)
})

const mergeArchiveOptions = computed(() => {
  const records = Array.isArray(archivesState.data.merge) ? archivesState.data.merge : []
  return records
    .map((archive) => {
      const date = typeof archive.date === 'string' ? archive.date : ''
      if (!date) return null
      const parts = [date]
      const channelCount = Array.isArray(archive.channels) ? archive.channels.length : null
      const updated = typeof archive.updated_at === 'string' ? archive.updated_at.slice(0, 16) : ''
      const meta = []
      if (channelCount) meta.push(`${channelCount} 渠道`)
      if (updated) meta.push(`更新于 ${updated}`)
      if (meta.length) {
        parts.push(meta.join(' · '))
      }
      return {
        value: date,
        label: parts.join(' · ')
      }
    })
    .filter(Boolean)
})

const describeDataset = (datasetId) => {
  if (!datasetId) return '未指定'
  const found = datasets.value.find((item) => item.id === datasetId)
  return found?.display_name || datasetId
}
const formatDateKey = (value) => {
  if (!value) return ''
  if (value instanceof Date && !Number.isNaN(value.getTime())) {
    const year = value.getFullYear()
    const month = `${value.getMonth() + 1}`.padStart(2, '0')
    const day = `${value.getDate()}`.padStart(2, '0')
    return `${year}${month}${day}`
  }
  if (typeof value === 'string') {
    const trimmed = value.trim()
    if (/^\d{8}$/.test(trimmed)) {
      return trimmed
    }
    const parsed = new Date(trimmed)
    if (!Number.isNaN(parsed.getTime())) {
      const year = parsed.getUTCFullYear()
      const month = `${parsed.getUTCMonth() + 1}`.padStart(2, '0')
      const day = `${parsed.getUTCDate()}`.padStart(2, '0')
      return `${year}${month}${day}`
    }
  }
  return ''
}
const formatTimestamp = (value) => {
  if (!value) return ''
  try {
    const dateObj = new Date(value)
    if (Number.isNaN(dateObj.getTime())) return value
    return datasetTimestampFormatter.format(dateObj)
  } catch (error) {
    return value
  }
}

const resetDatasetState = () => {
  datasets.value = []
  datasetsError.value = ''
  datasetsLoading.value = false
  selectedDatasetIds.value = []
  lastFetchedProjectName.value = ''
  resetArchivesState()
}

const fetchProjectDatasets = async (projectName, { force = false } = {}) => {
  const trimmed = projectName.trim()
  if (!trimmed) {
    resetDatasetState()
    return
  }
  if (!force && lastFetchedProjectName.value === trimmed && datasets.value.length) {
    return
  }

  datasetsLoading.value = true
  datasetsError.value = ''
  try {
    const endpoint = await buildApiUrl(`/projects/${encodeURIComponent(trimmed)}/datasets`)
    const response = await fetch(endpoint)
    const result = await response.json()
    if (!response.ok || result.status !== 'ok') {
      throw new Error(result.message || '无法加载专题数据集')
    }
    const items = Array.isArray(result.datasets) ? result.datasets : []
    datasets.value = items.map((item) => ({
      ...item,
      topic_label: typeof item.topic_label === 'string' ? item.topic_label.trim() : ''
    }))
    lastFetchedProjectName.value = trimmed

    if (items.length) {
      const current = new Set(selectedDatasetIds.value)
      const preserved = items.filter((item) => current.has(item.id)).map((item) => item.id)
      if (preserved.length) {
        selectedDatasetIds.value = preserved
      } else {
        selectedDatasetIds.value = [items[0].id]
      }
    } else {
      selectedDatasetIds.value = []
    }
    fetchProjectArchives({ force: true })
  } catch (err) {
    datasets.value = []
    datasetsError.value = err instanceof Error ? err.message : '无法加载专题数据集'
    selectedDatasetIds.value = []
    lastFetchedProjectName.value = ''
  } finally {
    datasetsLoading.value = false
  }
}

const refreshDatasets = () => {
  const projectName = currentProjectName.value
  if (!projectName) return
  fetchProjectDatasets(projectName, { force: true })
}

const resetArchivesState = () => {
  archivesState.loading = false
  archivesState.error = ''
  archivesState.data = {
    raw: [],
    merge: [],
    clean: []
  }
  archivesState.latest = {
    raw: '',
    merge: '',
    clean: ''
  }
  archivesState.lastProject = ''
  archivesState.lastDataset = ''
  archiveSelection.mergeDate = ''
  archiveSelection.cleanDate = ''
}

const syncArchiveSelection = () => {
  const rawArchives = Array.isArray(archivesState.data.raw) ? archivesState.data.raw : []
  if (!rawArchives.length) {
    // 没有历史 RAW 存档时保留用户手动输入的日期
  } else if (!rawArchives.some((item) => item.date === archiveSelection.mergeDate)) {
    const match = rawArchives.find((item) => item.matches_dataset)
    archiveSelection.mergeDate = (match && match.date) || rawArchives[0]?.date || ''
  }

  const mergeArchives = Array.isArray(archivesState.data.merge) ? archivesState.data.merge : []
  if (!mergeArchives.length) {
    archiveSelection.cleanDate = ''
  } else if (!mergeArchives.some((item) => item.date === archiveSelection.cleanDate)) {
    archiveSelection.cleanDate = mergeArchives[0]?.date || ''
  }
}

const fetchProjectArchives = async ({ force = false } = {}) => {
  const projectName = (currentProjectName.value || '').trim()
  if (!projectName) {
    resetArchivesState()
    return
  }
  const datasetId = (archiveDatasetId.value || '').trim()
  if (
    !force &&
    archivesState.lastProject === projectName &&
    archivesState.lastDataset === datasetId &&
    (archivesState.data.raw.length || archivesState.data.merge.length || archivesState.data.clean.length)
  ) {
    return
  }

  archivesState.loading = true
  archivesState.error = ''
  try {
    const params = new URLSearchParams({ layers: 'raw,merge,clean' })
    if (datasetId) {
      params.append('dataset_id', datasetId)
    }
    const endpoint = await buildApiUrl(`/projects/${encodeURIComponent(projectName)}/archives?${params.toString()}`)
    const response = await fetch(endpoint)
    const result = await response.json()
    if (!response.ok || result.status !== 'ok') {
      throw new Error(result.message || '无法获取存档信息')
    }
    const records = result.archives || {}
    archivesState.data = {
      raw: Array.isArray(records.raw) ? records.raw : [],
      merge: Array.isArray(records.merge) ? records.merge : [],
      clean: Array.isArray(records.clean) ? records.clean : []
    }
    const latest = result.latest || {}
    archivesState.latest = {
      raw: latest.raw || '',
      merge: latest.merge || '',
      clean: latest.clean || ''
    }
    archivesState.lastProject = projectName
    archivesState.lastDataset = datasetId
    syncArchiveSelection()
  } catch (err) {
    archivesState.error = err instanceof Error ? err.message : '无法获取存档信息'
    archivesState.data = {
      raw: [],
      merge: [],
      clean: []
    }
    archivesState.latest = {
      raw: '',
      merge: '',
      clean: ''
    }
    archivesState.lastProject = ''
    archivesState.lastDataset = ''
    archiveSelection.mergeDate = ''
    archiveSelection.cleanDate = ''
  } finally {
    archivesState.loading = false
  }
}

const useMergeDateSuggestion = () => {
  if (mergeDateSuggestion.value) {
    archiveSelection.mergeDate = mergeDateSuggestion.value
  } else if (!archiveSelection.mergeDate) {
    archiveSelection.mergeDate = formatDateKey(new Date())
  }
}

onMounted(() => {
  loadProjects()
})

watch(
  currentProjectName,
  (projectName) => {
    resetDatasetState()
    if (!projectName) return
    fetchProjectDatasets(projectName, { force: true })
  },
  { immediate: true }
)

watch(
  archiveDatasetId,
  () => {
    fetchProjectArchives({ force: true })
  },
  { immediate: false }
)

watch(
  () => mergeDateSuggestion.value,
  (suggestion) => {
    if (!rawArchiveOptions.value.length && suggestion && !archiveSelection.mergeDate) {
      archiveSelection.mergeDate = suggestion
    }
  }
)

const ensureParameters = (stageKey) => {
  const projectName = currentProjectName.value ? currentProjectName.value.trim() : ''
  if (!projectName) {
    parameterError.value = '请先选择项目'
    return false
  }
  if (datasetOptions.value.length && !selectedDatasetIds.value.length) {
    parameterError.value = '请选择需要处理的数据集'
    return false
  }
  if ((stageKey === 'merge' || stageKey === 'pipeline') && !archiveSelection.mergeDate) {
    parameterError.value = '请填写需要 Merge 的处理日期'
    return false
  }
  if (stageKey === 'clean' && !archiveSelection.cleanDate) {
    parameterError.value = '请选择需要 Clean 的 Merge 存档日期'
    return false
  }
  parameterError.value = ''
  return true
}

const resolveOperationDate = (key) => {
  if (key === 'clean') {
    return archiveSelection.cleanDate
  }
  return archiveSelection.mergeDate
}

const runOperation = async (key) => {
  if (!ensureParameters(key)) return
  const operation = operations.find((item) => item.key === key)
  if (!operation) return

  const state = statuses[key]
  state.running = true
  state.message = ''
  state.success = null

  try {
    const projectName = currentProjectName.value ? currentProjectName.value.trim() : ''
    const operationDate = resolveOperationDate(key)
    const datasetBatch = selectedDatasetIds.value.length ? [...selectedDatasetIds.value] : [null]
    const failures = []
    let successCount = 0

    for (const datasetId of datasetBatch) {
      const payload = {
        topic: projectName,
        date: operationDate
      }
      if (projectName) {
        payload.project = projectName
      }
      if (datasetId) {
        payload.dataset_id = datasetId
      }
      const endpoint = await buildApiUrl(operation.path)
      const response = await fetch(endpoint, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(payload)
      })
      const result = await response.json()
      const ok = response.ok && result.status !== 'error'
      if (ok) {
        successCount += 1
      } else {
        failures.push({
          datasetId,
          message: result.message || `${operation.label} 执行失败`
        })
      }
    }

    if (!failures.length) {
      state.success = true
      state.message =
        datasetBatch.length > 1
          ? `${operation.label} 已完成 ${datasetBatch.length} 个数据集`
          : `${operation.label} 执行成功`
      fetchProjectArchives({ force: true })
    } else {
      state.success = false
      const failedNames = failures.map((failure) => describeDataset(failure.datasetId)).join('、')
      const errorReason = failures[0]?.message || `${operation.label} 执行失败`
      state.message =
        successCount > 0
          ? `${operation.label} 已完成 ${successCount}/${datasetBatch.length}，失败：${errorReason}（${failedNames}）`
          : `${operation.label} 执行失败：${errorReason}（${failedNames}）`
    }
  } catch (err) {
    state.success = false
    state.message = err instanceof Error ? err.message : `${operation.label} 执行失败`
  } finally {
    state.running = false
  }
}

const runPipeline = async () => {
  if (!ensureParameters('pipeline')) return
  pipeline.running = true
  pipeline.message = ''
  pipeline.success = null

  try {
    const projectName = currentProjectName.value ? currentProjectName.value.trim() : ''
    const operationDate = archiveSelection.mergeDate
    const datasetBatch = selectedDatasetIds.value.length ? [...selectedDatasetIds.value] : [null]
    const failures = []
    let successCount = 0

    for (const datasetId of datasetBatch) {
      const payload = {
        topic: projectName,
        date: operationDate
      }
      if (projectName) {
        payload.project = projectName
      }
      if (datasetId) {
        payload.dataset_id = datasetId
      }
      const endpoint = await buildApiUrl('/pipeline')
      const response = await fetch(endpoint, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(payload)
      })
      const result = await response.json()
      const ok = response.ok && result.status !== 'error'
      if (ok) {
        successCount += 1
      } else {
        failures.push({
          datasetId,
          message: result.message || 'Pipeline 执行失败'
        })
      }
    }

    if (!failures.length) {
      pipeline.success = true
      pipeline.message =
        datasetBatch.length > 1
          ? `Pipeline 已完成 ${datasetBatch.length} 个数据集`
          : 'Pipeline 执行成功，Merge 与 Clean 均已完成。'
      fetchProjectArchives({ force: true })
    } else {
      pipeline.success = false
      const failedNames = failures.map((failure) => describeDataset(failure.datasetId)).join('、')
      const errorReason = failures[0]?.message || 'Pipeline 执行失败'
      pipeline.message =
        successCount > 0
          ? `Pipeline 已完成 ${successCount}/${datasetBatch.length}，失败：${errorReason}（${failedNames}）`
          : `${errorReason}（${failedNames}）`
    }
  } catch (err) {
    pipeline.success = false
    pipeline.message = err instanceof Error ? err.message : 'Pipeline 执行失败'
  } finally {
    pipeline.running = false
  }
}

// 删除存档相关方法
const confirmDeleteArchive = (layer, date) => {
  deleteArchiveState.deleteConfirm.show = true
  deleteArchiveState.deleteConfirm.layer = layer
  deleteArchiveState.deleteConfirm.date = date
  deleteArchiveState.deleteConfirm.error = ''
}

const closeDeleteConfirm = () => {
  deleteArchiveState.deleteConfirm.show = false
  deleteArchiveState.deleteConfirm.layer = ''
  deleteArchiveState.deleteConfirm.date = ''
  deleteArchiveState.deleteConfirm.error = ''
}

const executeDeleteArchive = async () => {
  if (!currentProjectName.value) {
    deleteArchiveState.deleteConfirm.error = '项目名称未设置'
    return
  }

  const { layer, date } = deleteArchiveState.deleteConfirm
  deleteArchiveState.deleting = true
  deleteArchiveState.deleteConfirm.error = ''

  try {
    const projectName = currentProjectName.value.trim()
    const baseUrl = await ensureApiBase()

    // 构建删除URL
    let url = `${baseUrl}/projects/${encodeURIComponent(projectName)}/archives/${layer}/${date}`

    // 如果选择了数��集，添加dataset_id参数
    if (archiveDatasetId.value) {
      url += `?dataset_id=${encodeURIComponent(archiveDatasetId.value)}`
    }

    const response = await fetch(url, {
      method: 'DELETE',
      headers: {
        'Content-Type': 'application/json'
      }
    })

    const result = await response.json()

    if (response.ok && result.status === 'ok') {
      // 删除成功
      closeDeleteConfirm()

      // 清空相关选择
      if (layer === 'raw' && archiveSelection.mergeDate === date) {
        archiveSelection.mergeDate = ''
      } else if (layer === 'merge' && archiveSelection.cleanDate === date) {
        archiveSelection.cleanDate = ''
      }

      // 刷新存档列表
      await fetchProjectArchives({ force: true })

      // 显示成功消息
      const deletedCount = result.deleted_count || 0
      const deletedSize = result.deleted_size || 0
      const sizeText = deletedSize > 0 ? ` (${formatFileSize(deletedSize)})` : ''

      // 临时显示成功消息
      parameterError.value = `成功删除 ${layer.toUpperCase()} 存档 (${date})，共 ${deletedCount} 个文件${sizeText}`
      setTimeout(() => {
        parameterError.value = ''
      }, 3000)

    } else {
      // 删除失败
      let errorMessage = result.message || `删除 ${layer.toUpperCase()} 存档失败`

      // 处理依赖关系错误
      if (result.dependent_layers && result.dependent_layers.length > 0) {
        const dependencies = result.dependent_layers.map((dep) =>
          `${dep.layer.toUpperCase()}(${dep.date})`
        ).join(', ')
        errorMessage += `。依赖关系：${dependencies}`
      }

      deleteArchiveState.deleteConfirm.error = errorMessage
    }
  } catch (err) {
    const errorMessage = err instanceof Error ? err.message : '删除存档时发生未知错误'
    deleteArchiveState.deleteConfirm.error = errorMessage
  } finally {
    deleteArchiveState.deleting = false
  }
}

const formatFileSize = (bytes) => {
  if (bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(2))} ${sizes[i]}`
}
</script>
