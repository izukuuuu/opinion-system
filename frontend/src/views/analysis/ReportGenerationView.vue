<template>
  <div class="space-y-6 pb-12">
    <section class="card-surface space-y-5 p-6">
      <div class="flex flex-wrap items-center justify-between gap-3">
        <div class="space-y-1">
          <h2 class="text-xl font-semibold text-primary">查看结构化结果</h2>
          <p class="text-sm text-secondary">这里按结构化字段展开所有判断，并支持直接回链到引用索引。</p>
        </div>
        <div class="flex flex-wrap items-center gap-2">
          <button type="button" class="btn-secondary inline-flex items-center gap-2" :disabled="topicsState.loading" @click="loadTopics">
            <ArrowPathIcon class="h-4 w-4" :class="topicsState.loading ? 'animate-spin' : ''" />
            {{ topicsState.loading ? '刷新中…' : '刷新专题' }}
          </button>
          <button type="button" class="btn-secondary inline-flex items-center gap-2" @click="goToRunPage">
            <PlayCircleIcon class="h-4 w-4" />
            前往运行页
          </button>
          <button type="button" class="btn-secondary inline-flex items-center gap-2" :disabled="historyState.loading || !reportForm.topic" @click="handleRefreshHistory">
            <ClockIcon class="h-4 w-4" />
            {{ historyState.loading ? '读取中…' : '刷新记录' }}
          </button>
        </div>
      </div>

      <div class="grid gap-4 lg:grid-cols-[1.2fr,1fr,1fr,1fr]">
        <label class="space-y-2 text-secondary">
          <span class="text-xs font-semibold text-muted">专题</span>
          <AppSelect
            :options="topicSelectOptions"
            :value="reportForm.topic"
            :disabled="topicsState.loading || !topicOptions.length"
            @change="reportForm.topic = $event"
          />
          <p v-if="topicsState.error" class="text-xs text-danger">{{ topicsState.error }}</p>
        </label>

        <label class="space-y-2 text-secondary">
          <span class="text-xs font-semibold text-muted">历史记录</span>
          <AppSelect
            :options="historySelectOptions"
            :value="selectedHistoryId"
            :disabled="historyState.loading || !reportHistory.length"
            :placeholder="historyState.loading ? '加载历史中…' : reportHistory.length ? '选择历史记录' : '暂无历史记录'"
            @change="handleSelectHistory"
          />
        </label>

        <label class="space-y-2 text-secondary">
          <span class="text-xs font-semibold text-muted">开始日期</span>
          <input v-model="reportForm.start" type="date" class="input" />
        </label>

        <label class="space-y-2 text-secondary">
          <span class="text-xs font-semibold text-muted">结束日期</span>
          <input v-model="reportForm.end" type="date" class="input" />
        </label>
      </div>

      <div class="flex flex-wrap items-center justify-between gap-3 border-t border-soft pt-4">
        <p class="text-xs text-muted">
          建议范围：{{ availableRange.start || '--' }} → {{ availableRange.end || '--' }}
          <span v-if="availableRange.loading" class="ml-2 animate-pulse">检查中…</span>
          <span v-else-if="availableRange.error" class="ml-2 text-danger">{{ availableRange.error }}</span>
          <span v-else-if="availableRange.notice" class="ml-2 text-warning">{{ availableRange.notice }}</span>
        </p>
        <div class="flex flex-wrap items-center gap-2">
          <button type="button" class="btn-primary inline-flex items-center gap-2" :disabled="reportState.loading" @click="loadReport()">
            <ArrowPathIcon class="h-4 w-4" :class="reportState.loading ? 'animate-spin' : ''" />
            {{ reportState.loading ? '读取中…' : '读取结果' }}
          </button>
          <button type="button" class="btn-secondary inline-flex items-center gap-2" :disabled="!report" @click="exportJson">
            <ArrowDownTrayIcon class="h-4 w-4" />
            导出结果
          </button>
        </div>
      </div>

      <div v-if="reportState.error" class="rounded-2xl border border-danger/40 bg-danger-soft px-4 py-3 text-sm text-danger">
        {{ reportState.error }}
      </div>
    </section>

    <template v-if="report">
      <section class="grid gap-6 xl:grid-cols-[1.08fr,0.92fr]">
        <article class="card-surface space-y-5 p-6">
          <div class="space-y-2">
            <p class="text-xs font-semibold uppercase tracking-[0.24em] text-muted">报告概览</p>
            <h1 class="text-2xl font-semibold text-primary md:text-3xl">{{ reportTitle }}</h1>
            <p class="text-sm text-secondary">区间：{{ reportRange }}<span v-if="reportState.lastLoaded"> · 读取时间：{{ reportState.lastLoaded }}</span></p>
          </div>

          <div class="rounded-3xl border border-brand-soft bg-brand-soft/40 px-5 py-5">
            <p class="text-xs font-semibold uppercase tracking-[0.18em] text-muted">结论摘要</p>
            <p class="mt-3 text-sm leading-7 text-primary">{{ conclusion.executive_summary || '当前结果没有给出摘要。' }}</p>
            <div class="mt-3 flex flex-wrap gap-2">
              <span v-if="conclusion.confidence_label" class="rounded-full bg-surface px-3 py-1 text-xs font-semibold text-brand">整体把握：{{ conclusion.confidence_label }}</span>
              <span v-for="risk in conclusion.key_risks || []" :key="risk" class="rounded-full bg-warning-soft px-3 py-1 text-xs text-warning">{{ risk }}</span>
            </div>
          </div>

          <div class="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <article v-for="card in summaryCards" :key="card.label" class="rounded-3xl border border-soft bg-surface-muted/50 p-4">
              <p class="text-xs font-semibold uppercase tracking-[0.18em] text-muted">{{ card.label }}</p>
              <p class="mt-2 text-2xl font-semibold text-primary">{{ card.value }}</p>
            </article>
          </div>
        </article>

        <article class="card-surface space-y-4 p-6">
          <div>
            <p class="text-xs font-semibold uppercase tracking-[0.24em] text-muted">核心发现</p>
            <p class="text-sm text-secondary">适合先快速扫一遍结论，再决定是否下钻查看证据。</p>
          </div>
          <div v-if="conclusion.key_findings?.length" class="space-y-3">
            <article v-for="item in conclusion.key_findings" :key="item" class="rounded-3xl border border-soft bg-surface-muted/50 p-4">
              <p class="text-sm leading-7 text-primary">{{ item }}</p>
            </article>
          </div>
          <div v-else class="rounded-3xl border border-dashed border-soft px-4 py-8 text-sm text-secondary">
            当前结果没有单列核心发现。
          </div>
        </article>
      </section>

      <section class="grid gap-6 xl:grid-cols-[1fr,1fr]">
        <article v-for="section in collectionSections" :id="section.id" :key="section.id" class="card-surface space-y-4 p-6">
          <div>
            <p class="text-xs font-semibold uppercase tracking-[0.24em] text-muted">{{ section.kicker }}</p>
            <p class="text-sm text-secondary">{{ section.description }}</p>
          </div>
          <div v-if="section.items.length" class="space-y-3">
            <article v-for="item in section.items" :key="item.id" class="rounded-3xl border border-soft bg-surface-muted/40 p-4">
              <div class="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <p class="text-sm font-semibold text-primary">{{ item.title }}</p>
                  <p v-if="item.subtitle" class="mt-1 text-xs text-muted">{{ item.subtitle }}</p>
                </div>
                <div v-if="item.badges.length" class="flex flex-wrap gap-2">
                  <span v-for="badge in item.badges" :key="`${item.id}-${badge}`" class="rounded-full bg-base-soft px-3 py-1 text-xs text-secondary">
                    {{ badge }}
                  </span>
                </div>
              </div>
              <p v-if="item.description" class="mt-3 text-sm leading-7 text-secondary">{{ item.description }}</p>
              <div v-if="item.citations.length" class="mt-3 flex flex-wrap gap-2">
                <button
                  v-for="citation in item.citations"
                  :key="`${item.id}-${citation.citation_id}`"
                  type="button"
                  class="rounded-full border border-brand-soft bg-surface px-3 py-1 text-xs text-brand"
                  @click="scrollToCitation(citation.citation_id)"
                >
                  {{ citation.citation_id }}
                </button>
              </div>
            </article>
          </div>
          <div v-else class="rounded-3xl border border-dashed border-soft px-4 py-8 text-sm text-secondary">
            {{ section.emptyText }}
          </div>
        </article>
      </section>

      <section id="citations" class="card-surface space-y-4 p-6">
        <div class="flex items-center justify-between gap-3">
          <div>
            <p class="text-xs font-semibold uppercase tracking-[0.24em] text-muted">引用索引</p>
            <p class="text-sm text-secondary">所有回链按钮都会跳到这里，便于核对来源标题、时间和摘录。</p>
          </div>
          <span class="text-xs text-muted">{{ citations.length }} 条引用</span>
        </div>

        <div v-if="citations.length" class="space-y-3">
          <article v-for="item in citations" :id="citationAnchorId(item.citation_id)" :key="item.citation_id" class="rounded-3xl border border-soft bg-surface-muted/40 p-5">
            <div class="flex flex-wrap items-start justify-between gap-3">
              <div class="space-y-1">
                <div class="flex flex-wrap items-center gap-2">
                  <span class="rounded-full bg-brand-soft px-3 py-1 text-xs font-semibold text-brand">{{ item.citation_id }}</span>
                  <p class="text-sm font-semibold text-primary">{{ item.title || '未命名来源' }}</p>
                </div>
                <p class="text-xs text-muted">{{ [item.platform, item.published_at, item.source_type].filter(Boolean).join(' · ') || '来源信息未完整标注' }}</p>
              </div>
              <a v-if="item.url" :href="item.url" target="_blank" rel="noreferrer" class="rounded-full border border-soft px-3 py-1 text-xs text-secondary hover:bg-brand-soft hover:text-brand">
                打开来源
              </a>
            </div>
            <p v-if="item.snippet" class="mt-3 text-sm leading-7 text-secondary">{{ item.snippet }}</p>
          </article>
        </div>

        <div v-else class="rounded-3xl border border-dashed border-soft px-4 py-8 text-sm text-secondary">
          当前结果没有引用索引。
        </div>
      </section>
    </template>

    <section v-else class="card-surface p-6 text-sm text-secondary">
      请选择专题和时间范围，然后读取结构化结果。
    </section>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { ArrowDownTrayIcon, ArrowPathIcon, ClockIcon, PlayCircleIcon } from '@heroicons/vue/24/outline'
