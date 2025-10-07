import { computed, ref, watch } from 'vue'

const storageKey = 'opinion-system-active-project'
const activeProject = ref(null)

if (typeof window !== 'undefined') {
  const savedName = window.localStorage.getItem(storageKey)
  if (savedName) {
    activeProject.value = { name: savedName }
  }
}

watch(
  () => activeProject.value?.name ?? '',
  (name) => {
    if (typeof window === 'undefined') return
    if (name) {
      window.localStorage.setItem(storageKey, name)
    } else {
      window.localStorage.removeItem(storageKey)
    }
  }
)

const setActiveProject = (project) => {
  if (project && typeof project === 'object') {
    activeProject.value = { ...project }
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
