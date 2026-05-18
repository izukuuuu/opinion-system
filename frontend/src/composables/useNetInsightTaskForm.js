import { computed, reactive } from 'vue'

export const PLATFORM_OPTIONS = [
  '全部',
  '新闻网站',
  '新闻APP',
  '视频',
  '微博',
  '微信',
  '自媒体号',
  '论坛',
  '电子报',
  '境外新闻',
  'Twitter',
  'Facebook',
]

export const SCOPE_OPTIONS = [
  { value: 'domestic', label: '国内范围' },
  { value: 'foreign', label: '境外范围' },
  { value: 'global', label: '全球范围' },
]

export const SCOPE_PLATFORM_PRESETS = {
  domestic: ['微博', '新闻APP', '新闻网站', '视频', '自媒体号', '论坛', '微信', '电子报'],
  foreign: ['境外新闻', 'Facebook', 'Twitter'],
  global: ['微博', '新闻APP', '新闻网站', '视频', '自媒体号', '论坛', '微信', '电子报', '境外新闻', 'Facebook', 'Twitter'],
}

export function useNetInsightTaskForm() {
  const form = reactive(createNetInsightTaskFormState())
  const canSubmit = computed(() => isNetInsightTaskFormSubmittable(form))

  return {
    form,
    canSubmit,
    resetForm: (settings = {}, overrides = {}) => resetNetInsightTaskForm(form, settings, overrides),
    applyPlan: (plan = {}) => applyNetInsightTaskPlan(form, plan),
    setScope: (scope) => setNetInsightTaskScope(form, scope),
    buildPayload: (overrides = {}) => buildNetInsightTaskPayload(form, overrides),
  }
}

export function createNetInsightTaskFormState() {
  return {
    title: '',
    project: '',
    brief: '',
    scope: 'domestic',
    keywordsText: '',
    platforms: defaultPlatformsForScope('domestic'),
    startDate: '',
    endDate: '',
    totalLimit: 500,
    pageSize: 50,
    sort: 'comments_desc',
    infoType: '2',
    dedupeByContent: true,
    allocateByPlatform: false,
  }
}

export function resetNetInsightTaskForm(form, settings = {}, overrides = {}) {
  const today = new Date()
  const start = new Date(today)
  const defaultDays = Number(settings?.planner?.default_days || 30)
  start.setDate(today.getDate() - defaultDays + 1)

  const scope = normalizeScope(overrides.scope || settings?.planner?.default_scope || 'domestic')
  form.title = ''
  form.project = ''
  form.brief = ''
  form.scope = scope
  form.keywordsText = ''
  form.platforms = normalizePlatformsForSubmit(
    overrides.platforms || defaultPlatformsForScope(scope),
    { expandAll: true }
  )
  form.startDate = formatDateInput(start)
  form.endDate = formatDateInput(today)
  form.totalLimit = Number(settings?.planner?.default_total_limit || 500)
  form.pageSize = Number(settings?.runtime?.page_size || 50)
  form.sort = String(settings?.runtime?.sort || 'comments_desc')
  form.infoType = String(settings?.runtime?.info_type || '2')
  form.dedupeByContent = true
  form.allocateByPlatform = Boolean(settings?.planner?.default_allocate_by_platform)
  Object.assign(form, overrides)
  form.scope = normalizeScope(form.scope)
  form.platforms = normalizePlatformsForSubmit(form.platforms, { expandAll: true })
}

export function applyNetInsightTaskPlan(form, plan = {}) {
  const scope = normalizeScope(plan.scope || form.scope)
  form.scope = scope
  form.title = String(plan.title || form.title || '').trim()
  form.keywordsText = Array.isArray(plan.keywords) ? plan.keywords.join('\n') : form.keywordsText
  form.platforms = Array.isArray(plan.platforms) && plan.platforms.length
    ? normalizePlatformsForSubmit(plan.platforms, { expandAll: true })
    : defaultPlatformsForScope(scope)
  form.startDate = String(plan.start_date || form.startDate || '')
  form.endDate = String(plan.end_date || form.endDate || '')
  form.totalLimit = Number(plan.total_limit || form.totalLimit || 500)
  form.pageSize = Number(plan.page_size || form.pageSize || 50)
  form.sort = String(plan.sort || form.sort || 'comments_desc')
  form.infoType = String(plan.info_type || form.infoType || '2')
  form.dedupeByContent = Boolean(plan.dedupe_by_content ?? form.dedupeByContent)
  form.allocateByPlatform = Boolean(plan.allocate_by_platform ?? form.allocateByPlatform)
}

export function setNetInsightTaskScope(form, scope) {
  const normalized = normalizeScope(scope)
  form.scope = normalized
  form.platforms = defaultPlatformsForScope(normalized)
}

export function buildNetInsightTaskPayload(form, overrides = {}) {
  return {
    title: form.title,
    project: form.project,
    query: form.brief,
    summary: form.brief,
    scope: normalizeScope(form.scope),
    keywords: parseKeywords(form.keywordsText),
    platforms: normalizePlatformsForSubmit(form.platforms, { expandAll: true }),
    start_date: form.startDate,
    end_date: form.endDate,
    total_limit: Number(form.totalLimit || 500),
    page_size: Number(form.pageSize || 50),
    sort: form.sort,
    info_type: form.infoType,
    dedupe_by_content: form.dedupeByContent,
    allocate_by_platform: form.allocateByPlatform,
    ...overrides,
  }
}

export function isNetInsightTaskFormSubmittable(form) {
  if (!String(form.title || '').trim()) return false
  if (!form.startDate || !form.endDate) return false
  if (!parseKeywords(form.keywordsText).length) return false
  if (!normalizePlatformsForSubmit(form.platforms, { expandAll: true }).length) return false
  return true
}

export function parseKeywords(text) {
  return String(text || '')
    .split(/[\n,，;；、]+/)
    .map((item) => item.trim())
    .filter(Boolean)
}

export function normalizePlatformsForSubmit(values, { expandAll = false } = {}) {
  const list = Array.isArray(values) ? values.map((item) => String(item).trim()).filter(Boolean) : []
  if (list.includes('全部')) return expandAll ? defaultPlatformsForScope('global') : ['全部']
  return [...new Set(list)]
}

export function defaultPlatformsForScope(scope) {
  return [...(SCOPE_PLATFORM_PRESETS[normalizeScope(scope)] || SCOPE_PLATFORM_PRESETS.domestic)]
}

export function normalizeScope(scope) {
  return ['domestic', 'foreign', 'global'].includes(String(scope || '').trim())
    ? String(scope || '').trim()
    : 'domestic'
}

export function formatDateInput(value) {
  const date = value instanceof Date ? value : new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}
