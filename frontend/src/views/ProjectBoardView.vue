<template>
  <div class="board">
    <section class="board__hero">
      <div class="hero__background"></div>
      <div class="hero__content">
        <div class="hero__copy">
          <p class="hero__eyebrow">项目工作台</p>
          <h1>Opinion System 控制中心</h1>
          <p>在此编辑和开始新项目</p>
        </div>
        <button class="hero__action" type="button" @click="startNewProject">
          <span class="hero__action-icon" aria-hidden="true">+</span>
          新建项目
        </button>
      </div>

      <div v-if="activeProject" class="hero__current">
        <div class="hero__current-header">
          <div>
            <span class="hero__current-label">当前项目</span>
            <h2 class="hero__current-title">{{ activeProject.name }}</h2>
          </div>
          <button class="hero__current-edit" type="button" @click="startEditProject(activeProject.name)">
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <path
                d="M16.6 4.2a2 2 0 0 1 2.8 2.8l-9.4 9.4-3.3.6.6-3.3 9.3-9.5ZM5 19a1 1 0 1 0 0 2h14a1 1 0 1 0 0-2H5Z"
                fill="currentColor"
              />
            </svg>
            编辑
          </button>
        </div>
        <div class="hero__current-meta">
          <div class="meta-block">
            <span class="meta-block__label">状态</span>
            <span class="meta-block__value" :data-status="activeProject.status">
              {{ statusLabel(activeProject.status) }}
            </span>
          </div>
          <div class="meta-block">
            <span class="meta-block__label">最近更新</span>
            <span class="meta-block__value">{{ formatTimestamp(activeProject.updated_at) }}</span>
          </div>
          <div class="meta-block">
            <span class="meta-block__label">当前模式</span>
            <span class="meta-block__value">{{ modeLabel }}</span>
          </div>
        </div>
      </div>
      <div v-else class="hero__current hero__current--empty">
        <div class="hero__empty-icon" aria-hidden="true">📊</div>
        <h2>暂未选择项目</h2>
        <p>从下方列表选择一个项目，或点击右上角按钮快速创建。</p>
      </div>
    </section>

    <div class="board__body">
      <aside class="board__sidebar">
        <header class="sidebar__header">
          <div>
            <h3>项目列表</h3>
            <p>浏览所有项目并快速切换。</p>
          </div>
          <button class="sidebar__refresh" type="button" @click="refreshProjects" :disabled="isRefreshing">
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <path
                d="M5 12a7 7 0 0 1 11.9-4.9l1.5-1.5a1 1 0 1 1 1.4 1.4l-3.3 3.3H16a1 1 0 0 1-1-1V7.9A5 5 0 1 0 17 16a1 1 0 0 1 1.7 1A7 7 0 0 1 5 12Z"
                fill="currentColor"
              />
            </svg>
            {{ isRefreshing ? '刷新中…' : '刷新' }}
          </button>
        </header>

        <div v-if="projects.length" class="sidebar__stats">
          <div class="stat-card">
            <span class="stat-card__label">项目总数</span>
            <strong class="stat-card__value">{{ totalProjects }}</strong>
          </div>
          <div class="stat-card">
            <span class="stat-card__label">进行中</span>
            <strong class="stat-card__value">{{ activeProjectsCount }}</strong>
          </div>
          <div class="stat-card">
            <span class="stat-card__label">已完成</span>
            <strong class="stat-card__value">{{ completedProjects }}</strong>
          </div>
          <div class="stat-card">
            <span class="stat-card__label">失败</span>
            <strong class="stat-card__value">{{ failedProjects }}</strong>
          </div>
        </div>

        <ul class="project-list">
          <li
            v-for="project in projects"
            :key="project.name"
            :class="['project-tile', { 'project-tile--active': project.name === selectedProjectName }]"
          >
            <button class="project-tile__body" type="button" @click="openProject(project.name)">
              <span class="project-tile__avatar">{{ project.name.slice(0, 1).toUpperCase() }}</span>
              <div class="project-tile__info">
                <span class="project-tile__name">{{ project.name }}</span>
                <span class="project-tile__date">更新：{{ formatTimestamp(project.updated_at) }}</span>
              </div>
            </button>
            <div class="project-tile__meta">
              <span class="project-tile__status" :data-status="project.status">
                {{ statusLabel(project.status) }}
              </span>
              <div class="project-tile__actions">
                <button
                  type="button"
                  class="project-tile__menu-button"
                  @click.stop="toggleProjectMenu(project.name)"
                  :aria-expanded="openActionMenu === project.name"
                  title="更多操作"
                >
                  <svg viewBox="0 0 24 24" aria-hidden="true">
                    <path
                      d="M5 12a1.5 1.5 0 1 1 3 0 1.5 1.5 0 0 1-3 0Zm5.5 0a1.5 1.5 0 1 1 3 0 1.5 1.5 0 0 1-3 0Zm5.5 0a1.5 1.5 0 1 1 3 0 1.5 1.5 0 0 1-3 0Z"
                      fill="currentColor"
                    />
                  </svg>
                </button>
                <transition name="dropdown-fade">
                  <ul
                    v-if="openActionMenu === project.name"
                    class="project-tile__menu"
                    role="menu"
                    @click.stop
                  >
                    <li>
                      <button type="button" role="menuitem" @click="handleMenuView(project.name)">
                        查看项目
                      </button>
                    </li>
                    <li>
                      <button type="button" role="menuitem" @click="handleMenuEdit(project.name)">
                        编辑项目
                      </button>
                    </li>
                    <li>
                      <button
                        type="button"
                        role="menuitem"
                        class="project-tile__menu-danger"
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
          </li>
        </ul>
        <p v-if="!projects.length && !loading" class="state-message">暂无项目记录，点击右上角按钮开始创建吧。</p>
        <p v-if="loading" class="state-message">加载中…</p>
        <p v-if="error" class="state-message state-message--error">{{ error }}</p>
      </aside>

      <main class="board__main">
        <ProjectDashboard
          :project="displayedProject"
          :loading="loading"
          :error="error"
          :mode="viewMode"
          @project-created="handleProjectCreated"
          @cancel="handleDashboardCancel"
        />
      </main>
    </div>

    <transition name="modal-fade">
      <div v-if="showCreateModal" class="modal" @click.self="handleCreateCancelled">
        <div class="modal__panel">
          <header class="modal__header">
            <div>
              <p class="modal__eyebrow">快速创建</p>
              <h2>新建项目</h2>
            </div>
            <button class="modal__close" type="button" @click="handleCreateCancelled" aria-label="关闭">
              ✕
            </button>
          </header>
          <ProjectDashboard
            :project="null"
            :loading="false"
            :error="error"
            mode="create"
            @project-created="handleProjectCreated"
            @cancel="handleCreateCancelled"
          />
        </div>
      </div>
    </transition>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import ProjectDashboard from '../components/ProjectDashboard.vue'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api'