import AppSelect from '../../components/AppSelect.vue'
import { useReportGeneration } from '../../composables/useReportGeneration'

const router = useRouter()
const {
  topicsState,
  topicOptions,
  reportForm,
  availableRange,
  reportState,
  historyState,
  reportHistory,
  selectedHistoryId,
  reportData,
  loadTopics,
  loadHistory,
  loadReport,
  applyHistorySelection
} = useReportGeneration()

const report = computed(() => (reportData.value && typeof reportData.value === 'object' ? reportData.value : null))
const task = computed(() => report.value?.task || {})
const conclusion = computed(() => report.value?.conclusion || {})
const citations = computed(() => Array.isArray(report.value?.citations) ? report.value.citations : [])
const citationMap = computed(() => {
  const map = new Map()
  citations.value.forEach((item) => {
    const key = String(item?.citation_id || '').trim()
    if (key) map.set(key, item)
  })
  return map
})

const reportTitle = computed(() => task.value.topic_label || task.value.topic_identifier || '结构化结果')
const reportRange = computed(() => `${task.value.start || '--'} → ${task.value.end || '--'}`)

const topicSelectOptions = computed(() =>
  topicOptions.value.map(option => ({ value: option, label: option }))
)

const historySelectOptions = computed(() =>
  reportHistory.value.map(record => ({
    value: record.id,
    label: `${record.start} → ${record.end}`
  }))
)
const summaryCards = computed(() => [
  { label: '时间线节点', value: listOf(report.value?.timeline).length },
  { label: '主体数量', value: listOf(report.value?.subjects).length },
  { label: '证据数量', value: listOf(report.value?.key_evidence).length },
  { label: '引用数量', value: citations.value.length }
])

