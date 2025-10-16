<template>
  <div class="space-y-10">
    <section class="relative overflow-hidden rounded-3xl bg-gradient-to-br from-indigo-500 via-indigo-400 to-sky-400 px-6 py-10 text-white shadow-2xl sm:px-10">
      <div class="absolute inset-0 opacity-50 mix-blend-screen">
        <div class="absolute -right-28 -top-24 h-72 w-72 rounded-full bg-white/20 blur-3xl"></div>
        <div class="absolute bottom-0 left-1/3 h-56 w-56 rounded-full bg-sky-200/30 blur-3xl"></div>
      </div>
      <div class="relative flex flex-col gap-8 lg:flex-row lg:items-center lg:justify-between">
        <div class="space-y-4">
          <p class="text-sm font-semibold uppercase tracking-[0.4em] text-white/60">项目工作台</p>
          <h1 class="text-3xl font-semibold sm:text-4xl">Opinion System 控制中心</h1>
          <p class="text-lg text-indigo-100/90">在此编辑和开始新项目</p>
        </div>
        <button
          type="button"
          class="inline-flex items-center gap-2 rounded-full bg-white/90 px-6 py-3 text-indigo-600 shadow-lg transition hover:-translate-y-0.5 hover:bg-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-white"
          @click="startNewProject"
        >
          <span class="flex h-9 w-9 items-center justify-center rounded-full bg-indigo-100 text-indigo-600">
            <PlusIcon class="h-5 w-5" />
          </span>
          <span class="text-base font-semibold">新建项目</span>
        </button>
      </div>

      <div class="relative mt-8 rounded-3xl bg-white/10 p-6 backdrop-blur">
        <div v-if="activeProject" class="space-y-6">
          <div class="flex flex-col gap-6 lg:flex-row lg:items-center lg:justify-between">
            <div>
              <p class="text-sm uppercase tracking-[0.3em] text-white/70">当前项目</p>
              <h2 class="mt-2 text-2xl font-semibold">{{ activeProject.name }}</h2>
            </div>
            <div class="flex flex-wrap gap-3">
              <button
                type="button"
                class="inline-flex items-center gap-2 rounded-full bg-white/20 px-4 py-2 text-sm font-semibold text-white transition hover:bg-white/30 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-white"
                @click="startViewProject(activeProject.name)"
              >
                <EyeIcon class="h-4 w-4" />
                查看
              </button>
              <button
                type="button"
                class="inline-flex items-center gap-2 rounded-full bg-white px-4 py-2 text-sm font-semibold text-indigo-600 shadow hover:bg-white/90 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-white"
                @click="startEditProject(activeProject.name)"
              >
                <PencilSquareIcon class="h-4 w-4" />
                编辑
              </button>
            </div>
          </div>
          <dl class="grid gap-4 sm:grid-cols-3">
            <div class="rounded-2xl bg-white/10 px-4 py-3">
              <dt class="text-xs uppercase tracking-widest text-white/60">状态</dt>
              <dd class="mt-2 text-lg font-semibold">{{ statusLabel(activeProject.status) }}</dd>
            </div>
            <div class="rounded-2xl bg-white/10 px-4 py-3">
              <dt class="text-xs uppercase tracking-widest text-white/60">最近更新</dt>
              <dd class="mt-2 text-lg font-semibold">{{ formatTimestamp(activeProject.updated_at) }}</dd>
            </div>
            <div class="rounded-2xl bg-white/10 px-4 py-3">
              <dt class="text-xs uppercase tracking-widest text-white/60">执行记录</dt>
              <dd class="mt-2 text-lg font-semibold">
                {{ activeProject.operations?.length ? `${activeProject.operations.length} 条` : '暂无' }}
              </dd>
            </div>
          </dl>
        </div>
        <div v-else class="flex flex-col items-center gap-4 text-center text-white/90">
          <div class="flex h-14 w-14 items-center justify-center rounded-full bg-white/10 text-3xl">📊</div>
          <h2 class="text-2xl font-semibold">暂未选择项目</h2>
          <p class="text-base">从下方列表选择一个项目，或点击右上角按钮快速创建。</p>
        </div>
      </div>
    </section>

    <div class="grid gap-8 xl:grid-cols-[340px,minmax(0,1fr)]">
      <aside class="card-surface flex flex-col gap-6 p-6">
        <header class="flex items-start justify-between gap-4">
          <div>
            <h3 class="text-lg font-semibold text-slate-900">项目列表</h3>
            <p class="text-sm text-slate-500">浏览所有项目并快速切换。</p>
          </div>
          <button
            type="button"
            :disabled="isRefreshing"
            :class="[
              'inline-flex h-10 w-10 items-center justify-center rounded-full border border-slate-200 text-slate-500 transition hover:-translate-y-0.5 hover:text-indigo-600 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand',
              isRefreshing ? 'animate-spin border-slate-300 text-indigo-400' : ''
            ]"
            @click.stop="refreshProjects"
            aria-label="刷新项目"
          >
            <ArrowPathIcon class="h-5 w-5" aria-hidden="true" />
          </button>
        </header>

        <div v-if="projects.length" class="grid gap-4 rounded-2xl bg-slate-50/80 p-4 sm:grid-cols-2">
          <div class="flex flex-col gap-1 rounded-xl bg-white p-3 shadow-sm">
            <span class="text-xs font-medium uppercase tracking-widest text-slate-400">项目总数</span>
            <strong class="text-2xl font-semibold text-slate-900">{{ totalProjects }}</strong>
          </div>
          <div class="flex flex-col gap-1 rounded-xl bg-white p-3 shadow-sm">
            <span class="text-xs font-medium uppercase tracking-widest text-slate-400">进行中</span>
            <strong class="text-2xl font-semibold text-slate-900">{{ activeProjectsCount }}</strong>
          </div>
          <div class="flex flex-col gap-1 rounded-xl bg-white p-3 shadow-sm">
            <span class="text-xs font-medium uppercase tracking-widest text-slate-400">已完成</span>
            <strong class="text-2xl font-semibold text-slate-900">{{ completedProjects }}</strong>
          </div>
          <div class="flex flex-col gap-1 rounded-xl bg-white p-3 shadow-sm">
            <span class="text-xs font-medium uppercase tracking-widest text-slate-400">失败</span>
            <strong class="text-2xl font-semibold text-slate-900">{{ failedProjects }}</strong>
          </div>
        </div>

        <ul class="space-y-3">
          <li
            v-for="project in projects"
            :key="project.name"
            :class="[
              'rounded-2xl border border-transparent bg-slate-50/80 transition hover:-translate-y-0.5 hover:border-indigo-100 hover:bg-white',
              project.name === selectedProjectName ? 'border-indigo-200 bg-white shadow-md' : ''
            ]"
          >
            <div class="flex items-center justify-between gap-3 p-4">
              <button
                type="button"
                class="flex flex-1 items-center gap-3 text-left"
                @click="openProject(project.name)"
              >
                <span class="flex h-12 w-12 items-center justify-center rounded-2xl bg-indigo-500/10 text-lg font-semibold text-indigo-600">
                  {{ project.name.slice(0, 1).toUpperCase() }}
                </span>
                <div class="flex flex-1 flex-col">
                  <span class="text-base font-semibold text-slate-900">{{ project.name }}</span>
                  <span class="text-sm text-slate-500">更新：{{ formatTimestamp(project.updated_at) }}</span>
                </div>
              </button>
              <div class="flex items-center gap-3">
                <span
                  class="badge-soft"
                  :class="{
                    'bg-emerald-100 text-emerald-600': project.status === 'success',
                    'bg-rose-100 text-rose-600': project.status === 'error',
                    'bg-amber-100 text-amber-600': project.status !== 'success' && project.status !== 'error'
                  }"
                >
                  {{ statusLabel(project.status) }}
                </span>
                <div class="relative">
                  <button
                    type="button"
                    class="flex h-9 w-9 items-center justify-center rounded-full text-slate-400 transition hover:bg-slate-100 hover:text-indigo-600 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand"
                    :aria-expanded="openActionMenu === project.name"
                    @click.stop="toggleProjectMenu(project.name)"
                    title="更多操作"
                  >
                    <EllipsisHorizontalIcon class="h-5 w-5" aria-hidden="true" />
                  </button>
                  <transition
                    enter-active-class="transition transform ease-out duration-150"
                    enter-from-class="opacity-0 translate-y-1"
                    enter-to-class="opacity-100 translate-y-0"
                    leave-active-class="transition transform ease-in duration-100"
                    leave-from-class="opacity-100 translate-y-0"
                    leave-to-class="opacity-0 translate-y-1"
                  >
                    <ul
                      v-if="openActionMenu === project.name"
                      class="absolute right-0 z-20 mt-2 w-40 overflow-hidden rounded-xl border border-slate-200 bg-white py-1 text-sm shadow-xl"
                      role="menu"
                      @click.stop
                    >
                      <li>
                        <button class="flex w-full items-center gap-2 px-4 py-2 text-left hover:bg-indigo-50" type="button" role="menuitem" @click="handleMenuView(project.name)">
                          查看项目
                        </button>
                      </li>
                      <li>
                        <button class="flex w-full items-center gap-2 px-4 py-2 text-left hover:bg-indigo-50" type="button" role="menuitem" @click="handleMenuEdit(project.name)">
                          编辑项目
                        </button>
                      </li>
                      <li>
                        <button
                          class="flex w-full items-center gap-2 px-4 py-2 text-left text-rose-600 hover:bg-rose-50"
                          type="button"
                          role="menuitem"
                          @click="handleMenuDelete(project.name)"
                          :disabled="isDeleting"
                        >
                          删除项目
                        </button>
                      </li>
                    </ul>
                  </transition>
                </div>
              </div>
            </div>
          </li>
        </ul>
        <p v-if="!projects.length && !loading" class="rounded-2xl bg-slate-100 px-4 py-3 text-sm text-slate-500">暂无项目记录，点击右上角按钮开始创建吧。</p>
        <p v-if="loading" class="rounded-2xl bg-slate-100 px-4 py-3 text-sm text-slate-500">加载中…</p>
        <p v-if="error" class="rounded-2xl bg-rose-100 px-4 py-3 text-sm text-rose-600">{{ error }}</p>
      </aside>

      <main class="space-y-6">
        <section v-if="activeProject" class="card-surface space-y-6 p-6">
          <header class="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
            <div>
              <h3 class="text-xl font-semibold text-slate-900">{{ activeProject.name }}</h3>
              <p class="text-sm text-slate-500">最近更新：{{ formatTimestamp(activeProject.updated_at) }}</p>
            </div>
            <div class="flex flex-wrap gap-3">
              <button
                type="button"
                class="inline-flex items-center gap-2 rounded-full border border-slate-200 px-4 py-2 text-sm font-medium text-slate-600 transition hover:border-indigo-200 hover:text-indigo-600"
                @click="startViewProject(activeProject.name)"
              >
                查看详情
              </button>
              <button
                type="button"
                class="inline-flex items-center gap-2 rounded-full bg-indigo-600 px-4 py-2 text-sm font-semibold text-white shadow hover:bg-indigo-500"
                @click="startEditProject(activeProject.name)"
              >
                编辑项目
              </button>
            </div>
          </header>
          <div class="space-y-6">
            <p v-if="activeProject.description" class="rounded-2xl bg-slate-50/80 px-4 py-3 text-sm text-slate-600">
              {{ activeProject.description }}
            </p>
            <dl class="grid gap-4 sm:grid-cols-3">
              <div class="rounded-2xl border border-slate-200/80 bg-white px-4 py-3">
                <dt class="text-xs uppercase tracking-widest text-slate-400">状态</dt>
                <dd class="mt-2 text-lg font-semibold" :data-status="activeProject.status">{{ statusLabel(activeProject.status) }}</dd>
              </div>
              <div class="rounded-2xl border border-slate-200/80 bg-white px-4 py-3">
                <dt class="text-xs uppercase tracking-widest text-slate-400">创建时间</dt>
                <dd class="mt-2 text-lg font-semibold">{{ formatTimestamp(activeProject.created_at) }}</dd>
              </div>
              <div class="rounded-2xl border border-slate-200/80 bg-white px-4 py-3">
                <dt class="text-xs uppercase tracking-widest text-slate-400">执行记录</dt>
                <dd class="mt-2 text-lg font-semibold">
                  {{ activeProject.operations?.length ? `${activeProject.operations.length} 条` : '暂无' }}
                </dd>
              </div>
            </dl>
            <div v-if="hasActiveMetadata" class="space-y-3">
              <h4 class="text-sm font-semibold text-slate-700">附加信息</h4>
              <ul class="space-y-2 rounded-2xl border border-slate-200/80 bg-slate-50/80 p-4">
                <li v-for="(value, key) in activeProject.metadata" :key="key" class="text-sm text-slate-600">
                  <strong class="font-medium text-slate-700">{{ key }}：</strong>{{ formatMetadataValue(value) }}
                </li>
              </ul>
            </div>
          </div>
        </section>
        <section v-else class="card-surface space-y-3 p-10 text-center">
          <h3 class="text-xl font-semibold text-slate-900">欢迎使用项目工作台</h3>
          <p class="text-sm text-slate-500">从左侧选择一个项目，或点击上方按钮快速创建新项目。</p>
          <p v-if="error" class="text-sm text-rose-600">{{ error }}</p>
        </section>
      </main>
    </div>

    <transition
      enter-active-class="transition ease-out duration-200"
      enter-from-class="opacity-0"
      enter-to-class="opacity-100"
      leave-active-class="transition ease-in duration-150"
      leave-from-class="opacity-100"
      leave-to-class="opacity-0"
    >
      <div
        v-if="showCreateModal"
        class="fixed inset-0 z-30 flex items-center justify-center bg-slate-900/40 px-4 py-6 backdrop-blur"
        @click.self="handleCreateCancelled"
      >
        <div class="w-full max-w-3xl rounded-3xl bg-white p-6 shadow-2xl">
          <header class="flex items-start justify-between gap-4 border-b border-slate-200 pb-4">
            <div>
              <p class="text-xs font-semibold uppercase tracking-[0.4em] text-slate-400">快速创建</p>
              <h2 class="mt-1 text-2xl font-semibold text-slate-900">新建项目</h2>
            </div>
            <button
              class="flex h-10 w-10 items-center justify-center rounded-full border border-slate-200 text-slate-500 transition hover:bg-slate-100"
              type="button"
              @click="handleCreateCancelled"
              aria-label="关闭"
            >
              ✕
            </button>
          </header>
          <ProjectDashboard
            :project="null"
            :loading="false"
            :error="error"
            mode="create"
            @project-created="handleProjectSaved"
            @cancel="handleCreateCancelled"
          />
        </div>
      </div>
    </transition>

    <transition
      enter-active-class="transition ease-out duration-200"
      enter-from-class="opacity-0"
      enter-to-class="opacity-100"
      leave-active-class="transition ease-in duration-150"
      leave-from-class="opacity-100"
      leave-to-class="opacity-0"
    >
      <div
        v-if="showProjectModal"
        class="fixed inset-0 z-30 flex items-center justify-center bg-slate-900/40 px-4 py-6 backdrop-blur"
        @click.self="handleProjectModalCancelled"
      >
        <div class="w-full max-w-5xl rounded-3xl bg-white p-6 shadow-2xl">
          <header class="flex items-start justify-between gap-4 border-b border-slate-200 pb-4">
            <div>
              <p class="text-xs font-semibold uppercase tracking-[0.4em] text-slate-400">{{ projectModalEyebrow }}</p>
              <h2 class="mt-1 text-2xl font-semibold text-slate-900">{{ projectModalTitle }}</h2>
            </div>
            <button
              class="flex h-10 w-10 items-center justify-center rounded-full border border-slate-200 text-slate-500 transition hover:bg-slate-100"
              type="button"
              @click="handleProjectModalCancelled"
              aria-label="关闭"
            >
              ✕
            </button>
          </header>
          <ProjectDashboard
            :project="activeProject"
            :loading="loading"
            :error="error"
            :mode="projectModalMode"
            @project-created="handleProjectSaved"
            @cancel="handleProjectModalCancelled"
          />
        </div>
      </div>
    </transition>

    <AppModal
      v-model="showDeleteModal"
      eyebrow="危险操作"
      title="删除项目"
      :description="deleteDescription"
      cancel-text="取消"
      confirm-text="删除"
      confirm-tone="danger"
      :confirm-loading="isDeleting"
      :confirm-disabled="isDeleting"
      confirm-loading-text="删除中…"
      :close-on-backdrop="!isDeleting"
      :show-close="!isDeleting"
      @cancel="handleDeleteCancelled"
      @confirm="confirmDeleteProject"
    >
      <p class="rounded-2xl bg-rose-50 px-4 py-3 text-sm text-rose-600">
        删除操作不可恢复，将从服务器移除该项目的所有归档与配置数据。
      </p>
    </AppModal>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ArrowPathIcon, EllipsisHorizontalIcon, EyeIcon, PencilSquareIcon, PlusIcon } from '@heroicons/vue/24/outline'
