<template>
  <div class="space-y-6">
    <header class="flex flex-wrap items-center justify-between gap-4">
      <div class="space-y-1">
        <h1 class="text-xl font-bold tracking-tight text-primary">数据预处理</h1>
        <p class="text-sm text-secondary">按日期依次执行 Merge 与 Clean，生成标准化分析结果。</p>
      </div>
      <div
        class="inline-flex items-center gap-2 rounded-full bg-brand-50 px-3 py-1 text-xs font-semibold text-brand-700">
        <FunnelIcon class="h-4 w-4" />
        <span>Preprocess</span>
      </div>
    </header>

    <!-- Configuration Section -->
    <section class="card-surface p-8 space-y-8">
      <header class="space-y-1">
        <h2 class="text-lg font-bold text-primary">基础配置</h2>
        <p class="text-xs text-secondary">
          配置当前任务的数据来源与存档日期。
        </p>
      </header>

      <div class="grid gap-8 lg:grid-cols-2">
        <!-- 1. Project & Dataset Selection -->
        <div class="space-y-6">
          <div class="space-y-2">
            <label class="text-xs font-bold text-primary ml-1">选择项目</label>
            <div class="relative">
              <select v-if="projectOptions.length" v-model="selectedProjectName"
                class="w-full appearance-none rounded-2xl border-0 bg-base-soft py-4 pl-4 pr-10 text-sm text-primary transition focus:bg-surface focus:ring-2 focus:ring-brand-500/20 placeholder:text-muted disabled:opacity-60"
                :disabled="projectsLoading">
                <option disabled value="">请选择项目</option>
                <option v-for="option in projectOptions" :key="option.value" :value="option.value">
                  {{ option.label }}
                </option>
              </select>
              <div class="pointer-events-none absolute inset-y-0 right-0 flex items-center pr-4 text-secondary/50">
                <ChevronDownIcon class="w-4 h-4" />
              </div>
            </div>
          </div>

          <div class="space-y-3">
            <div class="flex items-center justify-between">
              <label class="text-xs font-bold text-primary ml-1">选择数据集 <span
                  class="text-[10px] font-normal text-secondary ml-1">(多选)</span></label>
              <button type="button"
                class="text-[10px] font-bold text-brand-600 hover:text-brand-700 disabled:opacity-50 transition-colors"
                :disabled="datasetsLoading" @click="refreshDatasets">
                {{ datasetsLoading ? '正在加载...' : '刷新列表' }}
              </button>
            </div>

            <div v-if="!currentProjectName"
              class="rounded-[1.5rem] border border-dashed border-black/10 bg-brand-50/10 p-10 text-center text-xs text-secondary">
              请先选择项目
            </div>
            <div v-else-if="datasetsLoading"
              class="rounded-[1.5rem] bg-brand-50/20 p-10 text-center text-xs text-secondary animate-pulse">
              正在加载数据集...
            </div>
            <div v-else-if="!datasetOptions.length"
              class="rounded-[1.5rem] bg-brand-50/10 p-10 text-center text-xs text-secondary">
              暂无数据集，请前往“项目数据”页面上传。
            </div>
            <div v-else class="flex flex-wrap gap-2.5 p-1">
              <button v-for="option in datasetOptions" :key="option.id" type="button"
                class="group relative inline-flex items-center gap-2 rounded-xl px-4 py-2 text-xs font-medium transition-all"
                :class="selectedDatasetIds.includes(option.id)
                  ? 'bg-brand-600 text-white'
                  : 'bg-white border border-black/5 text-secondary hover:bg-brand-50 hover:border-brand-100'"
                @click="toggleDatasetSelection(option.id)">
                <span v-if="selectedDatasetIds.includes(option.id)"
                  class="flex h-1.5 w-1.5 rounded-full bg-white"></span>
                <span>{{ option.raw.display_name || option.id }}</span>
              </button>
            </div>
            <p v-if="datasetsError" class="text-xs text-rose-600 font-medium pl-1">{{ datasetsError }}</p>
          </div>
        </div>

        <!-- 2. Date Selection -->
        <div class="space-y-6">
          <div class="space-y-3">
            <label class="text-xs font-bold text-primary ml-1">Merge 存档日期</label>
            <div class="space-y-3">
              <input v-model="archiveSelection.mergeDate" type="text" inputmode="numeric"
                class="w-full rounded-2xl border-0 bg-base-soft px-4 py-4 text-sm text-primary transition focus:bg-surface focus:ring-2 focus:ring-brand-500/20 placeholder:text-muted"
                placeholder="例如 20251202" />

              <div v-if="rawArchiveOptions.length" class="space-y-2">
                <p class="text-[10px] font-bold uppercase tracking-wider text-muted ml-1 flex items-center gap-1.5">
                  <ClockIcon class="h-3 w-3" /> 历史存档快速选择
                </p>
                <div class="flex flex-wrap gap-2">
                  <button v-for="option in rawArchiveOptions.slice(0, 5)" :key="option.value" type="button"
                    class="group inline-flex items-center rounded-lg border border-transparent px-3 py-1.5 text-[11px] font-bold transition-all"
                    :class="archiveSelection.mergeDate === option.value
                      ? 'bg-brand-100 text-brand-700 border-brand-200'
                      : 'bg-white border-black/5 text-secondary hover:bg-brand-50'"
                    @click="archiveSelection.mergeDate = option.value">
                    {{ option.value }}
                  </button>
                </div>
              </div>
              <div v-else-if="mergeDateSuggestion" class="flex items-center gap-3 pl-1">
                <span class="text-xs text-secondary">建议日期:</span>
                <button type="button"
                  class="rounded-full bg-brand-50 border border-brand-100 px-3 py-1 text-xs font-bold text-brand-600 hover:bg-brand-100 transition-colors"
                  @click="useMergeDateSuggestion">
                  {{ mergeDateSuggestion }}
                </button>
              </div>
            </div>
          </div>

          <div class="space-y-3">
            <label class="text-xs font-bold text-primary ml-1">Clean 存档来源</label>
            <div class="relative w-full">
              <select v-if="mergeArchiveOptions.length" v-model="archiveSelection.cleanDate"
                class="w-full appearance-none rounded-2xl border-0 bg-base-soft py-4 pl-4 pr-10 text-sm text-primary transition focus:bg-surface focus:ring-2 focus:ring-brand-500/20 disabled:opacity-60">
                <option disabled value="">请选择 Merge 存档</option>
                <option v-for="option in mergeArchiveOptions" :key="option.value" :value="option.value">
                  {{ option.label }}
                </option>
              </select>
              <div v-else
                class="flex w-full items-center justify-center rounded-2xl bg-brand-50/20 py-4 px-4 text-xs text-secondary italic">
                {{ archivesState.loading ? '正在同步存档...' : '需执行 Merge 后方可见有效存档' }}
              </div>

              <div v-if="mergeArchiveOptions.length"
                class="pointer-events-none absolute inset-y-0 right-0 flex items-center pr-4 text-secondary/50">
                <ChevronDownIcon class="h-4 w-4" />
              </div>
            </div>
            <p class="text-[10px] text-muted pl-1 opacity-70">系统通常会自动关联最新的 Merge 结果参与清洗。</p>
          </div>
        </div>
      </div>

      <transition name="fade">
        <div v-if="parameterError"
          class="rounded-xl bg-rose-50 border border-rose-100 px-5 py-3 text-xs font-bold text-rose-600 flex items-center gap-3">
          <ExclamationCircleIcon class="h-4 w-4" />
          {{ parameterError }}
        </div>
      </transition>
    </section>

    <!-- Archive Management -->
    <section class="mute-card-surface p-8 space-y-6">
      <header class="flex flex-wrap items-center justify-between gap-4">
        <div class="flex items-center gap-4">
          <div
            class="flex h-12 w-12 items-center justify-center rounded-[1.25rem] bg-white text-brand-600 ring-1 ring-black/5">
            <ArchiveBoxIcon class="h-6 w-6" />
          </div>
          <div>
            <h2 class="text-lg font-bold text-primary">存档管理</h2>
            <p class="text-xs text-secondary">溯源历史生成的各阶段处理快照。</p>
          </div>
        </div>
        <button type="button"
          class="group flex items-center gap-2 rounded-full bg-white px-5 py-2 text-xs font-bold text-secondary transition hover:bg-white hover:text-brand-600 border border-black/5 active:scale-95"
          :disabled="archivesState.loading" @click="fetchProjectArchives({ force: true })">
          <ArrowPathIcon class="h-4 w-4 transition-transform group-hover:rotate-180"
            :class="{ 'animate-spin': archivesState.loading }" />
          <span>刷新数据</span>
        </button>
      </header>

      <div class="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <!-- RAW Archive List -->
        <article
          class="flex flex-col rounded-3xl bg-white p-3 border border-black/5 hover:border-brand-100 transition-colors group">
          <header class="flex items-center justify-between px-3 py-3 border-b border-black/5 mb-3">
            <div class="flex items-center gap-2">
              <div class="w-1.5 h-4 bg-blue-500 rounded-full"></div>
              <span class="text-xs font-bold text-secondary tracking-widest uppercase">Raw Items</span>
            </div>
            <span class="rounded-full bg-blue-50 px-2.5 py-0.5 text-[10px] font-bold text-blue-600">{{
              archivesState.data.raw.length || 0 }}</span>
          </header>

          <div class="flex-1 overflow-hidden">
            <div v-if="!archivesState.data.raw.length"
              class="flex flex-col items-center justify-center py-16 text-muted opacity-40">
              <InboxIcon class="mb-3 h-10 w-10" />
              <span class="text-xs font-bold">暂无原始存档</span>
            </div>
            <ul v-else class="max-h-[220px] space-y-2 overflow-y-auto pr-1 sidebar-scroll">
              <li v-for="archive in archivesState.data.raw" :key="archive.date"
                class="group/item relative flex cursor-pointer flex-col gap-1 rounded-2xl p-4 transition-all"
                :class="archiveSelection.mergeDate === archive.date ? 'bg-blue-50 ring-1 ring-blue-100' : 'hover:bg-brand-50/30'"
                @click="archiveSelection.mergeDate = archive.date">
                <div class="flex items-center justify-between">
                  <div class="flex items-center gap-2">
                    <span class="font-mono text-[13px] font-bold"
                      :class="archiveSelection.mergeDate === archive.date ? 'text-blue-700' : 'text-primary'">{{
                        archive.date }}</span>
                  </div>
                  <span v-if="archive.matches_dataset"
                    class="rounded-md bg-emerald-500 px-2 py-0.5 text-[10px] font-bold text-white">ACTIVE</span>
                </div>
                <div class="flex items-center gap-3 text-[11px] font-bold opacity-60">
                  <span class="text-primary">{{ archive.file_count || 0 }} Files</span>
                  <span class="text-secondary">{{ archive.updated_at?.slice(5, 10).replace('-', '/') }} Update</span>
                </div>
                <button type="button"
                  class="absolute right-3 top-4 rounded-xl bg-white/80 p-1.5 text-muted opacity-0 transition-all hover:bg-rose-50 hover:text-rose-600 group-hover/item:opacity-100"
                  @click.stop="confirmDeleteArchive('raw', archive.date)">
                  <TrashIcon class="h-4 w-4" />
                </button>
              </li>
            </ul>
          </div>
        </article>

        <!-- MERGE Archive List -->
        <article
          class="flex flex-col rounded-3xl bg-white p-3 border border-black/5 hover:border-purple-100 transition-colors">
          <header class="flex items-center justify-between px-3 py-3 border-b border-black/5 mb-3">
            <div class="flex items-center gap-2">
              <div class="w-1.5 h-4 bg-purple-500 rounded-full"></div>
              <span class="text-xs font-bold text-secondary tracking-widest uppercase">Merge Res</span>
            </div>
            <span class="rounded-full bg-purple-50 px-2.5 py-0.5 text-[10px] font-bold text-purple-600">{{
              archivesState.data.merge.length || 0 }}</span>
          </header>

          <div class="flex-1 overflow-hidden">
            <div v-if="!archivesState.data.merge.length"
              class="flex flex-col items-center justify-center py-16 text-muted opacity-40">
              <InboxIcon class="mb-3 h-10 w-10" />
              <span class="text-xs font-bold">暂无合并存档</span>
            </div>
            <ul v-else class="max-h-[220px] space-y-2 overflow-y-auto pr-1 sidebar-scroll">
              <li v-for="archive in archivesState.data.merge" :key="archive.date"
                class="group/item relative flex cursor-pointer flex-col gap-1 rounded-2xl p-4 transition-all"
                :class="archiveSelection.cleanDate === archive.date ? 'bg-purple-50 ring-1 ring-purple-100' : 'hover:bg-purple-50/20'"
                @click="archiveSelection.cleanDate = archive.date">
                <div class="flex items-center justify-between">
                  <span class="font-mono text-[13px] font-bold"
                    :class="archiveSelection.cleanDate === archive.date ? 'text-purple-700' : 'text-primary'">{{
                      archive.date }}</span>
                </div>
                <div class="flex items-center gap-3 text-[11px] font-bold opacity-60">
                  <span class="text-primary">{{ archive.channels?.length || 0 }} Chans</span>
                  <span class="text-secondary">{{ archive.updated_at?.slice(5, 10).replace('-', '/') }} Update</span>
                </div>
                <button type="button"
                  class="absolute right-3 top-4 rounded-xl bg-white/80 p-1.5 text-muted opacity-0 transition-all hover:bg-rose-50 hover:text-rose-600 group-hover/item:opacity-100"
                  @click.stop="confirmDeleteArchive('merge', archive.date)">
                  <TrashIcon class="h-4 w-4" />
                </button>
              </li>
            </ul>
          </div>
        </article>

        <!-- CLEAN Archive List -->
        <article
          class="flex flex-col rounded-3xl bg-white p-3 border border-black/5 hover:border-emerald-100 transition-colors">
          <header class="flex items-center justify-between px-3 py-3 border-b border-black/5 mb-3">
            <div class="flex items-center gap-2">
              <div class="w-1.5 h-4 bg-emerald-500 rounded-full"></div>
              <span class="text-xs font-bold text-secondary tracking-widest uppercase">Clean Data</span>
            </div>
            <span class="rounded-full bg-emerald-50 px-2.5 py-0.5 text-[10px] font-bold text-emerald-600">{{
              archivesState.data.clean.length || 0 }}</span>
          </header>

          <div class="flex-1 overflow-hidden">
            <div v-if="!archivesState.data.clean.length"
              class="flex flex-col items-center justify-center py-16 text-muted opacity-40">
              <InboxIcon class="mb-3 h-10 w-10" />
              <span class="text-xs font-bold">暂无清洗完成数据</span>
            </div>
            <ul v-else class="max-h-[220px] space-y-2 overflow-y-auto pr-1 sidebar-scroll">
              <li v-for="archive in archivesState.data.clean" :key="`clean-${archive.date}`"
                class="group/item relative flex flex-col gap-1 rounded-2xl p-4 transition-all hover:bg-brand-50/20">
                <div class="flex items-center justify-between">
                  <span class="font-mono text-[13px] font-bold text-primary">{{ archive.date }}</span>
                </div>
                <div class="flex items-center gap-3 text-[11px] font-bold opacity-60">
                  <span class="text-primary">{{ archive.channels?.length || 0 }} Chans</span>
                  <span class="text-secondary">{{ archive.updated_at?.slice(5, 10).replace('-', '/') }} Update</span>
                </div>
                <button type="button"
                  class="absolute right-3 top-4 rounded-xl bg-white/80 p-1.5 text-muted opacity-0 transition-all hover:bg-rose-50 hover:text-rose-600 group-hover/item:opacity-100"
                  @click.stop="confirmDeleteArchive('clean', archive.date)">
                  <TrashIcon class="h-4 w-4" />
                </button>
              </li>
            </ul>
          </div>
        </article>
      </div>
    </section>

    <!-- Pipeline Execution -->
    <section class="card-surface p-8 space-y-8">
      <div class="flex flex-wrap items-center justify-between gap-6">
        <div class="space-y-1">
          <h2 class="text-lg font-bold text-primary">数据预处理</h2>
          <p class="text-xs text-secondary">执行合并与清洗流程，生成标准化数据集。</p>
        </div>
        <button type="button"
          class="group relative inline-flex items-center gap-3 rounded-full bg-brand-600 px-10 py-4 text-sm font-bold text-white transition-all hover:bg-brand-700 active:scale-95 disabled:cursor-not-allowed disabled:opacity-60 overflow-hidden"
          :disabled="pipeline.running" @click="runPipeline">
          <div v-if="pipeline.running" class="absolute inset-0 bg-brand-500 animate-pulse"></div>
          <SparklesIcon class="h-5 w-5 relative z-10" />
          <span class="relative z-10">{{ pipeline.running ? '预处理执行中...' : '一键执行预处理' }}</span>
        </button>
      </div>

      <!-- Pipeline Message Widget -->
      <transition name="fade">
        <div v-if="pipeline.message" class="rounded-[1.25rem] p-6 border flex items-center gap-4 transition-all" :class="[
          pipeline.success === true ? 'bg-emerald-50 border-emerald-100 text-emerald-800' :
            pipeline.success === false ? 'bg-rose-50 border-rose-100 text-rose-800' : 'bg-brand-50/50 border-brand-100/50 text-brand-800'
        ]">
          <div class="flex h-10 w-10 items-center justify-center rounded-full bg-white ring-1 ring-black/5">
            <component
              :is="pipeline.success ? CheckIcon : pipeline.success === false ? ExclamationCircleIcon : ArrowPathRoundedSquareIcon"
              class="h-5 w-5" :class="{ 'animate-spin opacity-50': pipeline.running && !pipeline.success }" />
          </div>
          <span class="text-xs font-bold leading-relaxed">{{ pipeline.message }}</span>
        </div>
      </transition>

      <div class="grid grid-cols-1 gap-6 md:grid-cols-2">
        <div v-for="(operation, index) in operations" :key="operation.key"
          class="relative flex flex-col justify-between rounded-[2rem] p-6 transition-all border border-black/5"
          :class="operation.key === 'merge' ? 'bg-brand-50/10 hover:border-brand-200' : 'bg-accent-50/10 hover:border-accent-200'">
          <div class="space-y-6">
            <header class="flex items-center justify-between">
              <div class="flex items-center gap-4">
                <div class="flex h-12 w-12 items-center justify-center rounded-[1.25rem] bg-white border border-black/5"
                  :class="operation.key === 'merge' ? 'text-brand-600' : 'text-accent-600'">
                  <component :is="operation.icon" class="h-6 w-6" />
                </div>
                <div>
                  <span class="text-[10px] font-bold tracking-[0.2em] opacity-30 uppercase block leading-none mb-1">{{
                    operation.subtitle }}</span>
                  <h3 class="text-lg font-bold text-primary leading-none">{{ operation.title }}</h3>
                </div>
              </div>
              <transition name="fade">
                <div v-if="statuses[operation.key].message"
                  class="rounded-full bg-white px-3 py-1 text-[10px] font-bold border border-black/5"
                  :class="statuses[operation.key].success ? 'text-emerald-600 border-emerald-100' : 'text-rose-600 border-rose-100'">
                  {{ statuses[operation.key].message }}
                </div>
              </transition>
            </header>

            <p class="text-[13px] text-secondary leading-relaxed font-medium">{{ operation.description }}</p>
          </div>

          <div class="mt-8">
            <button type="button"
              class="flex w-full items-center justify-center gap-2.5 rounded-[1.25rem] bg-white border border-black/5 py-3 text-xs font-bold transition-all hover:bg-brand-50 active:scale-95 disabled:opacity-50"
              :class="operation.key === 'merge' ? 'text-brand-700' : 'text-accent-700'"
              :disabled="statuses[operation.key].running" @click="runOperation(operation.key)">
              <component
                :is="operation.key === 'merge' && statuses[operation.key].running ? ArrowPathIcon : operation.icon"
                class="h-4 w-4"
                :class="{ 'animate-spin': statuses[operation.key].running && operation.key === 'merge' }" />
              <span>{{ statuses[operation.key].running ? '正在处理...' : `独立启动 ${operation.label}` }}</span>
            </button>
          </div>
        </div>
      </div>
    </section>

    <!-- Delete Confirmation -->
    <div v-if="deleteArchiveState.deleteConfirm.show"
      class="fixed inset-0 z-50 flex items-center justify-center bg-black/20 backdrop-blur-sm p-4"
      @click.self="closeDeleteConfirm">
      <div class="w-full max-w-sm rounded-[2.5rem] bg-white p-8 space-y-6">
        <div class="space-y-4 text-center">
          <div class="mx-auto flex h-16 w-16 items-center justify-center rounded-[1.5rem] bg-rose-50 text-rose-500">
            <TrashIcon class="h-8 w-8" />
          </div>
          <div class="space-y-2">
            <h3 class="text-lg font-bold text-primary">彻底清理存档?</h3>
            <p class="text-xs text-secondary font-medium leading-relaxed">
              您正在从系统中永久移除 <span class="text-rose-600 font-bold">{{ deleteArchiveState.deleteConfirm.layer.toUpperCase()
                }}</span> 存档
              <br>
              <span class="font-mono bg-surface-muted px-2 py-1 rounded-md text-[13px] mt-1 inline-block">{{
                deleteArchiveState.deleteConfirm.date }}</span>
            </p>
          </div>
          <div class="rounded-2xl bg-rose-50/50 p-4 text-[11px] font-bold text-rose-700 border border-rose-100/50">
            这是一次破坏性操作，对应的物理文件与数据库引用都将被抹除。
          </div>
        </div>

        <div class="grid grid-cols-2 gap-3">
          <button type="button"
            class="rounded-full bg-surface-muted py-4 text-sm font-bold text-secondary transition hover:bg-gray-200 active:scale-95"
            :disabled="deleteArchiveState.deleting" @click="closeDeleteConfirm">
            返回
          </button>
          <button type="button"
            class="rounded-full bg-rose-600 py-4 text-sm font-bold text-white transition hover:bg-rose-700 active:scale-95"
            :disabled="deleteArchiveState.deleting" @click="executeDeleteArchive">
            {{ deleteArchiveState.deleting ? '清理中' : '执行删除' }}
          </button>
        </div>
        <p v-if="deleteArchiveState.deleteConfirm.error" class="text-center text-[11px] text-rose-600 font-bold">
          {{ deleteArchiveState.deleteConfirm.error }}
        </p>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useApiBase } from '../../composables/useApiBase'