function listOf(value) {
  return Array.isArray(value) ? value : []
}

function citationsFor(ids = []) {
  return listOf(ids).map((id) => citationMap.value.get(String(id || '').trim())).filter(Boolean)
}

function normalizeItem(type, item) {
  const source = item && typeof item === 'object' ? item : {}
  const base = {
    id: String(source.id || source.event_id || source.subject_id || source.conflict_id || source.feature_id || source.risk_id || source.item_id || source.action_id || source.note_id || source.evidence_id || source.citation_id || Math.random()).trim(),
    title: '',
    subtitle: '',
    description: '',
    badges: [],
    citations: citationsFor(source.citation_ids)
  }
  if (type === 'timeline') {
    base.id = String(source.event_id || base.id)
    base.title = String(source.title || '时间线节点')
    base.subtitle = String(source.date || '')
    base.description = String(source.description || source.impact || '')
    base.badges = [source.trigger, source.impact].filter(Boolean)
  } else if (type === 'subjects') {
    base.id = String(source.subject_id || base.id)
    base.title = String(source.name || '主体')
    base.subtitle = String(source.summary || '')
    base.badges = [source.category, source.role].filter(Boolean)
  } else if (type === 'stance') {
    base.id = `${source.subject || ''}-${source.stance || ''}`
    base.title = String(source.subject || '主体')
    base.subtitle = String(source.stance || '')
    base.description = String(source.summary || '')
    base.badges = listOf(source.conflict_with).filter(Boolean)
  } else if (type === 'evidence') {
    base.id = String(source.evidence_id || base.id)
    base.title = String(source.finding || '证据块')
    base.subtitle = String(source.source_summary || '')
    base.description = ''
    base.badges = [source.subject, source.stance, source.time_label, source.confidence].filter(Boolean)
  } else if (type === 'conflicts') {
    base.id = String(source.conflict_id || base.id)
    base.title = String(source.title || '冲突点')
    base.subtitle = listOf(source.subjects).join(' · ')
    base.description = String(source.description || '')
  } else if (type === 'propagation') {
    base.id = String(source.feature_id || base.id)
    base.title = String(source.dimension || '传播特征')
    base.subtitle = String(source.finding || '')
    base.description = String(source.explanation || '')
  } else if (type === 'risks') {
    base.id = String(source.risk_id || base.id)
    base.title = String(source.label || '风险项')
    base.subtitle = String(source.level || '')
    base.description = String(source.summary || '')
  } else if (type === 'unverified') {
    base.id = String(source.item_id || base.id)
    base.title = String(source.statement || '待核验点')
    base.description = String(source.reason || '')
  } else if (type === 'actions') {
    base.id = String(source.action_id || base.id)
    base.title = String(source.action || '建议动作')
    base.subtitle = String(source.priority || '')
    base.description = String(source.rationale || '')
  } else if (type === 'validation') {
    base.id = String(source.note_id || base.id)
    base.title = String(source.message || '校验记录')
    base.subtitle = String(source.category || '')
    base.badges = [source.severity].filter(Boolean)
  }
  return base
}