import AppModal from '../components/AppModal.vue'
import ProjectDashboard from '../components/ProjectDashboard.vue'
import { useActiveProject } from '../composables/useActiveProject'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api'

const projects = ref([])
const loading = ref(false)
const error = ref('')
const isRefreshing = ref(false)
const isDeleting = ref(false)
const lastSelectedProject = ref('')
const showCreateModal = ref(false)
const showProjectModal = ref(false)
const projectModalMode = ref('view')
const showDeleteModal = ref(false)
const openActionMenu = ref('')
const projectPendingDelete = ref('')

const { activeProjectName, setActiveProject, clearActiveProject } = useActiveProject()
const selectedProjectName = ref(activeProjectName.value || '')

const closeProjectMenu = () => {
  openActionMenu.value = ''
}

const toggleProjectMenu = (name) => {
  openActionMenu.value = openActionMenu.value === name ? '' : name
}

const fetchProjects = async () => {
  loading.value = true
  error.value = ''
  try {
    const response = await fetch(`${API_BASE_URL}/projects`)
    if (!response.ok) {
      throw new Error('获取项目列表失败')
    }
    const data = await response.json()
    projects.value = Array.isArray(data.projects) ? data.projects : []
    if (!projects.value.length) {
      selectedProjectName.value = ''
      clearActiveProject()
    } else {
      const currentName = activeProjectName.value || selectedProjectName.value
      const matched = currentName
        ? projects.value.find((project) => project.name === currentName)
        : null
      const targetProject = matched || projects.value[0]
      selectedProjectName.value = targetProject.name
      setActiveProject(targetProject)
    }
  } catch (err) {
    error.value = err instanceof Error ? err.message : '未知错误'
  } finally {
    loading.value = false
    isRefreshing.value = false
  }
}

