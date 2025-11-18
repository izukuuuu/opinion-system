import { computed, ref, watch } from 'vue'
import { useApiBase } from './useApiBase'

const storageKey = 'topic-creation-active-project'
const projects = ref([])
const projectsLoading = ref(false)
const projectsError = ref('')
const selectedProjectName = ref(
  typeof window !== 'undefined' ? window.localStorage.getItem(storageKey) || '' : ''
)

const { ensureApiBase } = useApiBase()

const projectOptions = computed(() =>
  projects.value
    .map((project) => {
      const name = typeof project.name === 'string' ? project.name.trim() : ''
      if (!name) return null
      const display =
        typeof project.display_name === 'string' && project.display_name.trim()
          ? project.display_name.trim()
          : name
      return { value: name, label: display, raw: project }
    })
    .filter(Boolean)
)

const activeProject = computed(() => {
  const name = selectedProjectName.value
  if (!name) return null
  return projects.value.find((project) => project.name === name) || null
})

const activeProjectName = computed(() => activeProject.value?.name || selectedProjectName.value || '')

const persistSelection = () => {
  if (typeof window === 'undefined') return
  if (selectedProjectName.value) {
    window.localStorage.setItem(storageKey, selectedProjectName.value)
  } else {
    window.localStorage.removeItem(storageKey)
  }
}

const applyProjectSelection = () => {
  const normalizedSelected = (selectedProjectName.value || '').trim()

  // 列表还没加载出来时，先保留当前选择（包括 localStorage 的值）
  if (!projectOptions.value.length) {
    persistSelection()
    return
  }

  if (normalizedSelected) {
    const exists = projectOptions.value.some(
      (item) => (item.value || '').trim() === normalizedSelected
    )
    if (exists) {
      persistSelection()
      return
    }
  }

  // 有列表但当前选择不存在时，默认选第一个
  selectedProjectName.value = projectOptions.value[0]?.value || ''
  persistSelection()
}

const setSelectedProjectName = (value) => {
  selectedProjectName.value = typeof value === 'string' ? value : ''
  persistSelection()
}

watch(selectedProjectName, () => {
  persistSelection()
})

const loadProjects = async ({ force = false } = {}) => {
  if (projectsLoading.value) return
  if (!force && projects.value.length) {
    applyProjectSelection()
    return
  }
  projectsLoading.value = true
  projectsError.value = ''
  try {
    const baseUrl = await ensureApiBase()
    const response = await fetch(`${baseUrl}/projects`)
    if (!response.ok) {
      throw new Error('获取项目列表失败')
    }
    const data = await response.json()
    projects.value = Array.isArray(data.projects) ? data.projects : []
    applyProjectSelection()
  } catch (err) {
    projectsError.value = err instanceof Error ? err.message : '请求项目列表时出现问题'
    projects.value = []
  } finally {
    projectsLoading.value = false
  }
}

const refreshProjects = async () => {
  await loadProjects({ force: true })
}

export function useTopicCreationProject() {
  return {
    projects,
    projectsLoading,
    projectsError,
    projectOptions,
    activeProject,
    activeProjectName,
    selectedProjectName,
    setSelectedProjectName,
    loadProjects,
    refreshProjects
  }
}