import {
  FunnelIcon,
  ArrowPathIcon,
  ArchiveBoxIcon,
  DocumentDuplicateIcon,
  QueueListIcon,
  SparklesIcon,
  TrashIcon,
  ExclamationCircleIcon,
  CheckIcon,
  InboxIcon,
  ArrowPathRoundedSquareIcon,
  ChevronDownIcon,
  ClockIcon
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
    title: '合并整合 Merge',
    subtitle: 'Step 01',
    description: '整合多份原始 Excel，统一字段标准，生成完整主题数据集。',
    path: '/merge',
    icon: ArrowPathRoundedSquareIcon
  },
  {
    key: 'clean',
    label: 'Clean',
    title: '数据清洗 Clean',
    subtitle: 'Step 02',
    description: '补齐元数据，标准化字段格式，剔除重复与空值项。',
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
      if (channelCount) parts.push(`${channelCount} 渠道`)
      return {
        value: date,
        label: parts.join(' · ')
      }
    })
    .filter(Boolean)
})

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

const toggleDatasetSelection = (id) => {
  const index = selectedDatasetIds.value.indexOf(id)
  if (index === -1) {
    selectedDatasetIds.value.push(id)
  } else {
    selectedDatasetIds.value.splice(index, 1)
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
  archivesState.data = { raw: [], merge: [], clean: [] }
  archivesState.latest = { raw: '', merge: '', clean: '' }
  archivesState.lastProject = ''
  archivesState.lastDataset = ''
  archiveSelection.mergeDate = ''
  archiveSelection.cleanDate = ''
}

const syncArchiveSelection = () => {
  const rawArchives = Array.isArray(archivesState.data.raw) ? archivesState.data.raw : []
  if (!rawArchives.length) {
    // skip
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
      throw new Error(result.message || '无法加载存档列表')
    }
    const { data } = result
    archivesState.data = {
      raw: Array.isArray(data.raw) ? data.raw : [],
      merge: Array.isArray(data.merge) ? data.merge : [],
      clean: Array.isArray(data.clean) ? data.clean : []
    }
    archivesState.latest = {
      raw: data.latest?.raw || '',
      merge: data.latest?.merge || '',
      clean: data.latest?.clean || ''
    }
    archivesState.lastProject = projectName
    archivesState.lastDataset = datasetId
    syncArchiveSelection()
  } catch (err) {
    archivesState.error = err instanceof Error ? err.message : '无法加载存档列表'
    archivesState.data = { raw: [], merge: [], clean: [] }
    archivesState.latest = { raw: '', merge: '', clean: '' }
  } finally {
    archivesState.loading = false
  }
}