const refreshProjects = async () => {
  if (isRefreshing.value) return
  isRefreshing.value = true
  closeProjectMenu()
  await fetchProjects()
}

const activeProject = computed(() =>
  projects.value.find((project) => project.name === selectedProjectName.value) || null
)

const totalProjects = computed(() => projects.value.length)
const completedProjects = computed(() =>
  projects.value.filter((project) => project.status === 'success').length
)
const failedProjects = computed(() =>
  projects.value.filter((project) => project.status === 'error').length
)
const activeProjectsCount = computed(() =>
  projects.value.filter((project) => project.status !== 'success').length
)

const hasActiveMetadata = computed(() => {
  const metadata = activeProject.value?.metadata
  return metadata && Object.keys(metadata).length > 0
})

const projectModalTitle = computed(() =>
  projectModalMode.value === 'edit' ? '编辑项目' : '查看项目信息'
)

const projectModalEyebrow = computed(() =>
  projectModalMode.value === 'edit' ? '更新信息' : '项目详情'
)

const deleteDescription = computed(() => {
  if (!projectPendingDelete.value) {
    return '确认删除当前项目吗？此操作无法撤销。'
  }
  return `确定要删除项目 “${projectPendingDelete.value}” 吗？此操作无法撤销。`
})

const startNewProject = () => {
  lastSelectedProject.value = selectedProjectName.value
  showCreateModal.value = true
  error.value = ''
  closeProjectMenu()
}

