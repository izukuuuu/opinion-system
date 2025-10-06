<template>
  <div class="layout">
    <aside class="layout__sidebar">
      <h1 class="layout__title">Opinion System 项目面板</h1>
      <p class="layout__subtitle">集中管理专题流程，追踪各步骤执行情况。</p>
      <section class="layout__actions">
        <button class="refresh" type="button" @click="refreshProjects" :disabled="isRefreshing">
          {{ isRefreshing ? '刷新中…' : '刷新项目' }}
        </button>
      </section>
      <ul class="layout__project-list">
        <li
          v-for="project in projects"
          :key="project.name"
          :class="['layout__project-item', { 'layout__project-item--active': project.name === selectedProjectName }]"
        >
          <button type="button" @click="selectProject(project.name)">
            <span class="project-name">{{ project.name }}</span>
            <span class="project-status" :data-status="project.status">{{ statusLabel(project.status) }}</span>
            <span class="project-updated">更新：{{ formatTimestamp(project.updated_at) }}</span>
          </button>
        </li>
      </ul>
      <p v-if="!projects.length && !loading" class="empty">暂无项目记录。</p>
      <p v-if="loading" class="loading">加载中…</p>
      <p v-if="error" class="error">{{ error }}</p>
    </aside>
    <main class="layout__main">
      <ProjectDashboard
        :project="activeProject"
        :loading="loading"
        :error="error"
        @project-created="handleProjectCreated"
      />
    </main>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import ProjectDashboard from '../components/ProjectDashboard.vue'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api'

const projects = ref([])
const selectedProjectName = ref('')
const loading = ref(false)
const error = ref('')
const isRefreshing = ref(false)

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
    if (!selectedProjectName.value && projects.value.length) {
      selectedProjectName.value = projects.value[0].name
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
  await fetchProjects()
}

const selectProject = (name) => {
  selectedProjectName.value = name
}

const activeProject = computed(() =>
  projects.value.find((project) => project.name === selectedProjectName.value) || null
)

const handleProjectCreated = (project) => {
  const existingIndex = projects.value.findIndex((item) => item.name === project.name)
  if (existingIndex === -1) {
    projects.value = [project, ...projects.value]
  } else {
    projects.value.splice(existingIndex, 1, project)
  }
  selectedProjectName.value = project.name
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

onMounted(fetchProjects)
</script>

<style scoped>
.layout {
  display: grid;
  grid-template-columns: 320px 1fr;
  gap: 2.5rem;
  color: #0f172a;
  font-family: 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif;
}

.layout__sidebar {
  padding: 2.25rem 2rem;
  background: rgba(255, 255, 255, 0.92);
  border-radius: 28px;
  display: flex;
  flex-direction: column;
  gap: 1.75rem;
  border: 1px solid rgba(148, 163, 184, 0.18);
  box-shadow: 0 25px 55px -22px rgba(30, 64, 175, 0.3);
}

.layout__title {
  margin: 0;
  font-size: 1.75rem;
  font-weight: 700;
}

.layout__subtitle {
  margin: 0;
  color: #52606d;
  line-height: 1.4;
}

.layout__actions {
  display: flex;
  gap: 0.5rem;
}

.refresh {
  border: none;
  background: linear-gradient(135deg, #2563eb 0%, #7c3aed 100%);
  color: #fff;
  padding: 0.6rem 1.2rem;
  border-radius: 999px;
  cursor: pointer;
  transition: transform 0.2s ease, box-shadow 0.2s ease;
  font-weight: 600;
}

.refresh:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.refresh:not(:disabled):hover {
  transform: translateY(-1px);
  box-shadow: 0 8px 20px rgba(37, 99, 235, 0.25);
}

.layout__project-list {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  flex: 1;
  overflow-y: auto;
  max-height: 60vh;
  padding-right: 0.35rem;
}

.layout__project-item button {
  width: 100%;
  border: none;
  background: rgba(248, 250, 252, 0.9);
  border-radius: 16px;
  padding: 0.95rem 1.1rem;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 0.35rem;
  cursor: pointer;
  transition: transform 0.2s ease, box-shadow 0.2s ease;
  text-align: left;
}

.layout__project-item button:hover {
  transform: translateX(4px);
  box-shadow: 0 18px 45px rgba(37, 99, 235, 0.18);
}

.layout__project-item--active button {
  background: linear-gradient(135deg, rgba(59, 130, 246, 0.25), rgba(14, 165, 233, 0.3));
  box-shadow: 0 24px 50px rgba(37, 99, 235, 0.28);
}

.project-name {
  font-weight: 600;
}

.project-status {
  font-size: 0.85rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: #475569;
}

.project-status[data-status='success'] {
  color: #059669;
}

.project-status[data-status='error'] {
  color: #dc2626;
}

.project-updated {
  font-size: 0.8rem;
  color: #64748b;
}

.layout__main {
  padding: 0;
}

@media (max-width: 1024px) {
  .layout {
    grid-template-columns: 1fr;
  }

  .layout__sidebar {
    padding: 2rem;
    border-radius: 24px;
  }

  .layout__project-list {
    max-height: none;
  }

  .layout__main {
    padding: 0;
  }
}

.loading,
.empty,
.error {
  margin: 0;
  font-size: 0.95rem;
}

.error {
  color: #dc2626;
}

@media (max-width: 960px) {
  .layout__sidebar {
    padding: 1.75rem 1.5rem;
  }
}
</style>