const runOperation = async (operationKey) => {
  if (statuses[operationKey].running || pipeline.running) return
  if (!currentProjectName.value) {
    parameterError.value = '请先选择项目'
    return
  }
  if (!archiveSelection.mergeDate) {
    parameterError.value = '请指定 Merge 存档日期'
    return
  }
  parameterError.value = ''

  statuses[operationKey].running = true
  statuses[operationKey].success = null
  statuses[operationKey].message = ''

  const operation = operations.find((op) => op.key === operationKey)
  if (!operation) return

  try {
    const payload = {
      project_name: currentProjectName.value,
      merge_date: archiveSelection.mergeDate,
      clean_date: archiveSelection.cleanDate || undefined,
      dataset_ids: selectedDatasetIds.value
    }

    const endpoint = await buildApiUrl(operation.path)
    const response = await fetch(endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    })
    const result = await response.json()
    const ok = response.ok && result.status === 'ok'

    statuses[operationKey].success = ok
    statuses[operationKey].message = ok ? '任务已下达' : result.message || '操作失败'
    if (ok) {
      fetchProjectArchives({ force: true })
    }
  } catch (err) {
    statuses[operationKey].success = false
    statuses[operationKey].message = err instanceof Error ? err.message : '网络请求失败'
  } finally {
    statuses[operationKey].running = false
  }
}