const collectionSections = computed(() => [
  {
    id: 'timeline',
    kicker: '时间线',
    description: '按事件顺序整理出的关键节点与影响。',
    emptyText: '当前结果没有生成时间线。',
    items: listOf(report.value?.timeline).map((item) => normalizeItem('timeline', item))
  },
  {
    id: 'subjects',
    kicker: '主体列表',
    description: '本次结果涉及的主体与角色说明。',
    emptyText: '当前结果没有列出主体信息。',
    items: listOf(report.value?.subjects).map((item) => normalizeItem('subjects', item))
  },
  {
    id: 'stance',
    kicker: '立场矩阵',
    description: '用于查看主体观点与冲突关系。',
    emptyText: '当前结果没有生成立场矩阵。',
    items: listOf(report.value?.stance_matrix).map((item) => normalizeItem('stance', item))
  },
  {
    id: 'evidence',
    kicker: '关键证据',
    description: '统一整理后的证据块与对应回链。',
    emptyText: '当前结果没有列出关键证据。',
    items: listOf(report.value?.key_evidence).map((item) => normalizeItem('evidence', item))
  },
  {
    id: 'conflicts',
    kicker: '冲突点',
    description: '集中展示争议结构和涉及主体。',
    emptyText: '当前结果没有单独列出冲突点。',
    items: listOf(report.value?.conflict_points).map((item) => normalizeItem('conflicts', item))
  },
  {
    id: 'propagation',
    kicker: '传播特征',
    description: '补充平台差异、扩散节奏和关键节点解释。',
    emptyText: '当前结果没有传播特征说明。',
    items: listOf(report.value?.propagation_features).map((item) => normalizeItem('propagation', item))
  },
  {
    id: 'risks',
    kicker: '风险判断',
    description: '列出当前需要重点关注的风险。',
    emptyText: '当前结果没有独立的风险判断。',
    items: listOf(report.value?.risk_judgement).map((item) => normalizeItem('risks', item))
  },
  {
    id: 'unverified',
    kicker: '待核验点',
    description: '这些内容仍需要继续补充证据。',
    emptyText: '当前结果没有待核验点。',
    items: listOf(report.value?.unverified_points).map((item) => normalizeItem('unverified', item))
  },
  {
    id: 'actions',
    kicker: '建议动作',
    description: '基于当前结论给出的下一步建议。',
    emptyText: '当前结果没有生成建议动作。',
    items: listOf(report.value?.suggested_actions).map((item) => normalizeItem('actions', item))
  },
  {
    id: 'validation',
    kicker: '校验记录',
    description: '记录事实、时间与主体维度的检查结果。',
    emptyText: '当前结果没有返回独立的校验记录。',
    items: listOf(report.value?.validation_notes).map((item) => normalizeItem('validation', item))
  }
])

function citationAnchorId(citationId) {
  return `citation-${String(citationId || '').trim()}`
}

function scrollToCitation(citationId) {
  const element = document.getElementById(citationAnchorId(citationId))
  if (!element) return
  element.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

async function handleSelectHistory(historyId) {
  if (!historyId) return
  await applyHistorySelection(historyId, { shouldLoad: true })
}

async function handleRefreshHistory() {
  await loadHistory(reportForm.topic)
}

function goToRunPage() {
  router.push({ name: 'report-generation-run' })
}

function exportJson() {
  if (!report.value) return
  const blob = new Blob([JSON.stringify(report.value, null, 2)], { type: 'application/json;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `${reportTitle.value || 'structured-report'}.json`
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  URL.revokeObjectURL(url)
}
</script>