const projects = ref([])
const selectedProjectName = ref('')
const loading = ref(false)
const error = ref('')
const isRefreshing = ref(false)
const isDeleting = ref(false)
const viewMode = ref('view')
const lastSelectedProject = ref('')
const showCreateModal = ref(false)
const openActionMenu = ref('')

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
    } else if (!selectedProjectName.value) {
      selectedProjectName.value = projects.value[0].name
    }
    if (selectedProjectName.value && !projects.value.some((project) => project.name === selectedProjectName.value)) {
      selectedProjectName.value = projects.value[0]?.name || ''
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

const displayedProject = computed(() => activeProject.value)

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

const modeLabel = computed(() => {
  if (showCreateModal.value) return '新建'
  if (viewMode.value === 'edit') return '编辑'
  if (viewMode.value === 'view' && activeProject.value) return '查看'
  return '浏览'
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
  viewMode.value = 'view'
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
  }
  if (!selectedProjectName.value && projects.value.length) {
    selectedProjectName.value = projects.value[0].name
  }
  lastSelectedProject.value = selectedProjectName.value
  viewMode.value = 'edit'
  closeProjectMenu()
}

const handleDashboardCancel = () => {
  if (viewMode.value === 'edit') {
    if (lastSelectedProject.value) {
      const exists = projects.value.some((project) => project.name === lastSelectedProject.value)
      if (exists) {
        selectedProjectName.value = lastSelectedProject.value
      }
    }
    viewMode.value = projects.value.length ? 'view' : 'view'
  }
}

const confirmDeleteProject = async (name = selectedProjectName.value) => {
  if (!name) return
  closeProjectMenu()
  const confirmed = window.confirm(`确定要删除项目 “${name}” 吗？`)
  if (!confirmed) return
  error.value = ''
  isDeleting.value = true
  try {
    const response = await fetch(`${API_BASE_URL}/projects/${encodeURIComponent(name)}`, {
      method: 'DELETE'
    })
    if (!response.ok) {
      throw new Error('删除项目失败')
    }
    projects.value = projects.value.filter((project) => project.name !== name)
    if (projects.value.length) {
      selectedProjectName.value = projects.value[0].name
      viewMode.value = 'view'
    } else {
      selectedProjectName.value = ''
      viewMode.value = 'view'
    }
  } catch (err) {
    error.value = err instanceof Error ? err.message : '删除项目时出现问题'
  } finally {
    isDeleting.value = false
  }
}

const handleProjectCreated = (project) => {
  const existingIndex = projects.value.findIndex((item) => item.name === project.name)
  if (existingIndex === -1) {
    projects.value = [project, ...projects.value]
  } else {
    projects.value.splice(existingIndex, 1, project)
  }
  selectedProjectName.value = project.name
  lastSelectedProject.value = project.name
  viewMode.value = 'view'
  showCreateModal.value = false
  error.value = ''
  closeProjectMenu()
}

const handleCreateCancelled = () => {
  closeCreateModal()
}

const handleMenuView = (name) => {
  openProject(name)
}

const handleMenuEdit = (name) => {
  startEditProject(name)
}

const handleMenuDelete = (name) => {
  closeProjectMenu()
  confirmDeleteProject(name)
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

onMounted(() => {
  document.addEventListener('click', closeProjectMenu)
  fetchProjects()
})

onBeforeUnmount(() => {
  document.removeEventListener('click', closeProjectMenu)
})
</script>

<style scoped>
.board {
  min-height: 100vh;
  padding: 2.5rem 3rem 3.5rem;
  background: linear-gradient(180deg, #f8fafc 0%, #eef2ff 40%, #e0e7ff 100%);
  color: #0f172a;
}

.board__hero {
  position: relative;
  padding: 1.8rem 2rem;
  border-radius: 24px;
  overflow: hidden;
  background: #ffffff;
  border: 1px solid #e2e8f0;
  box-shadow: 0 20px 40px rgba(15, 23, 42, 0.08);
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
}

.hero__background {
  position: absolute;
  inset: 0;
  background: radial-gradient(circle at top left, rgba(99, 102, 241, 0.18), transparent 60%),
    radial-gradient(circle at bottom right, rgba(59, 130, 246, 0.15), transparent 55%);
  opacity: 0.4;
  pointer-events: none;
}

.hero__content {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1.5rem;
}

.hero__copy {
  max-width: 460px;
}

.hero__eyebrow {
  margin: 0 0 0.45rem;
  font-size: 0.78rem;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: #6366f1;
}

.hero__copy h1 {
  margin: 0;
  font-size: 2rem;
  font-weight: 700;
  color: #1f2937;
}

.hero__copy p {
  margin: 0.75rem 0 0;
  color: #475569;
  line-height: 1.6;
}

.hero__action {
  display: inline-flex;
  align-items: center;
  gap: 0.6rem;
  padding: 0.75rem 1.6rem;
  border-radius: 999px;
  border: none;
  font-weight: 600;
  font-size: 0.95rem;
  color: #ffffff;
  background: linear-gradient(135deg, #6366f1, #8b5cf6);
  box-shadow: 0 16px 32px rgba(99, 102, 241, 0.25);
  cursor: pointer;
  transition: transform 0.2s ease, box-shadow 0.2s ease;
}

.hero__action:hover {
  transform: translateY(-1px);
  box-shadow: 0 18px 36px rgba(99, 102, 241, 0.28);
}

.hero__action-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 1.5rem;
  height: 1.5rem;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.2);
  font-weight: 700;
}

.hero__current {
  position: relative;
  margin-top: 0.5rem;
  padding: 1.25rem 1.5rem;
  border-radius: 20px;
  background: linear-gradient(135deg, #f8fafc 0%, #eef2ff 100%);
  border: 1px solid #e2e8f0;
  display: flex;
  flex-direction: column;
  gap: 1.1rem;
  color: #1f2937;
}

.hero__current-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
}

.hero__current-label {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  padding: 0.3rem 0.75rem;
  border-radius: 999px;
  background: #e0e7ff;
  font-size: 0.78rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: #4338ca;
}

.hero__current-title {
  margin: 0.5rem 0 0;
  font-size: 1.5rem;
  font-weight: 700;
  color: #1f2937;
}

.hero__current-edit {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  padding: 0.5rem 1.1rem;
  border-radius: 999px;
  border: none;
  background: #e0e7ff;
  color: #4338ca;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.2s ease, transform 0.2s ease;
}

.hero__current-edit svg {
  width: 1rem;
  height: 1rem;
}

.hero__current-edit:hover {
  background: #c7d2fe;
  transform: translateY(-1px);
}

.hero__current-meta {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 1rem;
}

.meta-block {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
}

.meta-block__label {
  font-size: 0.75rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: #64748b;
}

.meta-block__value {
  font-size: 1.05rem;
  font-weight: 600;
  color: #1f2937;
}

.meta-block__value[data-status='success'] {
  color: #047857;
}

.meta-block__value[data-status='error'] {
  color: #b91c1c;
}

.hero__current--empty {
  align-items: center;
  text-align: center;
  color: #475569;
  background: linear-gradient(135deg, #f8fafc 0%, #e2e8f0 100%);
}

.hero__empty-icon {
  font-size: 2rem;
}

.board__body {
  margin-top: 2rem;
  display: grid;
  grid-template-columns: minmax(280px, 320px) 1fr;
  gap: 2rem;
  align-items: flex-start;
}

.board__sidebar {
  background: #ffffff;
  border-radius: 24px;
  padding: 1.75rem 1.5rem;
  border: 1px solid #e2e8f0;
  box-shadow: 0 18px 36px rgba(15, 23, 42, 0.06);
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
}

.sidebar__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem;
}

.sidebar__header h3 {
  margin: 0;
  font-size: 1.2rem;
  color: #1f2937;
}

.sidebar__header p {
  margin: 0.35rem 0 0;
  color: #64748b;
}

.sidebar__refresh {
  border: 1px solid transparent;
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  padding: 0.5rem 1.05rem;
  border-radius: 999px;
  background: #e0e7ff;
  color: #4338ca;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.2s ease, transform 0.2s ease, border-color 0.2s ease;
}

.sidebar__refresh svg {
  width: 1rem;
  height: 1rem;
}

.sidebar__refresh:hover:not(:disabled) {
  background: #c7d2fe;
  border-color: #a5b4fc;
  transform: translateY(-1px);
}

.sidebar__refresh:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.sidebar__stats {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0.75rem;
}

.stat-card {
  padding: 0.75rem 0.9rem;
  border-radius: 16px;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
}

.stat-card__label {
  font-size: 0.78rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: #64748b;
}

.stat-card__value {
  font-size: 1.4rem;
  font-weight: 700;
  color: #1f2937;
}

.project-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.project-tile {
  padding: 0.9rem 1rem;
  border-radius: 16px;
  border: 1px solid #e2e8f0;
  background: #ffffff;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  transition: border-color 0.2s ease, box-shadow 0.2s ease, transform 0.2s ease;
}

.project-tile:hover {
  border-color: #c7d2fe;
  box-shadow: 0 14px 28px rgba(99, 102, 241, 0.08);
}

.project-tile--active {
  border-color: #6366f1;
  box-shadow: 0 16px 32px rgba(99, 102, 241, 0.15);
  transform: translateY(-1px);
}

.project-tile__body {
  display: flex;
  align-items: center;
  gap: 0.85rem;
  width: 100%;
  text-align: left;
  background: none;
  border: none;
  color: inherit;
  cursor: pointer;
}

.project-tile__avatar {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 2.5rem;
  height: 2.5rem;
  border-radius: 12px;
  background: #eef2ff;
  color: #4338ca;
  font-size: 1rem;
  font-weight: 600;
}

.project-tile__info {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.project-tile__name {
  font-weight: 600;
  color: #1f2937;
}

.project-tile__date {
  font-size: 0.82rem;
  color: #64748b;
}

.project-tile__meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
}

.project-tile__status {
  padding: 0.3rem 0.75rem;
  border-radius: 999px;
  font-size: 0.78rem;
  font-weight: 600;
  background: #f1f5f9;
  color: #1f2937;
}

.project-tile__status[data-status='success'] {
  background: rgba(16, 185, 129, 0.15);
  color: #047857;
}

.project-tile__status[data-status='error'] {
  background: rgba(239, 68, 68, 0.18);
  color: #b91c1c;
}

.project-tile__actions {
  position: relative;
  display: flex;
  align-items: center;
}

.project-tile__menu-button {
  border: 1px solid #e2e8f0;
  background: #ffffff;
  color: #4338ca;
  width: 2rem;
  height: 2rem;
  border-radius: 50%;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: background 0.2s ease, border-color 0.2s ease, transform 0.2s ease;
}

.project-tile__menu-button:hover {
  background: #eef2ff;
  border-color: #c7d2fe;
  transform: translateY(-1px);
}

.project-tile__menu {
  position: absolute;
  top: calc(100% + 0.5rem);
  right: 0;
  min-width: 160px;
  background: #ffffff;
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  box-shadow: 0 18px 36px rgba(15, 23, 42, 0.12);
  padding: 0.4rem 0;
  list-style: none;
  margin: 0;
  z-index: 10;
}

.project-tile__menu li {
  margin: 0;
}

.project-tile__menu button {
  width: 100%;
  padding: 0.55rem 1rem;
  border: none;
  background: none;
  text-align: left;
  font-size: 0.9rem;
  color: #1f2937;
  cursor: pointer;
  transition: background 0.2s ease, color 0.2s ease;
}

.project-tile__menu button:hover:not(:disabled) {
  background: #eef2ff;
  color: #4338ca;
}

.project-tile__menu button:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.project-tile__menu-danger {
  color: #b91c1c;
}

.project-tile__menu-danger:hover:not(:disabled) {
  background: #fee2e2;
  color: #b91c1c;
}

.dropdown-fade-enter-active,
.dropdown-fade-leave-active {
  transition: opacity 0.15s ease, transform 0.15s ease;
}

.dropdown-fade-enter-from,
.dropdown-fade-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}

.state-message {
  font-size: 0.9rem;
  color: #64748b;
}

.state-message--error {
  color: #b91c1c;
}

.board__main {
  background: #ffffff;
  border-radius: 24px;
  padding: 2rem;
  border: 1px solid #e2e8f0;
  box-shadow: 0 24px 48px rgba(15, 23, 42, 0.08);
}

.modal-fade-enter-active,
.modal-fade-leave-active {
  transition: opacity 0.2s ease;
}

.modal-fade-enter-from,
.modal-fade-leave-to {
  opacity: 0;
}

.modal {
  position: fixed;
  inset: 0;
  background: rgba(15, 23, 42, 0.35);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 2rem;
  z-index: 50;
}

.modal__panel {
  width: min(720px, 100%);
  background: #ffffff;
  border-radius: 20px;
  padding: 2rem 2.25rem 2.25rem;
  border: 1px solid #e2e8f0;
  box-shadow: 0 32px 64px rgba(15, 23, 42, 0.18);
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
}

.modal__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
}