const runPipeline = async () => {
  if (pipeline.running) return
  if (!currentProjectName.value) {
    parameterError.value = '请先选择项目'
    return
  }
  if (!archiveSelection.mergeDate) {
    parameterError.value = '请指定 Merge 存档日期'
    return
  }
  parameterError.value = ''
  pipeline.running = true
  pipeline.success = null
  pipeline.message = '数据工厂管道初始化中...'

  for (const opKey of Object.keys(statuses)) {
    statuses[opKey].running = false
    statuses[opKey].success = null
    statuses[opKey].message = ''
  }

  try {
    pipeline.message = '正在执行合并 (Merge) 步骤...'
    statuses.merge.running = true
    await runOperation('merge')
    if (!statuses.merge.success) {
      throw new Error(`Merge 失败: ${statuses.merge.message}`)
    }

    await new Promise(r => setTimeout(r, 1000))

    pipeline.message = '正在执行清洗 (Clean) 步骤...'
    statuses.clean.running = true
    await runOperation('clean')
    if (!statuses.clean.success) {
      throw new Error(`Clean 失败: ${statuses.clean.message}`)
    }

    pipeline.success = true
    pipeline.message = '预处理全链路执行完毕'
  } catch (err) {
    pipeline.success = false
    pipeline.message = err instanceof Error ? err.message : '执行过程发生未知中断'
  } finally {
    pipeline.running = false
    statuses.merge.running = false
    statuses.clean.running = false
  }
}

