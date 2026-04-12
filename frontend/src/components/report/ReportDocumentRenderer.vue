<template>
  <div class="space-y-6">
    <section v-if="showHero && hero.title" class="card-surface space-y-5 p-6">
      <div class="space-y-2">
        <p class="text-xs font-semibold uppercase tracking-[0.24em] text-muted">报告概览</p>
        <h1 class="text-2xl font-semibold text-primary md:text-3xl">{{ hero.title }}</h1>
        <p v-if="hero.subtitle" class="text-sm text-secondary">{{ hero.subtitle }}</p>
      </div>

      <div class="rounded-3xl border border-brand-soft bg-brand-soft/40 px-5 py-5">
        <p class="text-xs font-semibold uppercase tracking-[0.18em] text-muted">结论摘要</p>
        <p class="mt-3 text-sm leading-7 text-primary">{{ hero.summary || '当前结果没有独立摘要。' }}</p>
        <div v-if="hero.risks?.length" class="mt-3 flex flex-wrap gap-2">
          <span v-for="risk in hero.risks" :key="risk" class="rounded-full bg-warning-soft px-3 py-1 text-xs text-warning">
            {{ risk }}
          </span>
        </div>
      </div>

      <div v-if="hero.metrics?.length" class="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <article v-for="metric in hero.metrics" :key="metric.metric_id || metric.label" class="rounded-3xl border border-soft bg-surface-muted/50 p-4">
          <p class="text-xs font-semibold uppercase tracking-[0.18em] text-muted">{{ metric.label }}</p>
          <p class="mt-2 text-2xl font-semibold text-primary">{{ metric.value || '--' }}</p>
          <p v-if="metric.detail" class="mt-1 text-xs text-muted">{{ metric.detail }}</p>
        </article>
      </div>

      <div v-if="hero.highlights?.length" class="space-y-3">
        <p class="text-xs font-semibold uppercase tracking-[0.18em] text-muted">核心发现</p>
        <article v-for="item in hero.highlights" :key="item" class="rounded-3xl border border-soft bg-surface-muted/50 p-4">
          <p class="text-sm leading-7 text-primary">{{ item }}</p>
        </article>
      </div>
    </section>

    <section
      v-for="section in sections"
      :id="section.section_id"
      :key="section.section_id"
      class="card-surface space-y-6 p-6"
    >
      <header class="space-y-2">
        <p v-if="section.kicker" class="text-xs font-semibold uppercase tracking-[0.24em] text-muted">{{ section.kicker }}</p>
        <h2 class="text-xl font-semibold text-primary">{{ section.title }}</h2>
        <p v-if="section.summary" class="max-w-3xl text-sm leading-7 text-secondary">{{ section.summary }}</p>
      </header>

      <template v-for="block in section.blocks" :key="block.block_id">
        <section v-if="block.type === 'narrative'" class="rounded-3xl border border-soft bg-surface-muted/30 p-5">
          <p v-if="block.title" class="text-xs font-semibold uppercase tracking-[0.18em] text-muted">{{ block.title }}</p>
          <p class="mt-3 text-sm leading-7 text-primary">{{ block.content || '当前区块暂无正文内容。' }}</p>
          <div v-if="block.citation_ids?.length" class="mt-3 flex flex-wrap gap-2">
            <a
              v-for="citationId in block.citation_ids"
              :key="`${block.block_id}-${citationId}`"
              class="rounded-full border border-brand-soft bg-surface px-3 py-1 text-xs text-brand"
              :href="`#${citationAnchorId(citationId)}`"
            >
              {{ citationId }}
            </a>
          </div>
        </section>

        <section v-else-if="block.type === 'bullets'" class="rounded-3xl border border-soft bg-surface-muted/30 p-5">
          <p v-if="block.title" class="text-xs font-semibold uppercase tracking-[0.18em] text-muted">{{ block.title }}</p>
          <ul class="mt-3 space-y-2 text-sm text-secondary">
            <li v-for="item in block.items || []" :key="item" class="rounded-2xl border border-soft bg-surface px-4 py-3 leading-7">
              {{ item }}
            </li>
          </ul>
          <p v-if="!(block.items || []).length" class="mt-3 text-sm text-muted">当前区块暂无要点。</p>
        </section>

        <section v-else-if="block.type === 'figure_ref'" class="space-y-4">
          <ChartFigure v-if="resolveFigure(block.figure_id)" :contract="resolveFigure(block.figure_id)" />
          <div v-else class="rounded-3xl border border-dashed border-soft px-4 py-8 text-sm text-secondary">
            当前区块没有可展示的图表。
          </div>
        </section>

        <section v-else-if="block.type === 'evidence_list'" class="space-y-3 rounded-3xl border border-soft bg-surface-muted/30 p-5">
          <p class="text-xs font-semibold uppercase tracking-[0.18em] text-muted">{{ block.title || '关键证据' }}</p>
          <article v-for="item in resolveEvidence(block.evidence_ids)" :key="item.evidence_id" class="rounded-3xl border border-soft bg-surface p-4">
            <p class="text-sm font-semibold text-primary">{{ item.finding }}</p>
            <p v-if="item.source_summary" class="mt-2 text-sm leading-7 text-secondary">{{ item.source_summary }}</p>
            <div class="mt-3 flex flex-wrap gap-2">
              <span v-for="badge in [item.subject, item.stance, item.time_label, item.confidence].filter(Boolean)" :key="`${item.evidence_id}-${badge}`" class="rounded-full bg-base-soft px-3 py-1 text-xs text-secondary">
                {{ badge }}
              </span>
            </div>
            <div v-if="item.citation_ids?.length" class="mt-3 flex flex-wrap gap-2">
              <a v-for="citationId in item.citation_ids" :key="`${item.evidence_id}-${citationId}`" class="rounded-full border border-brand-soft bg-surface px-3 py-1 text-xs text-brand" :href="`#${citationAnchorId(citationId)}`">
                {{ citationId }}
              </a>
            </div>
          </article>
          <p v-if="!resolveEvidence(block.evidence_ids).length" class="text-sm text-muted">当前区块没有可展示的证据。</p>
        </section>

        <section v-else-if="block.type === 'timeline_list'" class="space-y-3 rounded-3xl border border-soft bg-surface-muted/30 p-5">
          <p class="text-xs font-semibold uppercase tracking-[0.18em] text-muted">{{ block.title || '关键节点' }}</p>
          <article v-for="item in resolveTimeline(block.event_ids)" :key="item.event_id" class="rounded-3xl border border-soft bg-surface p-4">
            <div class="flex flex-wrap items-start justify-between gap-3">
              <div>
                <p class="text-sm font-semibold text-primary">{{ item.title }}</p>
                <p v-if="item.date" class="mt-1 text-xs text-muted">{{ item.date }}</p>
              </div>
              <div class="flex flex-wrap gap-2">
                <span v-for="badge in [item.trigger, item.impact].filter(Boolean)" :key="`${item.event_id}-${badge}`" class="rounded-full bg-base-soft px-3 py-1 text-xs text-secondary">
                  {{ badge }}
                </span>
              </div>
            </div>
            <p v-if="item.description" class="mt-3 text-sm leading-7 text-secondary">{{ item.description }}</p>
            <div v-if="item.citation_ids?.length" class="mt-3 flex flex-wrap gap-2">
              <a v-for="citationId in item.citation_ids" :key="`${item.event_id}-${citationId}`" class="rounded-full border border-brand-soft bg-surface px-3 py-1 text-xs text-brand" :href="`#${citationAnchorId(citationId)}`">
                {{ citationId }}
              </a>
            </div>
          </article>
          <p v-if="!resolveTimeline(block.event_ids).length" class="text-sm text-muted">当前区块没有可展示的时间线。</p>
        </section>

        <section v-else-if="block.type === 'subject_cards'" class="space-y-3 rounded-3xl border border-soft bg-surface-muted/30 p-5">
          <p class="text-xs font-semibold uppercase tracking-[0.18em] text-muted">{{ block.title || '主体列表' }}</p>
          <div class="grid gap-3 xl:grid-cols-2">
            <article v-for="item in resolveSubjects(block.subject_ids)" :key="item.subject_id" class="rounded-3xl border border-soft bg-surface p-4">
              <div class="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <p class="text-sm font-semibold text-primary">{{ item.name }}</p>
                  <p v-if="item.summary" class="mt-1 text-xs text-muted">{{ item.summary }}</p>
                </div>
                <div class="flex flex-wrap gap-2">
                  <span v-for="badge in [item.category, item.role].filter(Boolean)" :key="`${item.subject_id}-${badge}`" class="rounded-full bg-base-soft px-3 py-1 text-xs text-secondary">
                    {{ badge }}
                  </span>
                </div>
              </div>
              <div v-if="item.citation_ids?.length" class="mt-3 flex flex-wrap gap-2">
                <a v-for="citationId in item.citation_ids" :key="`${item.subject_id}-${citationId}`" class="rounded-full border border-brand-soft bg-surface px-3 py-1 text-xs text-brand" :href="`#${citationAnchorId(citationId)}`">
                  {{ citationId }}
                </a>
              </div>
            </article>
          </div>
          <p v-if="!resolveSubjects(block.subject_ids).length" class="text-sm text-muted">当前区块没有可展示的主体。</p>
        </section>

        <section v-else-if="block.type === 'stance_matrix'" class="space-y-3 rounded-3xl border border-soft bg-surface-muted/30 p-5">
          <p class="text-xs font-semibold uppercase tracking-[0.18em] text-muted">{{ block.title || '立场矩阵' }}</p>
          <div class="overflow-hidden rounded-2xl border border-soft">
            <table class="min-w-full text-sm">
              <thead class="bg-surface-muted text-xs uppercase tracking-wide text-muted">
                <tr>
                  <th class="px-3 py-2 text-left">主体</th>
                  <th class="px-3 py-2 text-left">立场</th>
                  <th class="px-3 py-2 text-left">说明</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="item in resolveStance(block.subject_names)" :key="`${item.subject}-${item.stance}`" class="border-t border-soft text-secondary">
                  <td class="px-3 py-3 font-medium text-primary">{{ item.subject }}</td>
                  <td class="px-3 py-3">{{ item.stance || '--' }}</td>
                  <td class="px-3 py-3">{{ item.summary || '--' }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>

        <section v-else-if="block.type === 'risk_list'" class="space-y-3 rounded-3xl border border-soft bg-surface-muted/30 p-5">
          <p class="text-xs font-semibold uppercase tracking-[0.18em] text-muted">{{ block.title || '风险判断' }}</p>
          <article v-for="item in resolveRisks(block.risk_ids)" :key="item.risk_id" class="rounded-3xl border border-soft bg-surface p-4">
            <div class="flex flex-wrap items-start justify-between gap-3">
              <div>
                <p class="text-sm font-semibold text-primary">{{ item.label }}</p>
                <p v-if="item.summary" class="mt-2 text-sm leading-7 text-secondary">{{ item.summary }}</p>
              </div>
              <span class="rounded-full bg-warning-soft px-3 py-1 text-xs text-warning">{{ item.level || 'medium' }}</span>
            </div>
          </article>
          <p v-if="!resolveRisks(block.risk_ids).length" class="text-sm text-muted">当前区块没有可展示的风险。</p>
        </section>

        <section v-else-if="block.type === 'action_list'" class="space-y-3 rounded-3xl border border-soft bg-surface-muted/30 p-5">
          <p class="text-xs font-semibold uppercase tracking-[0.18em] text-muted">{{ block.title || '建议动作' }}</p>
          <article v-for="item in resolveActions(block.action_ids)" :key="item.action_id" class="rounded-3xl border border-soft bg-surface p-4">
            <div class="flex flex-wrap items-start justify-between gap-3">
              <div>
                <p class="text-sm font-semibold text-primary">{{ item.action }}</p>
                <p v-if="item.rationale" class="mt-2 text-sm leading-7 text-secondary">{{ item.rationale }}</p>
              </div>
              <span class="rounded-full bg-brand-soft px-3 py-1 text-xs text-brand">{{ item.priority || 'medium' }}</span>
            </div>
          </article>
          <p v-if="!resolveActions(block.action_ids).length" class="text-sm text-muted">当前区块没有可展示的建议动作。</p>
        </section>

        <section v-else-if="block.type === 'citation_refs'" class="space-y-4">
          <div class="space-y-1">
            <p class="text-xs font-semibold uppercase tracking-[0.18em] text-muted">{{ block.title || '引用索引' }}</p>
            <p class="text-sm text-secondary">可直接核对来源标题、时间和摘录。</p>
          </div>
          <article v-for="item in resolveCitations(block.citation_ids)" :id="citationAnchorId(item.citation_id)" :key="item.citation_id" class="rounded-3xl border border-soft bg-surface-muted/40 p-5">
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
          <p v-if="!resolveCitations(block.citation_ids).length" class="text-sm text-muted">当前区块没有可展示的引用。</p>
        </section>

        <section v-else-if="block.type === 'callout'" class="rounded-3xl border p-5" :class="calloutClass(block.tone)">
          <p v-if="block.title" class="text-xs font-semibold uppercase tracking-[0.18em]">{{ block.title }}</p>
          <p class="mt-3 text-sm leading-7">{{ block.content || '当前提示区块没有内容。' }}</p>
        </section>
      </template>
    </section>

    <section v-if="appendix.blocks?.length" id="report-appendix" class="card-surface space-y-6 p-6">
      <header class="space-y-1">
        <p class="text-xs font-semibold uppercase tracking-[0.24em] text-muted">附录</p>
        <h2 class="text-xl font-semibold text-primary">{{ appendix.title || '引用与校验' }}</h2>
      </header>
      <template v-for="block in appendix.blocks" :key="block.block_id">
        <section v-if="block.type === 'citation_refs'" class="space-y-4">
          <div class="space-y-1">
            <p class="text-xs font-semibold uppercase tracking-[0.18em] text-muted">{{ block.title || '引用索引' }}</p>
          </div>
          <article v-for="item in resolveCitations(block.citation_ids)" :id="citationAnchorId(item.citation_id)" :key="item.citation_id" class="rounded-3xl border border-soft bg-surface-muted/40 p-5">
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
          <p v-if="!resolveCitations(block.citation_ids).length" class="text-sm text-muted">当前区块没有可展示的引用。</p>
        </section>
        <section v-else-if="block.type === 'callout'" class="rounded-3xl border p-5" :class="calloutClass(block.tone)">
          <p v-if="block.title" class="text-xs font-semibold uppercase tracking-[0.18em]">{{ block.title }}</p>
          <p class="mt-3 text-sm leading-7">{{ block.content || '当前提示区块没有内容。' }}</p>
        </section>
      </template>
    </section>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import ChartFigure from './ChartFigure.vue'
import { buildFigureContractMap } from '../../utils/reportFigures'

const props = defineProps({
  document: {
    type: Object,
    default: () => ({})
  },
  reportIr: {
    type: Object,
    default: () => ({})
  },
  artifactManifest: {
    type: Object,
    default: () => ({})
  },
  reportData: {
    type: Object,
    default: () => ({})
  },
  showHero: {
    type: Boolean,
    default: true
  }
})

const hero = computed(() => (props.document && typeof props.document.hero === 'object' ? props.document.hero : {}))
const sections = computed(() => Array.isArray(props.document?.sections) ? props.document.sections : [])
const appendix = computed(() => (props.document && typeof props.document.appendix === 'object' ? props.document.appendix : { blocks: [] }))

const figureMap = computed(() => buildFigureContractMap(props.reportIr, props.artifactManifest))

const evidenceMap = computed(() => new Map((Array.isArray(props.reportData?.key_evidence) ? props.reportData.key_evidence : []).map((item) => [String(item?.evidence_id || '').trim(), item])))
const timelineMap = computed(() => new Map((Array.isArray(props.reportData?.timeline) ? props.reportData.timeline : []).map((item) => [String(item?.event_id || '').trim(), item])))
const subjectMap = computed(() => new Map((Array.isArray(props.reportData?.subjects) ? props.reportData.subjects : []).map((item) => [String(item?.subject_id || '').trim(), item])))
const stanceRows = computed(() => Array.isArray(props.reportData?.stance_matrix) ? props.reportData.stance_matrix : [])
const riskMap = computed(() => new Map((Array.isArray(props.reportData?.risk_judgement) ? props.reportData.risk_judgement : []).map((item) => [String(item?.risk_id || '').trim(), item])))
const actionMap = computed(() => new Map((Array.isArray(props.reportData?.suggested_actions) ? props.reportData.suggested_actions : []).map((item) => [String(item?.action_id || '').trim(), item])))
const citationMap = computed(() => new Map((Array.isArray(props.reportData?.citations) ? props.reportData.citations : []).map((item) => [String(item?.citation_id || '').trim(), item])))

function resolveFigure(id = '') {
  return figureMap.value.get(String(id || '').trim()) || null
}

function resolveEvidence(ids = []) {
  return (Array.isArray(ids) ? ids : []).map((id) => evidenceMap.value.get(String(id || '').trim())).filter(Boolean)
}

function resolveTimeline(ids = []) {
  return (Array.isArray(ids) ? ids : []).map((id) => timelineMap.value.get(String(id || '').trim())).filter(Boolean)
}

function resolveSubjects(ids = []) {
  return (Array.isArray(ids) ? ids : []).map((id) => subjectMap.value.get(String(id || '').trim())).filter(Boolean)
}

function resolveStance(subjectNames = []) {
  const names = new Set((Array.isArray(subjectNames) ? subjectNames : []).map((item) => String(item || '').trim()).filter(Boolean))
  if (!names.size) return stanceRows.value
  return stanceRows.value.filter((item) => names.has(String(item?.subject || '').trim()))
}

function resolveRisks(ids = []) {
  return (Array.isArray(ids) ? ids : []).map((id) => riskMap.value.get(String(id || '').trim())).filter(Boolean)
}

function resolveActions(ids = []) {
  return (Array.isArray(ids) ? ids : []).map((id) => actionMap.value.get(String(id || '').trim())).filter(Boolean)
}

function resolveCitations(ids = []) {
  return (Array.isArray(ids) ? ids : []).map((id) => citationMap.value.get(String(id || '').trim())).filter(Boolean)
}

function citationAnchorId(citationId) {
  return `citation-${String(citationId || '').trim()}`
}

function calloutClass(tone) {
  if (tone === 'danger') return 'border-danger/40 bg-danger-soft text-danger'
  if (tone === 'warning') return 'border-warning/40 bg-warning-soft text-warning'
  return 'border-brand-soft bg-brand-soft/30 text-primary'
}
</script>