const closeCreateModal = () => {
  showCreateModal.value = false
  if (!projects.value.length) {
    selectedProjectName.value = lastSelectedProject.value || ''
  }
  closeProjectMenu()
}

const openProject = (name) => {
  if (!name) return
  selectedProjectName.value = name
  const project = projects.value.find((item) => item.name === name)
  setActiveProject(project || name)
  error.value = ''
  closeProjectMenu()
}

const startEditProject = (name = selectedProjectName.value) => {
  error.value = ''
  if (!projects.value.length) {
    error.value = '当前没有可编辑的项目，请先创建一个新项目'
    return
  }
  if (name) {
    selectedProjectName.value = name
    const project = projects.value.find((item) => item.name === name)
    setActiveProject(project || name)
  }
  if (!selectedProjectName.value && projects.value.length) {
    selectedProjectName.value = projects.value[0].name
    setActiveProject(projects.value[0])
  }
  lastSelectedProject.value = selectedProjectName.value
  projectModalMode.value = 'edit'
  showProjectModal.value = true
  closeProjectMenu()
}

const startViewProject = (name = selectedProjectName.value) => {
  error.value = ''
  if (!projects.value.length) return
  if (name) {
    selectedProjectName.value = name
    const project = projects.value.find((item) => item.name === name)
    setActiveProject(project || name)
  }
  if (!activeProject.value) return
  projectModalMode.value = 'view'
  showProjectModal.value = true
  closeProjectMenu()
}