const useMergeDateSuggestion = () => {
  if (mergeDateSuggestion.value) {
    archiveSelection.mergeDate = mergeDateSuggestion.value
  }
}

const confirmDeleteArchive = (layer, date) => {
  if (!layer || !date) return
  deleteArchiveState.deleteConfirm = {
    show: true,
    layer,
    date,
    error: ''
  }
}

const closeDeleteConfirm = () => {
  deleteArchiveState.deleteConfirm = { show: false, layer: '', date: '', error: '' }
}

const executeDeleteArchive = async () => {
  const { layer, date } = deleteArchiveState.deleteConfirm
  const projectName = currentProjectName.value
  if (!layer || !date || !projectName) return

  deleteArchiveState.deleting = true
  deleteArchiveState.deleteConfirm.error = ''

  try {
    const endpoint = await buildApiUrl(`/archives/${encodeURIComponent(projectName)}/${layer}/${date}`)
    const response = await fetch(endpoint, {
      method: 'DELETE'
    })
    const result = await response.json()
    if (!response.ok || result.status !== 'ok') {
      throw new Error(result.message || '删除请求被拒绝')
    }
    closeDeleteConfirm()
    fetchProjectArchives({ force: true })
  } catch (err) {
    deleteArchiveState.deleteConfirm.error = err instanceof Error ? err.message : '连接异常'
  } finally {
    deleteArchiveState.deleting = false
  }
}

onMounted(() => {
  loadProjects()
})

watch(selectedProjectName, (newVal) => {
  if (newVal) {
    fetchProjectDatasets(newVal)
  } else {
    resetDatasetState()
  }
})
</script>

<style scoped>
.sidebar-scroll::-webkit-scrollbar {
  width: 4px;
}

.sidebar-scroll::-webkit-scrollbar-track {
  background: transparent;
}

.sidebar-scroll::-webkit-scrollbar-thumb {
  background: rgba(0, 0, 0, 0.05);
  border-radius: 10px;
}

.sidebar-scroll::-webkit-scrollbar-thumb:hover {
  background: rgba(0, 0, 0, 0.1);
}

.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.3s ease, transform 0.3s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
  transform: translateY(-5px);
}
</style>
