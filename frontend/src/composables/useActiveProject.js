import { computed, ref, watch } from 'vue'

const storageKey = 'opinion-system-active-project'
const activeProject = ref(null)

if (typeof window !== 'undefined') {
  const savedValue = window.localStorage.getItem(storageKey)
  if (savedValue) {
    try {
      const parsed = JSON.parse(savedValue)
      if (parsed && typeof parsed === 'object') {
        const name = typeof parsed.name === 'string' ? parsed.name : ''
        const id = typeof parsed.id === 'string' ? parsed.id : ''
        activeProject.value = name ? { name, id } : null
      } else if (typeof savedValue === 'string' && savedValue.trim()) {
        activeProject.value = { name: savedValue }
      }
    } catch {
      activeProject.value = { name: savedValue }
    }
  }
}

watch(
  () => ({
    name: activeProject.value?.name ?? '',
    id: activeProject.value?.id ?? ''
  }),
  ({ name, id }) => {
    if (typeof window === 'undefined') return
    if (name) {
      window.localStorage.setItem(storageKey, JSON.stringify({ name, id }))
    } else {
      window.localStorage.removeItem(storageKey)
    }
  }
)

const setActiveProject = (project) => {
  if (project && typeof project === 'object') {
    const name = typeof project.name === 'string' ? project.name : ''
    const idCandidate =
      (typeof project.id === 'string' && project.id) ||
      (typeof project.project_id === 'string' && project.project_id) ||
      ''
    activeProject.value = { ...project, name, id: idCandidate }
  } else if (typeof project === 'string') {
    activeProject.value = project ? { name: project } : null
  } else {
    activeProject.value = null
  }
}

const clearActiveProject = () => {
  activeProject.value = null
}

export function useActiveProject() {
  const activeProjectName = computed(() => activeProject.value?.name ?? '')

  return {
    activeProject,
    activeProjectName,
    setActiveProject,
    clearActiveProject
  }
}