.modal__header h2 {
  margin: 0;
  font-size: 1.6rem;
  color: #1f2937;
}

.modal__eyebrow {
  margin: 0 0 0.35rem;
  font-size: 0.72rem;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: #64748b;
}

.modal__close {
  border: 1px solid transparent;
  background: #eef2ff;
  width: 2.25rem;
  height: 2.25rem;
  border-radius: 50%;
  font-size: 1.1rem;
  color: #4338ca;
  cursor: pointer;
  transition: background 0.2s ease, border-color 0.2s ease;
}

.modal__close:hover {
  background: #c7d2fe;
  border-color: #a5b4fc;
}

@media (max-width: 1280px) {
  .board {
    padding: 2rem;
  }

  .board__body {
    grid-template-columns: 1fr;
  }

  .board__main {
    order: 2;
  }

  .board__sidebar {
    order: 1;
  }
}

@media (max-width: 768px) {
  .board {
    padding: 1.5rem;
  }

  .board__hero {
    padding: 1.5rem;
  }

  .hero__content {
    flex-direction: column;
    align-items: flex-start;
  }

  .hero__current-meta {
    grid-template-columns: 1fr;
  }

  .board__body {
    gap: 1.5rem;
  }

  .board__sidebar {
    padding: 1.5rem;
  }

  .project-tile__meta {
    flex-direction: column;
    align-items: flex-start;
    gap: 0.5rem;
  }

  .project-tile__actions {
    width: 100%;
    justify-content: flex-end;
  }

  .modal__panel {
    padding: 1.5rem;
  }
}
</style>