const confirmDeleteProject = async (name) => {
  const targetName = name || projectPendingDelete.value || selectedProjectName.value
  if (!targetName) return
  error.value = ''
  isDeleting.value = true
  try {
    const response = await fetch(`${API_BASE_URL}/projects/${encodeURIComponent(targetName)}`, {
      method: 'DELETE'
    })
    if (!response.ok) {
      throw new Error('删除项目失败')
    }
    projects.value = projects.value.filter((project) => project.name !== targetName)
    if (projects.value.length) {
      selectedProjectName.value = projects.value[0].name
      setActiveProject(projects.value[0])
    } else {
      selectedProjectName.value = ''
      clearActiveProject()
    }
    closeProjectModal()
    closeDeleteModal()
  } catch (err) {
    error.value = err instanceof Error ? err.message : '删除项目时出现问题'
  } finally {
    isDeleting.value = false
  }
}

const closeDeleteModal = () => {
  showDeleteModal.value = false
  projectPendingDelete.value = ''
}

const closeProjectModal = () => {
  showProjectModal.value = false
  projectModalMode.value = 'view'
}

const handleProjectSaved = (project) => {
  const existingIndex = projects.value.findIndex((item) => item.name === project.name)
  if (existingIndex === -1) {
    projects.value = [project, ...projects.value]
  } else {
    projects.value.splice(existingIndex, 1, project)
  }
  selectedProjectName.value = project.name
  lastSelectedProject.value = project.name
  showCreateModal.value = false
  closeProjectModal()
  error.value = ''
  setActiveProject(project)
  closeProjectMenu()
}

const handleCreateCancelled = () => {
  closeCreateModal()
}

const handleMenuView = (name) => {
  startViewProject(name)
}

const handleMenuEdit = (name) => {
  startEditProject(name)
}

const handleMenuDelete = (name) => {
  closeProjectMenu()
  if (!name) return
  projectPendingDelete.value = name
  showDeleteModal.value = true
  error.value = ''
}

const formatTimestamp = (timestamp) => {
  if (!timestamp) return '未知'
  try {
    const date = new Date(timestamp)
    return date.toLocaleString()
  } catch (err) {
    return timestamp
  }
}

const statusLabel = (status) => {
  if (status === 'success') return '成功'
  if (status === 'error') return '失败'
  return '进行中'
}

const formatMetadataValue = (value) => {
  if (value === null || value === undefined) return '—'
  if (typeof value === 'object') {
    try {
      return JSON.stringify(value)
    } catch (err) {
      return String(value)
    }
  }
  return String(value)
}

const handleProjectModalCancelled = () => {
  closeProjectModal()
}

const handleDeleteCancelled = () => {
  if (isDeleting.value) return
  closeDeleteModal()
}

onMounted(() => {
  document.addEventListener('click', closeProjectMenu)
  fetchProjects()
})

onBeforeUnmount(() => {
  document.removeEventListener('click', closeProjectMenu)
})

watch(activeProjectName, (name) => {
  if (!name) {
    selectedProjectName.value = ''
    return
  }
  if (selectedProjectName.value !== name) {
    selectedProjectName.value = name
  }
})

watch(showDeleteModal, (visible) => {
  if (!visible) {
    projectPendingDelete.value = ''
  }
})
</script>
