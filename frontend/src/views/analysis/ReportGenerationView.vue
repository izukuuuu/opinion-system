<template>
  <div class="space-y-6 pb-12">
    <section class="card-surface space-y-5 p-6">
      <div class="flex flex-wrap items-center justify-between gap-3">
        <h2 class="text-xl font-semibold text-primary">查看报告</h2>
        <div class="flex flex-wrap items-center gap-2">
          <button
            type="button"
            class="btn-secondary inline-flex items-center gap-2"
            :disabled="topicsState.loading"
            @click="loadTopics"
          >
            <ArrowPathIcon class="h-4 w-4" :class="topicsState.loading ? 'animate-spin' : ''" />
            {{ topicsState.loading ? '同步中…' : '刷新专题' }}
          </button>
          <button
            type="button"
            class="btn-secondary inline-flex items-center gap-2"
            @click="goToRunPage"
          >
            <PlayCircleIcon class="h-4 w-4" />
            前往运行页
          </button>
          <button
            type="button"
            class="btn-secondary inline-flex items-center gap-2"
            :disabled="historyState.loading || !reportForm.topic"
            @click="handleRefreshHistory"
          >
            <ClockIcon class="h-4 w-4" />
            {{ historyState.loading ? '加载中…' : '刷新记录' }}
          </button>
        </div>
      </div>

      <div class="grid gap-4 lg:grid-cols-[1.2fr,1fr,1fr,1fr]">
        <label class="space-y-2 text-secondary">
          <span class="text-xs font-semibold text-muted">专题 (Topic)</span>
          <select
            v-model="reportForm.topic"
            class="input"
            :disabled="topicsState.loading || !topicOptions.length"
            required
          >
            <option value="" disabled>请选择专题</option>
            <option v-for="option in topicOptions" :key="`report-topic-${option}`" :value="option">
              {{ option }}
            </option>
          </select>
          <p v-if="topicsState.error" class="text-xs text-danger">{{ topicsState.error }}</p>
        </label>

        <label class="space-y-2 text-secondary">
          <span class="text-xs font-semibold text-muted">历史记录</span>
          <select
            :value="selectedHistoryId"
            class="input"
            :disabled="historyState.loading || !reportHistory.length"
            @change="handleSelectHistory"
          >
            <option value="" disabled>
              {{ historyState.loading ? '加载历史中…' : reportHistory.length ? '选择历史记录' : '暂无历史记录' }}
            </option>
            <option v-for="record in reportHistory" :key="record.id" :value="record.id">
              {{ record.start }} → {{ record.end }}
            </option>
          </select>
          <p v-if="historyState.error" class="text-xs text-muted">{{ historyState.error }}</p>
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
          <span v-else-if="availableRange.notice" class="ml-2 text-amber-600">{{ availableRange.notice }}</span>
        </p>
        <div class="flex flex-wrap items-center gap-2">
          <button
            type="button"
            class="btn-secondary inline-flex items-center gap-2"
            :disabled="reportState.loading"
            @click="loadReport()"
          >
            <ArrowPathIcon class="h-4 w-4" :class="reportState.loading ? 'animate-spin' : ''" />
            {{ reportState.loading ? '读取中…' : '读取报告' }}
          </button>
          <button
            type="button"
            class="btn-secondary inline-flex items-center gap-2"
            :disabled="exporting || !report"
            @click="exportHtmlReport"
          >
            <ArrowDownTrayIcon class="h-4 w-4" />
            {{ exporting ? '导出中…' : '导出报告 HTML' }}
          </button>
        </div>
      </div>

      <div v-if="reportState.error" class="rounded-2xl border border-danger/40 bg-danger-soft px-4 py-3 text-sm text-danger">
        {{ reportState.error }}
      </div>
    </section>

    <section v-if="report" class="card-surface space-y-6 p-6">
      <header class="space-y-2">
        <p class="text-xs font-semibold uppercase tracking-[0.25em] text-muted">报告概览</p>
        <h1 class="text-2xl font-semibold text-primary md:text-3xl">{{ reportMeta.title }}</h1>
        <p class="text-sm text-secondary">{{ reportMeta.subtitle }}</p>
        <p class="text-xs text-muted">
          {{ reportMeta.rangeText }} · 最近更新：{{ reportMeta.lastUpdated }}
          <span v-if="reportState.lastLoaded"> · 前端读取：{{ reportState.lastLoaded }}</span>
        </p>
      </header>

      <div class="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <article class="rounded-2xl border border-soft bg-surface p-4">
          <p class="text-xs font-semibold uppercase tracking-[0.2em] text-muted">总声量</p>
          <p class="mt-2 text-3xl font-semibold text-primary">{{ formatNumber(metrics.totalVolume) }}</p>
        </article>

        <article class="rounded-2xl border border-soft bg-surface p-4">
          <p class="text-xs font-semibold uppercase tracking-[0.2em] text-muted">峰值</p>
          <p class="mt-2 text-xl font-semibold text-primary">{{ formatNumber(metrics.peak.value) }}</p>
          <p class="text-sm text-secondary">{{ metrics.peak.date || '未提供' }}</p>
        </article>

        <article class="rounded-2xl border border-soft bg-surface p-4">
          <p class="text-xs font-semibold uppercase tracking-[0.2em] text-muted">情感结构</p>
          <p class="mt-2 text-base font-semibold text-primary">正向 {{ formatRate(metrics.positiveRate) }}</p>
          <p class="text-sm text-secondary">中性 {{ formatRate(metrics.neutralRate) }} · 负向 {{ formatRate(metrics.negativeRate) }}</p>
        </article>

        <article class="rounded-2xl border border-soft bg-surface p-4">
          <p class="text-xs font-semibold uppercase tracking-[0.2em] text-muted">内容结构</p>
          <p class="mt-2 text-base font-semibold text-primary">报道 {{ formatRate(metrics.factualRatio) }}</p>
          <p class="text-sm text-secondary">观点 {{ formatRate(metrics.opinionRatio) }}</p>
        </article>
      </div>
    </section>

    <template v-if="report">
      <section class="card-surface space-y-5 p-6">
        <header class="space-y-3">
          <div class="flex flex-wrap items-center justify-between gap-3">
            <div class="space-y-1">
              <p class="text-xs font-semibold uppercase tracking-[0.25em] text-muted">基础分析总览</p>
              <h3 class="text-lg font-semibold text-primary">基础分析已压缩进报告结构</h3>
            </div>
            <p class="text-xs text-muted">
              <span v-if="analysisState.loading">基础分析结果加载中…</span>
              <span v-else-if="analysisState.lastLoaded">图表读取：{{ analysisState.lastLoaded }}</span>
              <span v-else>图表来自 `/api/analyze/results`</span>
            </p>
          </div>

          <div class="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
            <article
              v-for="item in sourceReadinessItems"
              :key="item.id"
              class="rounded-2xl border p-4"
              :class="item.ready ? 'border-brand-soft bg-brand-soft/10' : 'border-soft bg-surface'"
            >
              <div class="flex items-center justify-between gap-2">
                <p class="text-sm font-semibold text-primary">{{ item.label }}</p>
                <span
                  class="rounded-full px-2.5 py-1 text-[11px] font-semibold"
                  :class="item.ready ? 'bg-brand-soft/40 text-brand-700' : 'bg-surface-muted text-muted'"
                >
                  {{ item.ready ? '已接入' : '待补齐/缺失' }}
                </span>
              </div>
              <p class="mt-2 text-xs leading-6 text-secondary">{{ item.detail }}</p>
            </article>
          </div>

          <div v-if="analysisMainFinding" class="rounded-2xl border border-brand-soft bg-brand-soft/10 px-4 py-4">
            <div class="flex items-start gap-3">
              <span class="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-brand-600/10 text-brand-600">
                <SparklesIcon class="h-4 w-4" />
              </span>
              <div class="space-y-1.5">
                <p class="text-xs font-semibold uppercase tracking-[0.25em] text-brand-700">AI 主要发现</p>
                <p class="text-sm leading-7 text-primary">{{ analysisMainFinding.summary }}</p>
                <p v-if="analysisMainFinding.sourceFunctions.length" class="text-xs text-muted">
                  依据模块：{{ analysisMainFinding.sourceFunctions.join('、') }}
                </p>
              </div>
            </div>
          </div>
        </header>

        <div v-if="analysisState.loading" class="rounded-2xl border border-dashed border-soft bg-surface px-4 py-8 text-center text-sm text-muted">
          正在读取基础分析图表…
        </div>
        <div v-else-if="analysisState.error" class="rounded-2xl border border-danger/40 bg-danger-soft px-4 py-3 text-sm text-danger">
          {{ analysisState.error }}
        </div>
        <div v-else-if="analysisOverviewCards.length" class="grid gap-4 xl:grid-cols-2">
          <article
            v-for="card in analysisOverviewCards"
            :key="card.name"
            :id="card.anchorId"
            class="rounded-2xl border border-soft bg-surface p-5"
          >
            <div class="flex flex-wrap items-start justify-between gap-3">
              <div class="flex items-center gap-3">
                <span class="flex h-10 w-10 items-center justify-center rounded-full bg-brand-600/10 text-brand-600">
                  <component :is="getAnalysisSectionIcon(card.name)" class="h-5 w-5" />
                </span>
                <div>
                  <h4 class="text-base font-semibold text-primary">{{ card.label }}</h4>
                  <p class="text-sm text-secondary">{{ card.description }}</p>
                </div>
              </div>
              <span
                class="rounded-full border px-3 py-1 text-xs font-semibold"
                :class="getNarrativeSourceClass(card.source)"
              >
                {{ getNarrativeSourceLabel(card.source) }}
              </span>
            </div>

            <p class="mt-4 text-sm leading-7 text-primary">
              {{ card.summary || '暂无综合摘要。' }}
            </p>

            <AnalysisChartPanel
              class="mt-4"
              :title="card.primaryTarget.title"
              :description="card.primaryTarget.subtitle"
              :option="card.primaryTarget.option"
              :has-data="card.primaryTarget.hasData"
            />

            <div class="mt-4 grid gap-4 lg:grid-cols-[0.95fr,1.05fr]">
              <div class="rounded-2xl border border-soft">
                <table class="min-w-full text-sm">
                  <thead class="bg-surface-muted text-xs uppercase tracking-wide text-muted">
                    <tr>
                      <th class="px-3 py-2 text-left">名称</th>
                      <th class="px-3 py-2 text-left">数值</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr
                      v-for="(row, index) in card.rows"
                      :key="`${card.name}-${index}`"
                      class="border-t border-soft text-secondary"
                    >
                      <td class="px-3 py-2">{{ formatRowName(row) }}</td>
                      <td class="px-3 py-2">{{ formatRowValue(row) }}</td>
                    </tr>
                  </tbody>
                </table>
              </div>

              <div class="rounded-2xl border border-soft bg-surface-muted/60 p-4">
                <p class="text-xs font-semibold uppercase tracking-[0.2em] text-muted">综合解读</p>
                <p class="mt-3 text-sm leading-7 text-secondary">
                  {{ card.explainText || card.summary || '暂无综合解读。' }}
                </p>
              </div>
            </div>
          </article>
        </div>
        <p v-else class="text-sm text-muted">当前报告对应区间暂无基础分析图表，请先执行 analyze。</p>
      </section>

      <section class="grid gap-6 xl:grid-cols-[1.2fr,1fr,1fr]">
        <article class="card-surface space-y-4 p-5">
          <header>
            <p class="text-xs font-semibold uppercase tracking-[0.25em] text-muted">解释与研判</p>
            <h3 class="text-lg font-semibold text-primary">AI 深度研判</h3>
          </header>

          <p class="text-sm leading-7 text-secondary">
            {{ deepAnalysis.narrativeSummary || '暂无结构化研判摘要。请重新生成报告以补齐该区块。' }}
          </p>

          <div v-if="deepAnalysis.eventType || deepAnalysis.domain || deepAnalysis.stage" class="flex flex-wrap gap-2">
            <span
              v-if="deepAnalysis.eventType"
              class="rounded-full border border-brand-soft bg-brand-soft/20 px-3 py-1 text-xs font-semibold text-brand-700"
            >
              事件类型 · {{ deepAnalysis.eventType }}
            </span>
            <span
              v-if="deepAnalysis.domain"
              class="rounded-full border border-soft bg-surface px-3 py-1 text-xs font-semibold text-secondary"
            >
              领域 · {{ deepAnalysis.domain }}
            </span>
            <span
              v-if="deepAnalysis.stage"
              class="rounded-full border border-amber-200 bg-amber-50 px-3 py-1 text-xs font-semibold text-amber-700"
            >
              阶段 · {{ deepAnalysis.stage }}
            </span>
          </div>

          <div v-if="deepAnalysis.indicatorDimensions.length || deepAnalysis.theoryNames.length" class="grid gap-3 md:grid-cols-2">
            <div v-if="deepAnalysis.indicatorDimensions.length" class="space-y-2">
              <p class="text-xs font-semibold uppercase tracking-[0.2em] text-muted">持续观察维度</p>
              <div class="flex flex-wrap gap-2">
                <span
                  v-for="dimension in deepAnalysis.indicatorDimensions"
                  :key="`deep-dimension-${dimension}`"
                  class="rounded-full border border-soft bg-surface px-3 py-1 text-xs text-secondary"
                >
                  {{ dimension }}
                </span>
              </div>
            </div>
            <div v-if="deepAnalysis.theoryNames.length" class="space-y-2">
              <p class="text-xs font-semibold uppercase tracking-[0.2em] text-muted">理论锚点</p>
              <div class="flex flex-wrap gap-2">
                <span
                  v-for="theory in deepAnalysis.theoryNames"
                  :key="`deep-theory-${theory}`"
                  class="rounded-full border border-soft bg-surface px-3 py-1 text-xs text-secondary"
                >
                  {{ theory }}
                </span>
              </div>
            </div>
          </div>

          <div v-if="deepAnalysis.referenceLinks.length" class="space-y-2 border-t border-soft pt-3">
            <p class="text-xs font-semibold uppercase tracking-[0.2em] text-muted">外部参考入口</p>
            <div class="space-y-2 text-sm">
              <a
                v-for="link in deepAnalysis.referenceLinks"
                :key="`deep-link-${link.name}-${link.url}`"
                :href="link.url"
                target="_blank"
                rel="noreferrer"
                class="block rounded-2xl border border-soft bg-surface px-3 py-2 text-secondary transition hover:border-brand-300 hover:text-brand-700"
              >
                <span class="font-semibold text-primary">{{ link.name }}</span>
                <span v-if="link.usage" class="ml-2 text-xs text-muted">{{ link.usage }}</span>
              </a>
            </div>
          </div>
        </article>

        <article class="card-surface space-y-3 p-5">
          <header>
            <p class="text-xs font-semibold uppercase tracking-[0.25em] text-muted">关键事件</p>
            <h3 class="text-lg font-semibold text-primary">阶段节点</h3>
          </header>
          <ul v-if="deepAnalysis.keyEvents.length" class="space-y-3 text-sm text-secondary">
            <li
              v-for="(event, index) in deepAnalysis.keyEvents"
              :key="`deep-event-${index}`"
              class="flex gap-2 rounded-2xl border border-soft bg-surface p-3"
            >
              <span class="mt-[7px] h-1.5 w-1.5 shrink-0 rounded-full bg-brand-600"></span>
              <span>{{ event }}</span>
            </li>
          </ul>
          <p v-else class="text-sm text-muted">暂无关键事件提炼。</p>
        </article>

        <article class="card-surface space-y-3 p-5">
          <header>
            <p class="text-xs font-semibold uppercase tracking-[0.25em] text-muted">风险提示</p>
            <h3 class="text-lg font-semibold text-primary">重点风险</h3>
          </header>
          <ul v-if="deepAnalysis.keyRisks.length" class="space-y-3 text-sm text-secondary">
            <li
              v-for="(risk, index) in deepAnalysis.keyRisks"
              :key="`deep-risk-${index}`"
              class="flex gap-2 rounded-2xl border border-soft bg-surface p-3"
            >
              <span class="mt-[7px] h-1.5 w-1.5 shrink-0 rounded-full bg-amber-500"></span>
              <span>{{ risk }}</span>
            </li>
          </ul>
          <p v-else class="text-sm text-muted">暂无重点风险提炼。</p>
        </article>
      </section>

      <section class="grid gap-6 xl:grid-cols-3">
        <AnalysisChartPanel title="渠道分布" :option="channelChartOption" :has-data="hasChannelData" />
        <AnalysisChartPanel title="情感态度" :option="sentimentChartOption" :has-data="hasSentimentData" />
        <AnalysisChartPanel title="内容结构" :option="contentSplitOption" :has-data="hasContentSplitData" />
      </section>

      <section class="grid gap-6 xl:grid-cols-[2fr,1fr]">
        <AnalysisChartPanel title="时间趋势" :option="trendChartOption" :has-data="hasTrendData" />
        <article class="card-surface space-y-3 p-5">
          <header>
            <p class="text-xs font-semibold uppercase tracking-[0.25em] text-muted">传播阶段</p>
            <h3 class="text-lg font-semibold text-primary">节奏拆解</h3>
          </header>
          <ul v-if="stageNotes.length" class="space-y-3 text-sm text-secondary">
            <li v-for="stage in stageNotes" :key="`${stage.badge}-${stage.title}`" class="rounded-2xl border border-soft bg-surface p-3">
              <div class="flex items-center justify-between gap-2">
                <p class="font-semibold text-primary">{{ stage.title }}</p>
                <span class="text-xs font-semibold text-brand-600">{{ stage.badge || '-' }}</span>
              </div>
              <p class="mt-1 text-xs text-muted">{{ stage.range }} · {{ stage.delta }}</p>
              <p class="mt-2 leading-relaxed">{{ stage.highlight }}</p>
            </li>
          </ul>
          <p v-else class="text-sm text-muted">暂无阶段说明。</p>
        </article>
      </section>

      <section class="card-surface space-y-4 p-6">
        <header class="space-y-4">
          <div class="border-b border-soft pb-3">
            <div>
              <p class="text-xs font-semibold uppercase tracking-[0.25em] text-muted">BERTopic 主题演化</p>
              <h3 class="mt-1 text-lg font-semibold text-primary">核心关注点随时间的变化</h3>
            </div>
          </div>
          
          <p class="text-sm text-secondary">
            {{ bertopicOverviewText }}
          </p>
        </header>

        <div class="rounded-2xl border border-brand-soft bg-brand-soft/10 p-5 mt-2 transition-all duration-300">
          <div class="flex items-center gap-2 mb-3">
            <SparklesIcon class="h-5 w-5 text-brand-500" />
            <span class="font-semibold text-primary">AI 深度解读</span>
          </div>
          <div
            v-if="formattedBertopicInsight"
            class="prose prose-sm max-w-none text-secondary" 
            v-html="formattedBertopicInsight"
          ></div>
          <p v-else class="text-sm text-muted">
            暂无 AI 深度解读。请点击上方“重新生成”，在后端报告生成流程中补齐该区块。
          </p>
        </div>

        <div class="grid gap-4 md:grid-cols-3">
          <article class="rounded-2xl border border-soft bg-surface p-4">
            <p class="text-xs font-semibold uppercase tracking-[0.2em] text-muted">时序摘要</p>
            <p class="mt-3 text-sm leading-7 text-secondary">
              {{ bertopicTemporalNarrative.summary || '暂无结构化时序摘要。' }}
            </p>
          </article>

          <article class="rounded-2xl border border-soft bg-surface p-4">
            <p class="text-xs font-semibold uppercase tracking-[0.2em] text-muted">迁移信号</p>
            <ul v-if="bertopicTemporalNarrative.shiftSignals.length" class="mt-3 space-y-2 text-sm text-secondary">
              <li
                v-for="(signal, index) in bertopicTemporalNarrative.shiftSignals"
                :key="`bertopic-signal-${index}`"
                class="flex gap-2"
              >
                <span class="mt-[7px] h-1.5 w-1.5 shrink-0 rounded-full bg-brand-600"></span>
                <span>{{ signal }}</span>
              </li>
            </ul>
            <p v-else class="mt-3 text-sm text-muted">暂无明显迁移信号。</p>
          </article>

          <article class="rounded-2xl border border-soft bg-surface p-4">
            <p class="text-xs font-semibold uppercase tracking-[0.2em] text-muted">关注提醒</p>
            <ul v-if="bertopicTemporalNarrative.watchpoints.length" class="mt-3 space-y-2 text-sm text-secondary">
              <li
                v-for="(point, index) in bertopicTemporalNarrative.watchpoints"
                :key="`bertopic-watchpoint-${index}`"
                class="flex gap-2"
              >
                <span class="mt-[7px] h-1.5 w-1.5 shrink-0 rounded-full bg-amber-500"></span>
                <span>{{ point }}</span>
              </li>
            </ul>
            <p v-else class="mt-3 text-sm text-muted">暂无额外提醒。</p>
          </article>
        </div>

        <div class="grid gap-6 xl:grid-cols-[1.6fr,1fr]">
          <AnalysisChartPanel
            title="主题热度时间轴"
            description="背景浅蓝色区域代表每天的样本总量走势，彩色折线展示了几个核心话题在这些天的讨论热度变化。"
            :option="bertopicTimelineOption"
            :has-data="hasBertopicTimelineData"
            empty-message="暂无热度节点数据"
          />

          <article class="rounded-2xl border border-soft bg-surface p-4">
            <header class="mb-3 flex flex-wrap items-center justify-between gap-2 border-b border-soft pb-3">
              <p class="text-sm font-semibold text-primary">核心主题时间线</p>
              <span class="text-xs text-muted">包含 {{ formatNumber(themeActivePoints.length) }} 个主题节点</span>
            </header>
            
            <ul v-if="themeActivePoints.length" class="max-h-[560px] space-y-4 overflow-y-auto pr-1 text-sm text-secondary">
              <li
                v-for="group in themeActivePoints"
                :key="`theme-group-${group.theme}`"
                class="space-y-2"
              >
                <p class="font-semibold text-primary flex items-center gap-2">
                  <span class="h-2 w-2 rounded-full bg-brand-500"></span>
                  {{ group.theme }}
                </p>
                <div class="space-y-2 pl-4 border-l-2 border-brand-soft">
                  <div
                    v-for="node in group.points"
                    :key="`theme-node-${group.theme}-${node.date}`"
                    class="rounded-xl border border-soft bg-surface-muted p-2 hover:border-brand-soft hover:bg-brand-soft/10 transition-colors"
                  >
                    <div class="flex items-center justify-between gap-2">
                      <p class="font-medium text-primary">{{ node.label }}</p>
                      <span class="text-xs font-semibold text-brand-600">热度 {{ formatNumber(node.topValue) }}</span>
                    </div>
                    <p class="mt-1 text-xs text-muted">当日总样本数 {{ formatNumber(node.total) }}</p>
                  </div>
                </div>
              </li>
            </ul>
            <p v-else class="text-sm text-muted">暂无核心主题时间线数据。</p>
          </article>
        </div>
      </section>

      <section class="grid gap-6 xl:grid-cols-2">
        <AnalysisChartPanel title="关键词热度" :option="keywordChartOption" :has-data="hasKeywordData" />
        <AnalysisChartPanel title="主题分布" :option="themeChartOption" :has-data="hasThemeData" />
      </section>

      <section class="card-surface space-y-5 p-6">
        <header class="space-y-2">
          <p class="text-xs font-semibold uppercase tracking-[0.25em] text-muted">原始依据</p>
          <h3 class="text-lg font-semibold text-primary">旧版报告依据</h3>
          <p class="text-sm text-secondary">
            该区块用于承接旧版 `report.py` 链路中的文字解读、检索增强段落和长文结果，便于追溯报告结论的原始依据。
          </p>
        </header>

        <div
          v-if="!sourceReadiness.explainReady"
          class="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-700"
        >
          当前区间还没有补齐总体文字解读，报告页先展示 AI 摘要和统计结果；下方仅列出当前可用的旧版依据。
        </div>

        <div v-if="legacyContext.sections.length" class="grid gap-4 xl:grid-cols-2">
          <article
            v-for="section in legacyContext.sections"
            :id="section.anchorId"
            :key="section.anchorId"
            class="rounded-2xl border border-soft bg-surface p-5"
          >
            <div class="flex flex-wrap items-center justify-between gap-3">
              <div>
                <p class="text-xs font-semibold uppercase tracking-[0.2em] text-muted">{{ section.label }}</p>
                <h4 class="mt-1 text-base font-semibold text-primary">{{ section.sourceLabel || '文字解读段落' }}</h4>
              </div>
              <span class="rounded-full border border-sky-200 bg-sky-50 px-3 py-1 text-xs font-semibold text-sky-700">
                {{ getNarrativeSourceLabel(section.source) }}
              </span>
            </div>
            <p class="mt-4 whitespace-pre-line text-sm leading-7 text-secondary">{{ section.text }}</p>
          </article>
        </div>

        <div v-if="legacyContext.fullText || legacyContext.manualText" class="grid gap-4 xl:grid-cols-2">
          <details v-if="legacyContext.fullText" class="rounded-2xl border border-soft bg-surface p-4">
            <summary class="cursor-pointer text-sm font-semibold text-primary">查看 legacy report 长文</summary>
            <pre class="mt-3 max-h-80 overflow-auto whitespace-pre-wrap text-sm leading-7 text-secondary">{{ legacyContext.fullText }}</pre>
          </details>
          <details v-if="legacyContext.manualText" class="rounded-2xl border border-soft bg-surface p-4">
            <summary class="cursor-pointer text-sm font-semibold text-primary">查看人工补充文本</summary>
            <pre class="mt-3 max-h-80 overflow-auto whitespace-pre-wrap text-sm leading-7 text-secondary">{{ legacyContext.manualText }}</pre>
          </details>
        </div>

        <p v-if="!hasLegacyContextContent" class="text-sm text-muted">当前报告未找到可展示的旧版 explain / report 上下文。</p>
      </section>

      <section class="card-surface space-y-5 p-6">
        <header class="space-y-2">
          <p class="text-xs font-semibold uppercase tracking-[0.25em] text-muted">结论挖掘</p>
          <h3 class="text-lg font-semibold text-primary">从基础分析、文字解读与结构化研判中回收可执行结论</h3>
        </header>

        <div v-if="hasConclusionMiningContent" class="space-y-5">
          <div class="rounded-2xl border border-brand-soft bg-brand-soft/10 px-5 py-4">
            <p class="text-xs font-semibold uppercase tracking-[0.25em] text-brand-700">执行摘要</p>
            <p class="mt-2 text-sm leading-7 text-primary">
              {{ conclusionMining.executiveSummary || '暂无执行摘要。' }}
            </p>
            <div v-if="conclusionMining.supportingModules.length" class="mt-3 flex flex-wrap gap-2">
              <a
                v-for="module in conclusionMining.supportingModules"
                :key="`conclusion-summary-${module.anchorId}`"
                class="rounded-full border border-brand-soft bg-white px-3 py-1 text-xs font-semibold text-brand-700 transition hover:border-brand-300"
                :href="`#${module.anchorId}`"
              >
                依据模块：{{ module.label }}
              </a>
            </div>
          </div>

          <div class="grid gap-4 xl:grid-cols-3">
            <article
              v-for="group in conclusionGroups"
              :key="group.key"
              class="rounded-2xl border border-soft bg-surface p-5"
            >
              <header class="space-y-1 border-b border-soft pb-3">
                <p class="text-xs font-semibold uppercase tracking-[0.2em] text-muted">{{ group.title }}</p>
                <p class="text-sm text-secondary">{{ group.subtitle }}</p>
              </header>

              <div v-if="group.items.length" class="mt-4 space-y-4">
                <article
                  v-for="item in group.items"
                  :key="item.id"
                  class="rounded-2xl border border-soft bg-surface-muted px-4 py-3"
                >
                  <p v-if="item.headline" class="text-sm font-semibold text-primary">{{ item.headline }}</p>
                  <p class="mt-1 text-sm leading-7 text-secondary">{{ item.text }}</p>
                  <div v-if="item.supportingModules.length" class="mt-3 flex flex-wrap gap-2">
                    <a
                      v-for="module in item.supportingModules"
                      :key="`${item.id}-${module.anchorId}`"
                      class="rounded-full border border-soft bg-surface px-2.5 py-1 text-[11px] font-semibold text-secondary transition hover:border-brand-300 hover:text-brand-700"
                      :href="`#${module.anchorId}`"
                    >
                      {{ module.label }}
                    </a>
                  </div>
                </article>
              </div>
              <p v-else class="mt-4 text-sm text-muted">{{ group.emptyText }}</p>
            </article>
          </div>
        </div>
        <p v-else class="text-sm text-muted">当前报告未提炼出新的结论挖掘结果。</p>
      </section>

      <section class="card-surface space-y-4 p-6">
        <header class="flex flex-wrap items-center justify-between gap-2">
          <div>
            <p class="text-xs font-semibold uppercase tracking-[0.25em] text-muted">洞察亮点</p>
            <h3 class="text-lg font-semibold text-primary">重点结论</h3>
          </div>
        </header>

        <ul v-if="highlightPoints.length" class="space-y-2 rounded-2xl border border-brand-soft bg-brand-soft/20 p-4 text-sm text-secondary">
          <li v-for="(point, index) in highlightPoints" :key="`highlight-${index}`" class="flex gap-2">
            <span class="mt-[7px] h-1.5 w-1.5 shrink-0 rounded-full bg-brand-600"></span>
            <span>{{ point }}</span>
          </li>
        </ul>

        <div class="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          <article v-for="insight in insightCards" :key="insight.title" class="rounded-2xl border border-soft bg-surface p-4">
            <p class="text-xs font-semibold uppercase tracking-[0.2em] text-muted">{{ insight.title }}</p>
            <p class="mt-2 text-base font-semibold text-primary">{{ insight.headline }}</p>
            <ul class="mt-3 space-y-2 text-sm text-secondary">
              <li v-for="(point, idx) in insight.points" :key="`${insight.title}-${idx}`" class="flex gap-2">
                <span class="mt-[7px] h-1.5 w-1.5 shrink-0 rounded-full bg-brand-600"></span>
                <span>{{ point }}</span>
              </li>
            </ul>
          </article>
        </div>
      </section>
    </template>

    <section v-else class="card-surface p-6 text-sm text-muted">
      请先选择专题与时间范围，然后点击“读取报告”。
    </section>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import {
  ArrowDownTrayIcon,
  ArrowPathIcon,
  ChartBarIcon,
  ChartPieIcon,
  ClockIcon,
  GlobeAltIcon,
  HashtagIcon,
  MegaphoneIcon,
  PlayCircleIcon,
  SparklesIcon,
  UsersIcon
} from '@heroicons/vue/24/outline'
import { marked } from 'marked'
import AnalysisChartPanel from '../../components/AnalysisChartPanel.vue'
import { useReportGeneration } from '../../composables/useReportGeneration'

const router = useRouter()

const {
  topicsState,
  topicOptions,
  reportForm,
  availableRange,
  reportState,
  analysisState,
  historyState,
  reportHistory,
  selectedHistoryId,
  reportData,
  analysisSections,
  analysisAiSummary,
  loadTopics,
  loadHistory,
  loadReport,
  applyHistorySelection
} = useReportGeneration()

const exporting = ref(false)

const analysisSectionIconMap = {
  attitude: ChartBarIcon,
  classification: ChartPieIcon,
  geography: GlobeAltIcon,
  keywords: HashtagIcon,
  publishers: UsersIcon,
  trends: MegaphoneIcon,
  volume: MegaphoneIcon
}

const conclusionGroupMeta = [
  { key: 'conclusions', title: '核心结论', subtitle: '聚合页面亮点与重点判断。', emptyText: '暂无核心结论。' },
  { key: 'recommendations', title: '行动建议', subtitle: '从传播节奏与重点模块提炼后续动作。', emptyText: '暂无行动建议。' },
  { key: 'risks', title: '风险提示', subtitle: '需要持续观察或提前预警的信号。', emptyText: '暂无重点风险。' }
]

const clampRate = (value) => {
  const numeric = Number(value)
  if (Number.isNaN(numeric)) return 0
  return Math.max(0, Math.min(1, numeric))
}

const formatRate = (value) => `${(clampRate(value) * 100).toFixed(1)}%`

const formatNumber = (value) => {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '0'
  return new Intl.NumberFormat('zh-CN').format(Number(value))
}

const report = computed(() => (reportData.value && typeof reportData.value === 'object' ? reportData.value : null))

const reportMeta = computed(() => ({
  title: report.value?.title || `${reportForm.topic || '专题'}舆情分析报告`,
  subtitle: report.value?.subtitle || '基于分析结果自动生成',
  rangeText: report.value?.rangeText || `${reportForm.start || '--'} → ${reportForm.end || '--'}`,
  lastUpdated: report.value?.lastUpdated || '未提供'
}))

const analysisMainFinding = computed(() => {
  const payload = analysisAiSummary.value?.main_finding
  if (!payload || typeof payload !== 'object') return null
  const summary = String(payload?.summary || '').trim()
  if (!summary) return null
  return {
    summary,
    sourceFunctions: Array.isArray(payload?.source_functions)
      ? payload.source_functions.map((item) => String(item || '').trim()).filter(Boolean)
      : []
  }
})

const deepAnalysis = computed(() => {
  const payload = report.value?.deepAnalysis
  return {
    narrativeSummary: String(payload?.narrativeSummary || '').trim(),
    keyEvents: Array.isArray(payload?.keyEvents)
      ? payload.keyEvents.map((item) => String(item || '').trim()).filter(Boolean)
      : [],
    keyRisks: Array.isArray(payload?.keyRisks)
      ? payload.keyRisks.map((item) => String(item || '').trim()).filter(Boolean)
      : [],
    eventType: String(payload?.eventType || '').trim(),
    domain: String(payload?.domain || '').trim(),
    stage: String(payload?.stage || '').trim(),
    indicatorDimensions: Array.isArray(payload?.indicatorDimensions)
      ? payload.indicatorDimensions.map((item) => String(item || '').trim()).filter(Boolean)
      : [],
    theoryNames: Array.isArray(payload?.theoryNames)
      ? payload.theoryNames.map((item) => String(item || '').trim()).filter(Boolean)
      : [],
    referenceLinks: Array.isArray(payload?.referenceLinks)
      ? payload.referenceLinks
        .map((item) => ({
          name: String(item?.name || '').trim(),
          url: String(item?.url || '').trim(),
          usage: String(item?.usage || '').trim()
        }))
        .filter((item) => item.name && item.url)
      : []
  }
})

const metrics = computed(() => {
  const data = report.value?.metrics || {}
  const positiveRate = clampRate(data.positiveRate || 0)
  const neutralRate = clampRate(data.neutralRate || 0)
  const negativeRate = clampRate(1 - positiveRate - neutralRate)
  const factualRatio = clampRate(data.factualRatio || 0)
  const opinionRatio = clampRate(1 - factualRatio)
  return {
    totalVolume: Number(data.totalVolume || 0),
    peak: {
      value: Number(data?.peak?.value || 0),
      date: String(data?.peak?.date || '')
    },
    positiveRate,
    neutralRate,
    negativeRate,
    factualRatio,
    opinionRatio
  }
})

const channels = computed(() => (Array.isArray(report.value?.channels) ? report.value.channels : []))
const timeline = computed(() => (Array.isArray(report.value?.timeline) ? report.value.timeline : []))
const keywords = computed(() => (Array.isArray(report.value?.keywords) ? report.value.keywords : []))
const themes = computed(() => (Array.isArray(report.value?.themes) ? report.value.themes : []))
const sentiment = computed(() => report.value?.sentiment || { positive: 0, neutral: 0, negative: 0 })
const contentSplit = computed(() => report.value?.contentSplit || { factual: 0, opinion: 0 })
const moduleNarratives = computed(() => (
  Array.isArray(report.value?.moduleNarratives)
    ? report.value.moduleNarratives
      .map((item) => ({
        id: String(item?.id || '').trim(),
        label: String(item?.label || '').trim(),
        description: String(item?.description || '').trim(),
        summary: String(item?.summary || '').trim(),
        explainText: String(item?.explainText || '').trim(),
        source: String(item?.source || 'fallback').trim() || 'fallback',
        anchorId: String(item?.anchorId || `module-narrative-${item?.id || ''}`).trim(),
        hasAiSummary: Boolean(item?.hasAiSummary),
        hasExplain: Boolean(item?.hasExplain)
      }))
      .filter((item) => item.id && item.label)
    : []
))
const legacyContext = computed(() => {
  const payload = report.value?.legacyContext
  const sections = Array.isArray(payload?.sections)
    ? payload.sections
      .map((item) => ({
        id: String(item?.id || '').trim(),
        label: String(item?.label || item?.sourceLabel || '').trim(),
        sourceLabel: String(item?.sourceLabel || '').trim(),
        text: String(item?.text || '').trim(),
        source: String(item?.source || 'legacy_rag').trim() || 'legacy_rag',
        anchorId: `legacy-section-${String(item?.id || '').trim()}`
      }))
      .filter((item) => item.id && item.label && item.text)
    : []
  return {
    sections,
    fullText: String(payload?.fullText || '').trim(),
    manualText: String(payload?.manualText || '').trim(),
    hasManualText: Boolean(payload?.hasManualText),
    hasLegacyReportText: Boolean(payload?.hasLegacyReportText),
    sectionsCount: Number(payload?.sectionsCount || sections.length || 0),
    sourceTopic: String(payload?.sourceTopic || '').trim()
  }
})
const conclusionMining = computed(() => {
  const payload = report.value?.conclusionMining
  const normalizeModules = (rows) => (
    Array.isArray(rows)
      ? rows
        .map((item) => ({
          id: String(item?.id || '').trim(),
          label: String(item?.label || '').trim(),
          anchorId: String(item?.anchorId || `module-narrative-${item?.id || ''}`).trim()
        }))
        .filter((item) => item.id && item.label)
      : []
  )
  const normalizeItems = (rows) => (
    Array.isArray(rows)
      ? rows
        .map((item, index) => ({
          id: String(item?.id || `conclusion-item-${index + 1}`).trim(),
          text: String(item?.text || '').trim(),
          headline: String(item?.headline || '').trim(),
          supportingModules: normalizeModules(item?.supportingModules)
        }))
        .filter((item) => item.text)
      : []
  )
  return {
    executiveSummary: String(payload?.executiveSummary || '').trim(),
    conclusions: normalizeItems(payload?.conclusions),
    recommendations: normalizeItems(payload?.recommendations),
    risks: normalizeItems(payload?.risks),
    supportingModules: normalizeModules(payload?.supportingModules)
  }
})
const sourceReadiness = computed(() => {
  const payload = report.value?.sourceReadiness
  return {
    analyzeReady: Boolean(payload?.analyzeReady),
    aiSummaryReady: Boolean(payload?.aiSummaryReady),
    explainReady: Boolean(payload?.explainReady),
    legacyContextReady: Boolean(payload?.legacyContextReady)
  }
})

const sourceReadinessItems = computed(() => ([
  {
    id: 'analyze',
    label: '基础分析',
    ready: sourceReadiness.value.analyzeReady,
    detail: sourceReadiness.value.analyzeReady ? '7 个基础分析模块可直接复用。' : '基础分析结果尚未准备完成。'
  },
  {
    id: 'ai-summary',
    label: 'AI 摘要',
    ready: sourceReadiness.value.aiSummaryReady,
    detail: sourceReadiness.value.aiSummaryReady ? '模块摘要可用于快速解读。' : '当前缺少 AI 摘要，将仅展示统计结果。'
  },
  {
    id: 'explain',
    label: '总体文字解读',
    ready: sourceReadiness.value.explainReady,
    detail: sourceReadiness.value.explainReady ? '总体文字解读已接入报告。' : '总体文字解读待补齐，当前先结合 AI 摘要和统计结果展示。'
  },
  {
    id: 'legacy-context',
    label: '原始依据',
    ready: sourceReadiness.value.legacyContextReady,
    detail: sourceReadiness.value.legacyContextReady ? '已收集旧 report 段落与长文依据。' : '旧 report 上下文暂不可用。'
  }
]))

const conclusionGroups = computed(() => conclusionGroupMeta.map((group) => ({
  ...group,
  items: Array.isArray(conclusionMining.value?.[group.key]) ? conclusionMining.value[group.key] : []
})))

const hasLegacyContextContent = computed(() => Boolean(
  legacyContext.value.sections.length ||
  legacyContext.value.fullText ||
  legacyContext.value.manualText
))

const hasConclusionMiningContent = computed(() => Boolean(
  conclusionMining.value.executiveSummary ||
  conclusionGroups.value.some((group) => group.items.length) ||
  conclusionMining.value.supportingModules.length
))

const getAnalysisSectionIcon = (sectionName) => analysisSectionIconMap[sectionName] || ChartPieIcon

const formatRowName = (row) => {
  if (!row) return '-'
  return row.displayName ?? row.name ?? row.label ?? row.key ?? '未命名'
}

const formatRowValue = (row) => {
  if (!row) return 0
  if (row.displayValue != null) return row.displayValue
  return row.value ?? row.count ?? row.total ?? 0
}

const getNarrativeSourceLabel = (source) => ({
  'ai_summary+legacy_rag': 'AI 摘要 + 文字解读',
  ai_summary: 'AI 摘要',
  legacy_rag: '文字解读',
  snapshot: '统计快照',
  fallback: 'AI/统计补位'
}[String(source || '').trim()] || 'AI/统计补位')

const getNarrativeSourceClass = (source) => {
  const key = String(source || '').trim()
  if (key === 'ai_summary+legacy_rag') return 'border-brand-soft bg-brand-soft/20 text-brand-700'
  if (key === 'ai_summary') return 'border-emerald-200 bg-emerald-50 text-emerald-700'
  if (key === 'legacy_rag') return 'border-sky-200 bg-sky-50 text-sky-700'
  if (key === 'snapshot') return 'border-amber-200 bg-amber-50 text-amber-700'
  return 'border-soft bg-surface text-secondary'
}

const hasOverallTarget = (target) => {
  const rawTarget = String(target?.target || '').trim().toLowerCase()
  const title = String(target?.title || '').trim()
  return rawTarget === 'overall' || rawTarget === 'all' || title.endsWith('总体')
}

const createEmptyAnalysisTarget = (section) => ({
  target: '__empty__',
  title: `${section?.label || '模块'} · 代表图`,
  subtitle: '当前模块暂无可用图表。',
  option: {},
  hasData: false,
  rows: []
})

const pickPrimaryTarget = (section) => {
  const targets = Array.isArray(section?.targets) ? section.targets : []
  if (!targets.length) return createEmptyAnalysisTarget(section)

  const hasDataTargets = targets.filter((target) => Boolean(target?.hasData))
  if (section?.name === 'trends') {
    return (
      hasDataTargets.find((target) => target?.target === '__trend_flow__') ||
      hasDataTargets.find((target) => target?.target === '__trend_share__') ||
      hasDataTargets.find((target) => hasOverallTarget(target)) ||
      hasDataTargets[0] ||
      targets[0]
    )
  }

  return (
    hasDataTargets.find((target) => hasOverallTarget(target)) ||
    hasDataTargets[0] ||
    targets[0]
  )
}

const buildSnapshotSummary = (rows, label) => {
  const normalizedRows = Array.isArray(rows) ? rows.filter(Boolean).slice(0, 3) : []
  if (!normalizedRows.length) {
    return `${label || '当前模块'}暂无可直接复用的统计快照。`
  }
  const fragments = normalizedRows.map((row) => `${formatRowName(row)} ${formatRowValue(row)}`)
  return `${label || '当前模块'}的代表性指标为：${fragments.join('；')}。`
}

const analysisOverviewCards = computed(() => {
  const narrativeMap = new Map(moduleNarratives.value.map((item) => [item.id, item]))

  return analysisSections.value.map((section) => {
    const narrative = narrativeMap.get(section.name) || null
    const primaryTarget = pickPrimaryTarget(section)
    const rows = Array.isArray(primaryTarget?.rows) ? primaryTarget.rows.slice(0, 6) : []
    const summary = String(narrative?.summary || '').trim() || buildSnapshotSummary(rows, section.label)
    const explainText = String(narrative?.explainText || '').trim() || summary

    return {
      name: section.name,
      label: section.label,
      description: section.description,
      source: narrative?.source || 'fallback',
      summary,
      explainText,
      anchorId: String(narrative?.anchorId || `module-narrative-${section.name}`).trim(),
      primaryTarget,
      rows
    }
  })
})

const stageNotes = computed(() => (Array.isArray(report.value?.stageNotes) ? report.value.stageNotes : []))
const parseDateToken = (raw) => {
  const token = String(raw || '').trim().slice(0, 10)
  if (!/^\d{4}-\d{2}-\d{2}$/.test(token)) return null
  const dt = new Date(`${token}T00:00:00`)
  return Number.isNaN(dt.getTime()) ? null : dt
}

const bertopicTemporal = computed(() => (report.value?.bertopicTemporal && typeof report.value.bertopicTemporal === 'object'
  ? report.value.bertopicTemporal
  : {}))
const bertopicTemporalMeta = computed(() => (bertopicTemporal.value?.meta && typeof bertopicTemporal.value.meta === 'object'
  ? bertopicTemporal.value.meta
  : {}))

const normalizeBertopicThemes = (rows) => (
  Array.isArray(rows)
    ? rows
      .map((theme) => ({
        name: String(theme?.name || '').trim(),
        value: Number(theme?.value || 0)
      }))
      .filter((theme) => theme.name)
      .sort((a, b) => b.value - a.value)
    : []
)

const normalizeBertopicTimelineNodes = (rows) => (
  Array.isArray(rows)
    ? rows
      .map((item) => {
        const date = String(item?.date || '').trim()
        const label = String(item?.label || date).trim()
        const topTheme = String(item?.topTheme || '').trim()
        const topValue = Number(item?.topValue || 0)
        const total = Number(item?.total || 0)
        const themes = normalizeBertopicThemes(item?.themes)
        const tailThemes = themes
          .slice(1, 3)
          .map((theme) => `${theme.name}(${formatNumber(theme.value)})`)
          .join('、')
        return {
          date,
          label: label || date,
          topTheme,
          topValue,
          total,
          themes,
          tailThemes
        }
      })
      .filter((item) => item.date && item.topTheme)
      .sort((a, b) => {
        const left = parseDateToken(a.date)
        const right = parseDateToken(b.date)
        if (left && right) return left.getTime() - right.getTime()
        if (left) return -1
        if (right) return 1
        return a.date.localeCompare(b.date)
      })
    : []
)

const normalizeBertopicSeries = (rows) => (
  Array.isArray(rows)
    ? rows
      .map((item) => {
        const title = String(item?.title || item?.name || '').trim()
        const rawPoints = Array.isArray(item?.points) ? item.points : []
        const points = rawPoints
          .map((point) => {
            const date = String(point?.date || '').trim()
            return {
              date,
              label: String(point?.label || date).trim() || date,
              count: Number(point?.count || point?.value || 0)
            }
          })
          .filter((point) => point.date && point.count > 0)
          .sort((a, b) => {
            const left = parseDateToken(a.date)
            const right = parseDateToken(b.date)
            if (left && right) return left.getTime() - right.getTime()
            if (left) return -1
            if (right) return 1
            return a.date.localeCompare(b.date)
          })
        if (!title || !points.length) return null
        return {
          name: String(item?.name || title).trim() || title,
          title,
          description: String(item?.description || '').trim(),
          totalCount: Number(item?.totalCount || item?.total_count || points.reduce((sum, point) => sum + point.count, 0)),
          originalTopics: Array.isArray(item?.originalTopics || item?.original_topics)
            ? (item?.originalTopics || item?.original_topics).map((topic) => String(topic || '').trim()).filter(Boolean)
            : [],
          points
        }
      })
      .filter(Boolean)
      .sort((a, b) => b.totalCount - a.totalCount)
    : []
)

const deriveBertopicSeriesFromNodes = (nodes) => {
  const buckets = new Map()
  nodes.forEach((node) => {
    node.themes.forEach((theme) => {
      const current = buckets.get(theme.name) || []
      current.push({
        date: node.date,
        label: node.label || node.date,
        count: Number(theme.value || 0)
      })
      buckets.set(theme.name, current)
    })
  })

  return [...buckets.entries()]
    .map(([title, points]) => ({
      name: title,
      title,
      description: '',
      totalCount: points.reduce((sum, point) => sum + Number(point.count || 0), 0),
      originalTopics: [],
      points: [...points].sort((a, b) => {
        const left = parseDateToken(a.date)
        const right = parseDateToken(b.date)
        if (left && right) return left.getTime() - right.getTime()
        if (left) return -1
        if (right) return 1
        return a.date.localeCompare(b.date)
      })
    }))
    .sort((a, b) => b.totalCount - a.totalCount)
}

const getBertopicSourceLabel = (source) => ({
  llm_clusters: 'LLM 新主题时序序列',
  raw_topics: 'BERTopic 原始主题时序序列',
  legacy_doc_mapping: '回填映射时序序列',
  time_nodes: '主导主题节点序列'
}[String(source || '').trim()] || '')

const bertopicTimelineNodes = computed(() => {
  const rows = Array.isArray(bertopicTemporal.value?.timeNodes)
    ? bertopicTemporal.value.timeNodes
    : (Array.isArray(report.value?.bertopicTimeNodes) ? report.value.bertopicTimeNodes : [])
  return normalizeBertopicTimelineNodes(rows)
})
const bertopicTemporalSeries = computed(() => {
  const standardized = normalizeBertopicSeries(bertopicTemporal.value?.series)
  if (standardized.length) return standardized
  return deriveBertopicSeriesFromNodes(bertopicTimelineNodes.value)
})
const bertopicOverview = computed(() => (bertopicTemporal.value?.overview && typeof bertopicTemporal.value.overview === 'object'
  ? bertopicTemporal.value.overview
  : (report.value?.bertopicOverview && typeof report.value.bertopicOverview === 'object'
      ? report.value.bertopicOverview
      : {})))
const bertopicTemporalNarrative = computed(() => {
  const payload = report.value?.bertopicTemporalNarrative
  return {
    summary: String(payload?.summary || '').trim(),
    shiftSignals: Array.isArray(payload?.shiftSignals)
      ? payload.shiftSignals.map((item) => String(item || '').trim()).filter(Boolean)
      : [],
    watchpoints: Array.isArray(payload?.watchpoints)
      ? payload.watchpoints.map((item) => String(item || '').trim()).filter(Boolean)
      : []
  }
})
const bertopicCoverageRange = computed(() => {
  const overviewStart = String(bertopicOverview.value?.rangeStart || '').trim()
  const overviewEnd = String(bertopicOverview.value?.rangeEnd || '').trim()
  if (overviewStart || overviewEnd) {
    return { start: overviewStart, end: overviewEnd }
  }
  const rows = bertopicTimelineNodes.value
  if (!rows.length) return { start: '', end: '' }
  return {
    start: String(rows[0]?.date || '').trim(),
    end: String(rows[rows.length - 1]?.date || '').trim()
  }
})
const bertopicOverviewText = computed(() => {
  const bucketCount = Number(
    bertopicOverview.value?.bucketCount || bertopicOverview.value?.days || bertopicTimelineNodes.value.length || 0
  )
  const mappedDocs = Number(
    bertopicOverview.value?.totalMappedDocs || bertopicTemporalMeta.value?.mappedDocs || 0
  )
  const aggregationLabel = String(bertopicOverview.value?.aggregationLabel || '日').trim() || '日'
  const coverageStart = String(bertopicCoverageRange.value.start || '').trim()
  const coverageEnd = String(bertopicCoverageRange.value.end || '').trim()
  const reportStart = String(reportForm.start || '').trim()
  const reportEnd = String(reportForm.end || reportStart || '').trim()
  const sourceLabel = getBertopicSourceLabel(
    bertopicTemporalMeta.value?.seriesSource || bertopicTemporalMeta.value?.timeSource
  )
  const coverageRate = Number(bertopicTemporalMeta.value?.coverageRate || 0)
  if (!bucketCount && !mappedDocs) return '我们对这期间的讨论进行了分析，整理出了核心话题在时序上的变化走势。'

  const fragments = []
  if (coverageStart && coverageEnd) {
    fragments.push(`BERTopic 结果当前覆盖 ${coverageStart} 至 ${coverageEnd} 共 ${formatNumber(bucketCount)} 个${aggregationLabel}级时间桶，映射到 ${formatNumber(mappedDocs)} 条讨论。`)
  } else {
    fragments.push(`BERTopic 结果共覆盖 ${formatNumber(bucketCount)} 个${aggregationLabel}级时间桶，映射到 ${formatNumber(mappedDocs)} 条讨论。`)
  }
  if (sourceLabel) {
    fragments.push(`当前引用 ${sourceLabel}。`)
  }
  if (coverageRate > 0) {
    fragments.push(`时序映射覆盖率 ${formatRate(coverageRate)}。`)
  }
  if (coverageStart && coverageEnd && reportStart && reportEnd && (coverageStart > reportStart || coverageEnd < reportEnd)) {
    fragments.push(`与报告区间（${reportStart} 至 ${reportEnd}）不一致，请重新运行 BERTopic 后再生成报告。`)
  }
  return fragments.join('')
})
const bertopicInsight = computed(() => String(report.value?.bertopicInsight || '').trim())
const formattedBertopicInsight = computed(() => {
  if (!bertopicInsight.value) return ''
  return marked.parse(bertopicInsight.value, { mangle: false, headerIds: false })
})
const bertopicLeadingThemes = computed(() => {
  const payloadThemes = Array.isArray(bertopicTemporal.value?.leadingThemes)
    ? bertopicTemporal.value.leadingThemes.map((item) => String(item || '').trim()).filter(Boolean)
    : []
  if (payloadThemes.length) return payloadThemes.slice(0, 3)
  if (bertopicTemporalSeries.value.length) {
    return bertopicTemporalSeries.value.slice(0, 3).map((item) => item.title)
  }
  const stats = new Map()
  bertopicTimelineNodes.value.forEach((node) => {
    node.themes.forEach((theme) => {
      const name = String(theme?.name || '').trim()
      const value = Number(theme?.value || 0)
      if (!name || value <= 0) return
      stats.set(name, (stats.get(name) || 0) + value)
    })
  })
  return [...stats.entries()]
    .sort((a, b) => b[1] - a[1])
    .slice(0, 3)
    .map(([name]) => name)
})
const highlightPoints = computed(() => (Array.isArray(report.value?.highlightPoints) ? report.value.highlightPoints : []))
const insightCards = computed(() => (Array.isArray(report.value?.insights) ? report.value.insights : []))

const hasChannelData = computed(() => channels.value.length > 0)
const hasTrendData = computed(() => timeline.value.length > 0)
const hasSentimentData = computed(() => Boolean(sentiment.value))
const hasContentSplitData = computed(() => Boolean(contentSplit.value))
const hasKeywordData = computed(() => keywords.value.length > 0)
const hasThemeData = computed(() => themes.value.length > 0)
const hasBertopicTimelineData = computed(() => bertopicTimelineNodes.value.length > 0 || bertopicTemporalSeries.value.length > 0)

const channelChartOption = computed(() => {
  const sorted = [...channels.value]
    .map((item) => ({
      name: String(item?.name || ''),
      value: Number(item?.value || 0)
    }))
    .filter((item) => item.name)
    .sort((a, b) => b.value - a.value)
  const maxValue = sorted.length ? Math.max(...sorted.map((item) => item.value), 0) : 0
  const axisMax = maxValue > 0 ? Math.ceil((maxValue * 1.1) / 1000) * 1000 : 1

  return {
    color: ['#2563eb', '#0ea5e9', '#10b981', '#f97316', '#8b5cf6', '#ef4444'],
    tooltip: { trigger: 'axis' },
    grid: { left: 72, right: 72, top: 24, bottom: 24 },
    xAxis: { type: 'value', max: axisMax, axisLabel: { color: '#475569' } },
    yAxis: {
      type: 'category',
      inverse: true,
      data: sorted.map((item) => item.name),
      axisLabel: { color: '#475569' }
    },
    series: [
      {
        type: 'bar',
        barWidth: 18,
        data: sorted.map((item) => item.value),
        clip: false,
        itemStyle: { borderRadius: [8, 8, 8, 8] },
        label: { show: true, position: 'right', distance: 8, color: '#0f172a', fontWeight: 600 }
      }
    ]
  }
})

const trendChartOption = computed(() => {
  const rows = timeline.value.map((item) => ({
    date: String(item?.date || ''),
    value: Number(item?.value || 0)
  }))
  const interval = rows.length > 40 ? Math.ceil(rows.length / 12) : 0

  return {
    color: ['#2563eb'],
    tooltip: { trigger: 'axis' },
    grid: { left: 56, right: 20, top: 24, bottom: rows.length > 40 ? 72 : 34 },
    xAxis: {
      type: 'category',
      boundaryGap: false,
      data: rows.map((item) => item.date),
      axisLabel: { color: '#475569', interval }
    },
    yAxis: {
      type: 'value',
      axisLabel: { color: '#475569' },
      splitLine: { lineStyle: { color: '#e2e8f0' } }
    },
    dataZoom: rows.length > 40
      ? [
          { type: 'inside', start: 0, end: 100 },
          { type: 'slider', start: 0, end: 100, height: 20, bottom: 18 }
        ]
      : [],
    series: [
      {
        type: 'line',
        smooth: true,
        showSymbol: false,
        data: rows.map((item) => item.value),
        areaStyle: { color: 'rgba(37,99,235,0.12)' },
        lineStyle: { width: 2.5 }
      }
    ]
  }
})

const sentimentChartOption = computed(() => ({
  color: ['#22c55e', '#f59e0b', '#ef4444'],
  tooltip: { trigger: 'item' },
  series: [
    {
      type: 'pie',
      radius: ['45%', '70%'],
      label: { formatter: '{b}\n{d}%' },
      data: [
        { name: '正向', value: Number(sentiment.value.positive || 0) },
        { name: '中性', value: Number(sentiment.value.neutral || 0) },
        { name: '负向', value: Number(sentiment.value.negative || 0) }
      ]
    }
  ]
}))

const contentSplitOption = computed(() => ({
  color: ['#0ea5e9', '#6366f1'],
  tooltip: { trigger: 'item' },
  series: [
    {
      type: 'pie',
      radius: ['45%', '70%'],
      label: { formatter: '{b}\n{d}%' },
      data: [
        { name: '报道事实', value: Number(contentSplit.value.factual || 0) },
        { name: '评论观点', value: Number(contentSplit.value.opinion || 0) }
      ]
    }
  ]
}))

const keywordChartOption = computed(() => {
  const rows = [...keywords.value]
    .map((item) => ({ term: String(item?.term || ''), value: Number(item?.value || 0) }))
    .filter((item) => item.term)
    .sort((a, b) => b.value - a.value)
    .slice(0, 10)

  return {
    color: ['#2563eb'],
    tooltip: { trigger: 'axis' },
    grid: { left: 120, right: 24, top: 24, bottom: 24 },
    xAxis: { type: 'value', axisLabel: { color: '#475569' } },
    yAxis: {
      type: 'category',
      inverse: true,
      data: rows.map((item) => item.term),
      axisLabel: { color: '#475569' }
    },
    series: [
      {
        type: 'bar',
        barWidth: 16,
        data: rows.map((item) => item.value),
        itemStyle: { borderRadius: [6, 6, 6, 6] },
        label: { show: true, position: 'right', color: '#0f172a', fontWeight: 600 }
      }
    ]
  }
})

const themeChartOption = computed(() => {
  const rows = [...themes.value]
    .map((item) => ({ name: String(item?.name || ''), value: Number(item?.value || 0) }))
    .filter((item) => item.name)
    .sort((a, b) => b.value - a.value)
    .slice(0, 10)

  return {
    color: ['#8b5cf6'],
    tooltip: { trigger: 'axis' },
    grid: { left: 80, right: 24, top: 24, bottom: 84 },
    xAxis: {
      type: 'category',
      data: rows.map((item) => item.name),
      axisLabel: { color: '#475569', interval: 0, rotate: rows.length > 6 ? 20 : 0 }
    },
    yAxis: {
      type: 'value',
      axisLabel: { color: '#475569' },
      splitLine: { lineStyle: { color: '#e2e8f0' } }
    },
    series: [
      {
        type: 'bar',
        barWidth: 20,
        data: rows.map((item) => item.value),
        itemStyle: { borderRadius: [6, 6, 0, 0] },
        label: { show: true, position: 'top', color: '#0f172a', fontWeight: 600 }
      }
    ]
  }
})

const themeActivePoints = computed(() => {
  const rows = bertopicTimelineNodes.value
  const seriesRows = bertopicTemporalSeries.value
  const leaders = bertopicLeadingThemes.value
  if (!leaders.length) return []

  const grouped = []
  for (const themeName of leaders) {
    let points = []
    for (const node of rows) {
      if (node.topTheme === themeName) {
        points.push(node)
      }
    }
    if (!points.length) {
      const matchedSeries = seriesRows.find((item) => item.title === themeName)
      if (matchedSeries) {
        points = matchedSeries.points.map((point) => ({
          date: point.date,
          label: point.label || point.date,
          topTheme: themeName,
          topValue: Number(point.count || 0),
          total: Number(point.count || 0)
        }))
      }
    }
    if (points.length) {
      points.sort((a, b) => b.topValue - a.topValue)
      grouped.push({
        theme: themeName,
        points: points.slice(0, 3)
      })
    }
  }
  return grouped
})

const bertopicTimelineOption = computed(() => {
  const rows = bertopicTimelineNodes.value
  const seriesRows = bertopicTemporalSeries.value
  const leaders = bertopicLeadingThemes.value
  const dateMap = new Map()

  rows.forEach((node) => {
    if (!node.date) return
    dateMap.set(node.date, node.label || node.date)
  })
  seriesRows.forEach((series) => {
    series.points.forEach((point) => {
      if (!point.date || dateMap.has(point.date)) return
      dateMap.set(point.date, point.label || point.date)
    })
  })

  const orderedDates = [...dateMap.keys()].sort((a, b) => {
    const left = parseDateToken(a)
    const right = parseDateToken(b)
    if (left && right) return left.getTime() - right.getTime()
    if (left) return -1
    if (right) return 1
    return a.localeCompare(b)
  })
  const labels = orderedDates.map((date) => dateMap.get(date) || date)
  const totalMap = new Map()
  rows.forEach((node) => {
    totalMap.set(node.date, Number(node.total || 0))
  })
  if (!rows.length) {
    seriesRows.forEach((series) => {
      series.points.forEach((point) => {
        totalMap.set(point.date, Number(totalMap.get(point.date) || 0) + Number(point.count || 0))
      })
    })
  }
  const totals = orderedDates.map((date) => Number(totalMap.get(date) || 0))

  const leaderSeries = leaders.map((themeName) => ({
    name: themeName,
    type: 'line',
    smooth: true,
    showSymbol: false,
    lineStyle: { width: 2.5 },
    data: orderedDates.map((date) => {
      const matchedSeries = seriesRows.find((item) => item.title === themeName)
      if (matchedSeries) {
        const matchedPoint = matchedSeries.points.find((point) => point.date === date)
        return Number(matchedPoint?.count || 0)
      }
      const matchedNode = rows.find((node) => node.date === date)
      const matchedTheme = matchedNode?.themes.find((theme) => theme.name === themeName)
      return Number(matchedTheme?.value || 0)
    })
  }))

  const interval = labels.length > 42 ? Math.ceil(labels.length / 12) : 0

  return {
    color: ['#1d4ed8', '#f97316', '#0ea5e9', '#10b981'],
    tooltip: { trigger: 'axis' },
    legend: {
      top: 4,
      data: ['样本总量', ...leaders],
      textStyle: { color: '#475569', fontSize: 12 }
    },
    grid: { left: 56, right: 20, top: 56, bottom: labels.length > 42 ? 72 : 42 },
    xAxis: {
      type: 'category',
      data: labels,
      boundaryGap: false,
      axisLabel: { color: '#475569', interval }
    },
    yAxis: {
      type: 'value',
      axisLabel: { color: '#475569' },
      splitLine: { lineStyle: { color: '#e2e8f0' } }
    },
    dataZoom: labels.length > 42
      ? [
          { type: 'inside', start: 0, end: 100 },
          { type: 'slider', start: 0, end: 100, height: 20, bottom: 18 }
        ]
      : [],
    series: [
      {
        name: '样本总量',
        type: 'line',
        smooth: true,
        showSymbol: false,
        data: totals,
        areaStyle: { color: 'rgba(59, 130, 246, 0.15)' },
        lineStyle: { width: 0, color: 'rgba(59, 130, 246, 0.3)' },
      },
      ...leaderSeries,
    ]
  }
})

const handleSelectHistory = async (event) => {
  const historyId = String(event.target.value || '').trim()
  if (!historyId) return
  await applyHistorySelection(historyId, { shouldLoad: true })
}

const handleRefreshHistory = async () => {
  const topic = String(reportForm.topic || '').trim()
  if (!topic) return
  await loadHistory(topic)
}

const goToRunPage = () => router.push({ name: 'report-generation-run' })

const escapeHtml = (value) => String(value || '')
  .replace(/&/g, '&amp;')
  .replace(/</g, '&lt;')
  .replace(/>/g, '&gt;')
  .replace(/"/g, '&quot;')
  .replace(/'/g, '&#39;')

const buildHtmlDocument = () => {
  if (!report.value) return ''

  const chartOptions = {}
  const chartRuntime = []
  const registerChart = (optionKey, option, hasData) => {
    chartOptions[optionKey] = option || {}
    chartRuntime.push({
      id: `chart-${optionKey}`,
      optionKey,
      hasData: Boolean(hasData)
    })
  }

  registerChart('channel', channelChartOption.value, hasChannelData.value)
  registerChart('sentiment', sentimentChartOption.value, hasSentimentData.value)
  registerChart('contentSplit', contentSplitOption.value, hasContentSplitData.value)
  registerChart('trend', trendChartOption.value, hasTrendData.value)
  registerChart('bertopicTimeline', bertopicTimelineOption.value, hasBertopicTimelineData.value)
  registerChart('keyword', keywordChartOption.value, hasKeywordData.value)
  registerChart('theme', themeChartOption.value, hasThemeData.value)

  const analysisOverviewEntries = analysisOverviewCards.value.map((card) => {
    const optionKey = `analysis-overview-${card.name}`
    registerChart(optionKey, card.primaryTarget?.option, card.primaryTarget?.hasData)
    return {
      ...card,
      optionKey,
      chartId: `chart-${optionKey}`
    }
  })

  const renderChartPanel = (optionKey, title, description = '') => {
    const runtime = chartRuntime.find((item) => item.optionKey === optionKey)
    return `
      <article class="panel chart-panel">
        <header class="panel-header">
          <h3>${escapeHtml(title)}</h3>
          ${description ? `<p class="panel-subtitle">${escapeHtml(description)}</p>` : ''}
        </header>
        ${runtime?.hasData
          ? `<div id="${escapeHtml(runtime.id)}" class="chart"></div>`
          : '<div class="chart-empty">暂无可视化数据</div>'}
      </article>
    `
  }

  const renderTable = (rows) => {
    if (!Array.isArray(rows) || !rows.length) {
      return '<p class="empty-text" style="margin-top:12px;">暂无表格数据。</p>'
    }
    return `
      <div class="table-shell">
        <table class="data-table">
          <thead>
            <tr>
              <th>名称</th>
              <th>数值</th>
            </tr>
          </thead>
          <tbody>
            ${rows.map((row) => `
              <tr>
                <td>${escapeHtml(formatRowName(row))}</td>
                <td>${escapeHtml(formatRowValue(row))}</td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      </div>
    `
  }

  const renderModuleLinks = (modules, prefix = '') => {
    if (!Array.isArray(modules) || !modules.length) return ''
    return `
      <div class="chip-row">
        ${modules.map((module) => `
          <a class="anchor-chip" href="#${escapeHtml(module.anchorId || '')}">
            ${prefix}${escapeHtml(module.label || module.id || '')}
          </a>
        `).join('')}
      </div>
    `
  }

  const stageContent = stageNotes.value.length
    ? `<ul class="stage-list">
      ${stageNotes.value.map((stage) => `
        <li class="stage-item">
          <div class="stage-head">
            <p class="stage-title">${escapeHtml(stage.title || '-')}</p>
            <span class="stage-badge">${escapeHtml(stage.badge || '-')}</span>
          </div>
          <p class="stage-meta">${escapeHtml(stage.range || '-')} · ${escapeHtml(stage.delta || '-')}</p>
          <p class="stage-highlight">${escapeHtml(stage.highlight || '')}</p>
        </li>
      `).join('')}
    </ul>`
    : '<p class="empty-text">暂无阶段说明。</p>'

  const readinessHtml = `
    <div class="readiness-grid">
      ${sourceReadinessItems.value.map((item) => `
        <article class="readiness-card ${item.ready ? 'is-ready' : ''}">
          <div class="readiness-head">
            <p>${escapeHtml(item.label)}</p>
            <span>${item.ready ? '已接入' : '待补齐/缺失'}</span>
          </div>
          <p class="readiness-detail">${escapeHtml(item.detail)}</p>
        </article>
      `).join('')}
    </div>
  `

  const analysisMainFindingHtml = analysisMainFinding.value
    ? `
      <div class="callout">
        <p class="callout-kicker">AI 主要发现</p>
        <p class="callout-text">${escapeHtml(analysisMainFinding.value.summary)}</p>
        ${analysisMainFinding.value.sourceFunctions.length
          ? `<p class="callout-meta">依据模块：${escapeHtml(analysisMainFinding.value.sourceFunctions.join('、'))}</p>`
          : ''}
      </div>
    `
    : ''

  const renderNarrativeSource = (source) => escapeHtml(getNarrativeSourceLabel(source))
  const analysisOverviewHtml = analysisOverviewEntries.length
    ? `<div class="analysis-overview-grid">
      ${analysisOverviewEntries.map((card) => `
        <article class="analysis-overview-card" id="${escapeHtml(card.anchorId)}">
          <div class="card-head">
            <div>
              <p class="insight-title">${escapeHtml(card.label)}</p>
              <p class="insight-headline">${escapeHtml(card.description || '')}</p>
            </div>
            <span class="source-pill">${renderNarrativeSource(card.source)}</span>
          </div>
          <p class="narrative-text" style="margin-top:12px;">${escapeHtml(card.summary || '暂无综合摘要。')}</p>
          ${card.primaryTarget?.hasData
            ? `
              <div class="sub-block">
                <p class="sub-block-title">${escapeHtml(card.primaryTarget.title || '代表图')}</p>
                ${card.primaryTarget.subtitle ? `<p class="panel-subtitle">${escapeHtml(card.primaryTarget.subtitle)}</p>` : ''}
                <div id="${escapeHtml(card.chartId)}" class="chart chart-sm"></div>
              </div>
            `
            : `
              <div class="sub-block">
                <p class="sub-block-title">${escapeHtml(card.primaryTarget?.title || '代表图')}</p>
                <div class="chart-empty chart-sm">暂无可视化数据</div>
              </div>
            `}
          <div class="analysis-overview-bottom">
            ${renderTable(card.rows)}
            <div class="narrative-card">
              <p class="narrative-title">综合解读</p>
              <p class="narrative-text">${escapeHtml(card.explainText || card.summary || '暂无综合解读。')}</p>
            </div>
          </div>
        </article>
      `).join('')}
    </div>`
    : '<section class="panel"><p class="empty-text">暂无基础分析图表。</p></section>'

  const deepTags = [
    deepAnalysis.value.eventType ? `事件类型：${deepAnalysis.value.eventType}` : '',
    deepAnalysis.value.domain ? `领域：${deepAnalysis.value.domain}` : '',
    deepAnalysis.value.stage ? `阶段：${deepAnalysis.value.stage}` : ''
  ].filter(Boolean)
  const deepDimensionsHtml = deepAnalysis.value.indicatorDimensions.length
    ? `<p class="metric-sub">持续观察维度：${escapeHtml(deepAnalysis.value.indicatorDimensions.join('、'))}</p>`
    : ''
  const deepTheoryHtml = deepAnalysis.value.theoryNames.length
    ? `<p class="metric-sub">理论锚点：${escapeHtml(deepAnalysis.value.theoryNames.join('、'))}</p>`
    : ''
  const deepLinksHtml = deepAnalysis.value.referenceLinks.length
    ? `<ul class="bullet-list compact">
      ${deepAnalysis.value.referenceLinks.map((item) => `
        <li>
          <a href="${escapeHtml(item.url)}" target="_blank" rel="noreferrer" style="color:#1d4ed8;text-decoration:none;">
            ${escapeHtml(item.name)}
          </a>
          ${item.usage ? ` <span style="color:#64748b;">${escapeHtml(item.usage)}</span>` : ''}
        </li>
      `).join('')}
    </ul>`
    : ''
  const deepAnalysisHtml = `
    <section class="chart-grid-3">
      <article class="panel">
        <header class="panel-header">
          <h3>AI 深度研判</h3>
          <p class="panel-subtitle">解释与研判</p>
        </header>
        <p class="metric-sub" style="font-size:14px; line-height:1.9;">${escapeHtml(deepAnalysis.value.narrativeSummary || '暂无结构化研判摘要。')}</p>
        ${deepTags.length ? `<p class="metric-sub" style="margin-top:10px;">${escapeHtml(deepTags.join(' · '))}</p>` : ''}
        ${deepDimensionsHtml}
        ${deepTheoryHtml}
        ${deepLinksHtml}
      </article>
      <article class="panel">
        <header class="panel-header">
          <h3>阶段节点</h3>
          <p class="panel-subtitle">关键事件</p>
        </header>
        ${deepAnalysis.value.keyEvents.length
          ? `<ul class="bullet-list">${deepAnalysis.value.keyEvents.map((item) => `<li>${escapeHtml(item)}</li>`).join('')}</ul>`
          : '<p class="empty-text">暂无关键事件提炼。</p>'}
      </article>
      <article class="panel">
        <header class="panel-header">
          <h3>重点风险</h3>
          <p class="panel-subtitle">风险提示</p>
        </header>
        ${deepAnalysis.value.keyRisks.length
          ? `<ul class="bullet-list">${deepAnalysis.value.keyRisks.map((item) => `<li>${escapeHtml(item)}</li>`).join('')}</ul>`
          : '<p class="empty-text">暂无重点风险提炼。</p>'}
      </article>
    </section>
  `

  const themeTimelineHtml = themeActivePoints.value.length
    ? `<ul class="theme-group-list">
      ${themeActivePoints.value.map((group) => {
        const points = Array.isArray(group.points) ? group.points : []
        const pointsHtml = points.map((node) => `
          <article class="theme-point">
            <div class="theme-point-head">
              <p>${escapeHtml(node.label)}</p>
              <span>热度 ${escapeHtml(formatNumber(node.topValue))}</span>
            </div>
            <p class="theme-point-meta">当日总样本数 ${escapeHtml(formatNumber(node.total))}</p>
          </article>
        `).join('')
        return `
          <li class="theme-group">
            <p class="theme-name">${escapeHtml(group.theme)}</p>
            <div class="theme-point-list">${pointsHtml}</div>
          </li>
        `
      }).join('')}
    </ul>`
    : '<p class="empty-text">暂无核心主题时间线数据。</p>'

  const bertopicInsightHtml = formattedBertopicInsight.value
    ? `<div class="prose">${formattedBertopicInsight.value}</div>`
    : '<p class="empty-text">暂无 AI 深度解读。请重新生成报告以补齐该区块。</p>'
  const bertopicNarrativeHtml = `
    <div class="narrative-grid">
      <article class="narrative-card">
        <p class="narrative-title">时序摘要</p>
        <p class="narrative-text">${escapeHtml(bertopicTemporalNarrative.value.summary || '暂无结构化时序摘要。')}</p>
      </article>
      <article class="narrative-card">
        <p class="narrative-title">迁移信号</p>
        ${bertopicTemporalNarrative.value.shiftSignals.length
          ? `<ul class="bullet-list compact">${bertopicTemporalNarrative.value.shiftSignals.map((item) => `<li>${escapeHtml(item)}</li>`).join('')}</ul>`
          : '<p class="empty-text">暂无明显迁移信号。</p>'}
      </article>
      <article class="narrative-card">
        <p class="narrative-title">关注提醒</p>
        ${bertopicTemporalNarrative.value.watchpoints.length
          ? `<ul class="bullet-list compact">${bertopicTemporalNarrative.value.watchpoints.map((item) => `<li>${escapeHtml(item)}</li>`).join('')}</ul>`
          : '<p class="empty-text">暂无额外提醒。</p>'}
      </article>
    </div>
  `

  const legacySectionsHtml = legacyContext.value.sections.length
    ? `<div class="evidence-grid">
      ${legacyContext.value.sections.map((section) => `
        <article class="panel" id="${escapeHtml(section.anchorId)}">
          <header class="panel-header">
            <h3>${escapeHtml(section.label)}</h3>
            <p class="panel-subtitle">${escapeHtml(section.sourceLabel || '文字解读段落')}</p>
          </header>
          <span class="source-pill">${escapeHtml(getNarrativeSourceLabel(section.source))}</span>
          <p class="evidence-text">${escapeHtml(section.text)}</p>
        </article>
      `).join('')}
    </div>`
    : '<p class="empty-text">当前报告未找到可展示的旧版 explain / report 段落。</p>'

  const legacyLongformHtml = (legacyContext.value.fullText || legacyContext.value.manualText)
    ? `<div class="chart-grid-2" style="margin-top:14px;">
      ${legacyContext.value.fullText ? `
        <details class="panel">
          <summary class="details-summary">查看 legacy report 长文</summary>
          <pre class="evidence-pre">${escapeHtml(legacyContext.value.fullText)}</pre>
        </details>
      ` : ''}
      ${legacyContext.value.manualText ? `
        <details class="panel">
          <summary class="details-summary">查看人工补充文本</summary>
          <pre class="evidence-pre">${escapeHtml(legacyContext.value.manualText)}</pre>
        </details>
      ` : ''}
    </div>`
    : ''

  const conclusionHtml = hasConclusionMiningContent.value
    ? `
      <div class="callout">
        <p class="callout-kicker">执行摘要</p>
        <p class="callout-text">${escapeHtml(conclusionMining.value.executiveSummary || '暂无执行摘要。')}</p>
        ${renderModuleLinks(conclusionMining.value.supportingModules, '依据模块：')}
      </div>
      <div class="insight-grid" style="margin-top:14px;">
        ${conclusionGroups.value.map((group) => `
          <article class="insight-card">
            <p class="insight-title">${escapeHtml(group.title)}</p>
            <p class="panel-subtitle">${escapeHtml(group.subtitle)}</p>
            ${group.items.length
              ? group.items.map((item) => `
                <div class="sub-block">
                  ${item.headline ? `<p class="sub-block-title">${escapeHtml(item.headline)}</p>` : ''}
                  <p class="narrative-text">${escapeHtml(item.text)}</p>
                  ${renderModuleLinks(item.supportingModules)}
                </div>
              `).join('')
              : `<p class="empty-text" style="margin-top:12px;">${escapeHtml(group.emptyText)}</p>`}
          </article>
        `).join('')}
      </div>
    `
    : '<p class="empty-text">当前报告未提炼出新的结论挖掘结果。</p>'

  const highlightHtml = highlightPoints.value.length
    ? `<ul class="bullet-list">
      ${highlightPoints.value.map((point) => `<li>${escapeHtml(point)}</li>`).join('')}
    </ul>`
    : '<p class="empty-text">暂无洞察亮点。</p>'

  const insightHtml = insightCards.value.length
    ? `<div class="insight-grid">
      ${insightCards.value.map((insight) => {
        const points = Array.isArray(insight.points) ? insight.points : []
        const pointHtml = points.length
          ? `<ul class="bullet-list compact">${points.map((point) => `<li>${escapeHtml(point)}</li>`).join('')}</ul>`
          : '<p class="empty-text">暂无补充要点。</p>'
        return `
          <article class="insight-card">
            <p class="insight-title">${escapeHtml(insight.title)}</p>
            <p class="insight-headline">${escapeHtml(insight.headline)}</p>
            ${pointHtml}
          </article>
        `
      }).join('')}
    </div>`
    : '<p class="empty-text">暂无重点结论。</p>'

  const loadedSuffix = reportState.lastLoaded
    ? ` · 前端读取：${escapeHtml(reportState.lastLoaded)}`
    : ''
  const analysisLoadedSuffix = analysisState.lastLoaded
    ? ` · 图表读取：${escapeHtml(analysisState.lastLoaded)}`
    : ''

  const chartJson = JSON.stringify(chartOptions)
  const chartRuntimeJson = JSON.stringify(chartRuntime)
  const closeScript = '</scr' + 'ipt>'

  return `<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>${escapeHtml(reportMeta.value.title)}</title>
  <style>
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: #f8fafc;
      color: #0f172a;
      font-family: "PingFang SC", "Microsoft YaHei", "Noto Sans SC", sans-serif;
    }
    h1, h2, h3, p { margin: 0; }
    .report-root { max-width: 1240px; margin: 0 auto; padding: 24px; display: grid; gap: 16px; }
    .panel {
      background: #ffffff;
      border: 1px solid #e2e8f0;
      border-radius: 22px;
      padding: 18px;
    }
    .section-kicker {
      font-size: 12px;
      letter-spacing: 0.14em;
      text-transform: uppercase;
      color: #64748b;
      font-weight: 700;
      margin-bottom: 10px;
    }
    .title { font-size: 30px; line-height: 1.2; font-weight: 700; color: #0f172a; margin-bottom: 6px; }
    .subtitle { font-size: 14px; color: #334155; margin-bottom: 6px; }
    .meta-line { font-size: 12px; color: #64748b; }
    .metric-grid { display: grid; gap: 12px; margin-top: 14px; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); }
    .metric-card {
      border: 1px solid #e2e8f0;
      border-radius: 16px;
      background: #ffffff;
      padding: 14px;
    }
    .metric-label {
      font-size: 12px;
      letter-spacing: 0.12em;
      text-transform: uppercase;
      color: #64748b;
      font-weight: 700;
      margin-bottom: 8px;
    }
    .metric-value {
      color: #0f172a;
      font-size: 18px;
      font-weight: 700;
      line-height: 1.3;
    }
    .metric-value-lg { font-size: 30px; }
    .metric-sub { margin-top: 6px; color: #334155; font-size: 13px; }
    .chart-grid-3 { display: grid; gap: 16px; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); }
    .chart-grid-2 { display: grid; gap: 16px; grid-template-columns: repeat(auto-fit, minmax(340px, 1fr)); }
    .analysis-overview-grid { display: grid; gap: 16px; grid-template-columns: repeat(auto-fit, minmax(380px, 1fr)); }
    .analysis-overview-card {
      border: 1px solid #e2e8f0;
      border-radius: 18px;
      background: #ffffff;
      padding: 18px;
    }
    .analysis-overview-bottom {
      display: grid;
      gap: 12px;
      margin-top: 14px;
    }
    .split-grid { display: grid; gap: 16px; }
    .bertopic-grid { display: grid; gap: 16px; }
    .evidence-grid { display: grid; gap: 16px; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); }
    .panel-header { margin-bottom: 12px; }
    .panel-header h3 {
      font-size: 18px;
      color: #0f172a;
      line-height: 1.3;
      font-weight: 700;
    }
    .panel-subtitle {
      margin-top: 6px;
      color: #475569;
      font-size: 13px;
      line-height: 1.5;
    }
    .chart { width: 100%; height: 360px; }
    .chart.chart-sm { height: 320px; }
    .chart-empty {
      height: 360px;
      border-radius: 14px;
      border: 1px dashed #cbd5e1;
      background: #f8fafc;
      display: flex;
      align-items: center;
      justify-content: center;
      color: #64748b;
      font-size: 14px;
    }
    .chart-empty.chart-sm { height: 320px; }
    .readiness-grid {
      display: grid;
      gap: 12px;
      margin-top: 14px;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
    }
    .readiness-card {
      border: 1px solid #e2e8f0;
      border-radius: 16px;
      background: #ffffff;
      padding: 14px;
    }
    .readiness-card.is-ready {
      border-color: #bfdbfe;
      background: #eff6ff;
    }
    .readiness-head {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
    }
    .readiness-head p {
      color: #0f172a;
      font-size: 14px;
      font-weight: 700;
    }
    .readiness-head span {
      border-radius: 999px;
      background: #e2e8f0;
      color: #475569;
      font-size: 11px;
      font-weight: 700;
      padding: 4px 8px;
    }
    .readiness-card.is-ready .readiness-head span {
      background: #dbeafe;
      color: #1d4ed8;
    }
    .readiness-detail {
      margin-top: 8px;
      color: #334155;
      font-size: 13px;
      line-height: 1.7;
    }
    .callout {
      border: 1px solid #bfdbfe;
      border-radius: 18px;
      background: #eff6ff;
      padding: 16px;
    }
    .callout-kicker {
      font-size: 12px;
      letter-spacing: 0.14em;
      text-transform: uppercase;
      color: #1d4ed8;
      font-weight: 700;
    }
    .callout-text {
      margin-top: 8px;
      color: #0f172a;
      font-size: 14px;
      line-height: 1.85;
    }
    .callout-meta {
      margin-top: 8px;
      color: #64748b;
      font-size: 12px;
    }
    .stage-list, .theme-group-list { list-style: none; padding: 0; margin: 0; display: grid; gap: 12px; }
    .stage-item {
      border: 1px solid #e2e8f0;
      border-radius: 14px;
      padding: 12px;
      background: #ffffff;
    }
    .stage-head { display: flex; justify-content: space-between; gap: 8px; align-items: center; }
    .stage-title { color: #0f172a; font-size: 15px; font-weight: 700; }
    .stage-badge {
      color: #1d4ed8;
      font-size: 12px;
      font-weight: 700;
      background: #dbeafe;
      border: 1px solid #bfdbfe;
      border-radius: 999px;
      padding: 3px 9px;
    }
    .stage-meta { margin-top: 6px; font-size: 12px; color: #64748b; }
    .stage-highlight { margin-top: 8px; color: #334155; font-size: 13px; line-height: 1.7; }
    .bertopic-intro { font-size: 14px; color: #334155; line-height: 1.75; }
    .bertopic-insight {
      border: 1px solid #bfdbfe;
      border-radius: 16px;
      background: #eff6ff;
      padding: 14px;
      margin-top: 12px;
    }
    .bertopic-insight-title {
      font-size: 14px;
      color: #0f172a;
      font-weight: 700;
      margin-bottom: 10px;
    }
    .narrative-grid {
      display: grid;
      gap: 12px;
      grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
      margin-top: 14px;
    }
    .narrative-card {
      border: 1px solid #e2e8f0;
      border-radius: 16px;
      background: #ffffff;
      padding: 14px;
    }
    .narrative-title {
      font-size: 12px;
      letter-spacing: 0.12em;
      text-transform: uppercase;
      color: #64748b;
      font-weight: 700;
      margin-bottom: 10px;
    }
    .narrative-text {
      color: #334155;
      font-size: 14px;
      line-height: 1.75;
    }
    .theme-timeline {
      border: 1px solid #e2e8f0;
      border-radius: 16px;
      background: #ffffff;
      padding: 14px;
      max-height: 560px;
      overflow: auto;
    }
    .theme-group { display: grid; gap: 8px; }
    .theme-name { color: #0f172a; font-size: 14px; font-weight: 700; }
    .theme-point-list {
      border-left: 2px solid #dbeafe;
      padding-left: 10px;
      display: grid;
      gap: 8px;
    }
    .theme-point {
      border: 1px solid #e2e8f0;
      border-radius: 12px;
      padding: 10px;
      background: #f8fafc;
    }
    .theme-point-head { display: flex; justify-content: space-between; gap: 8px; align-items: center; }
    .theme-point-head p {
      color: #0f172a;
      font-size: 13px;
      font-weight: 600;
    }
    .theme-point-head span {
      color: #1d4ed8;
      font-size: 12px;
      font-weight: 700;
    }
    .theme-point-meta { margin-top: 5px; font-size: 12px; color: #64748b; }
    .bullet-list {
      margin: 0;
      padding-left: 18px;
      color: #334155;
      line-height: 1.7;
      display: grid;
      gap: 8px;
      font-size: 14px;
    }
    .bullet-list.compact { gap: 6px; font-size: 13px; }
    .insight-grid { display: grid; gap: 12px; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); margin-top: 12px; }
    .insight-card {
      border: 1px solid #e2e8f0;
      border-radius: 14px;
      padding: 12px;
      background: #ffffff;
    }
    .insight-title {
      font-size: 12px;
      letter-spacing: 0.12em;
      text-transform: uppercase;
      color: #64748b;
      font-weight: 700;
    }
    .insight-headline {
      margin-top: 8px;
      color: #0f172a;
      font-size: 15px;
      font-weight: 700;
      line-height: 1.5;
    }
    .card-head {
      display: flex;
      justify-content: space-between;
      gap: 12px;
      align-items: flex-start;
    }
    .source-pill, .meta-chip, .anchor-chip {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      border-radius: 999px;
      border: 1px solid #cbd5e1;
      padding: 5px 10px;
      font-size: 11px;
      font-weight: 700;
    }
    .source-pill {
      background: #f8fafc;
      color: #334155;
    }
    .meta-chip {
      background: #f8fafc;
      color: #475569;
    }
    .anchor-chip {
      text-decoration: none;
      background: #ffffff;
      color: #1d4ed8;
      border-color: #bfdbfe;
    }
    .chip-row {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-top: 10px;
    }
    .sub-block {
      margin-top: 12px;
      border-top: 1px solid #e2e8f0;
      padding-top: 12px;
    }
    .sub-block-title {
      color: #64748b;
      font-size: 12px;
      font-weight: 700;
      letter-spacing: 0.12em;
      text-transform: uppercase;
      margin-bottom: 8px;
    }
    .table-shell {
      margin-top: 12px;
      border: 1px solid #e2e8f0;
      border-radius: 14px;
      overflow: hidden;
    }
    .data-table {
      width: 100%;
      border-collapse: collapse;
      font-size: 13px;
    }
    .data-table th {
      text-align: left;
      background: #f8fafc;
      color: #64748b;
      font-size: 11px;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      padding: 10px 12px;
    }
    .data-table td {
      padding: 10px 12px;
      border-top: 1px solid #e2e8f0;
      color: #334155;
      vertical-align: top;
    }
    .evidence-text {
      margin-top: 12px;
      color: #334155;
      font-size: 14px;
      line-height: 1.85;
      white-space: pre-wrap;
    }
    .details-summary {
      cursor: pointer;
      color: #0f172a;
      font-size: 14px;
      font-weight: 700;
    }
    .evidence-pre {
      margin-top: 12px;
      max-height: 340px;
      overflow: auto;
      white-space: pre-wrap;
      color: #334155;
      font-size: 13px;
      line-height: 1.85;
    }
    .empty-text { color: #64748b; font-size: 14px; line-height: 1.75; }
    .prose { color: #334155; line-height: 1.75; font-size: 14px; }
    .prose :first-child { margin-top: 0; }
    .prose :last-child { margin-bottom: 0; }
    .prose p, .prose ul, .prose ol, .prose blockquote { margin: 0 0 10px; }
    .prose ul, .prose ol { padding-left: 18px; }
    .prose blockquote {
      margin-left: 0;
      padding: 8px 10px;
      border-left: 3px solid #93c5fd;
      background: #dbeafe;
      border-radius: 6px;
      color: #1e3a8a;
    }
    @media (min-width: 1120px) {
      .analysis-overview-bottom { grid-template-columns: 0.95fr 1.05fr; }
      .split-grid { grid-template-columns: 1.6fr 1fr; }
      .bertopic-grid { grid-template-columns: 1.6fr 1fr; }
    }
    @media (max-width: 768px) {
      .report-root { padding: 16px; }
      .panel { border-radius: 16px; padding: 14px; }
      .title { font-size: 24px; }
      .chart, .chart-empty { height: 300px; }
      .theme-timeline { max-height: none; }
    }
  </style>
  <script src="https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js">${closeScript}
</head>
<body>
  <main class="report-root">
    <section class="panel">
      <p class="section-kicker">报告概览</p>
      <h1 class="title">${escapeHtml(reportMeta.value.title)}</h1>
      <p class="subtitle">${escapeHtml(reportMeta.value.subtitle)}</p>
      <p class="meta-line">${escapeHtml(reportMeta.value.rangeText)} · 最近更新：${escapeHtml(reportMeta.value.lastUpdated)}${loadedSuffix}</p>

      <div class="metric-grid">
        <article class="metric-card">
          <p class="metric-label">总声量</p>
          <p class="metric-value metric-value-lg">${escapeHtml(formatNumber(metrics.value.totalVolume))}</p>
        </article>
        <article class="metric-card">
          <p class="metric-label">峰值</p>
          <p class="metric-value">${escapeHtml(formatNumber(metrics.value.peak.value))}</p>
          <p class="metric-sub">${escapeHtml(metrics.value.peak.date || '未提供')}</p>
        </article>
        <article class="metric-card">
          <p class="metric-label">情感结构</p>
          <p class="metric-value">正向 ${escapeHtml(formatRate(metrics.value.positiveRate))}</p>
          <p class="metric-sub">中性 ${escapeHtml(formatRate(metrics.value.neutralRate))} · 负向 ${escapeHtml(formatRate(metrics.value.negativeRate))}</p>
        </article>
        <article class="metric-card">
          <p class="metric-label">内容结构</p>
          <p class="metric-value">报道 ${escapeHtml(formatRate(metrics.value.factualRatio))}</p>
          <p class="metric-sub">观点 ${escapeHtml(formatRate(metrics.value.opinionRatio))}</p>
        </article>
      </div>
    </section>

    <section class="panel">
      <p class="section-kicker">基础分析总览</p>
      <h2 class="panel-header" style="margin-bottom:0;">
        <span style="display:block;font-size:20px;color:#0f172a;font-weight:700;">基础分析已压缩进报告结构</span>
        <span class="panel-subtitle">每个模块保留一张代表图，并直接结合摘要与综合解读。图表读取来自 /api/analyze/results${analysisLoadedSuffix}</span>
      </h2>
      ${readinessHtml}
      ${analysisMainFindingHtml}
      <div style="margin-top:16px;">
        ${analysisOverviewHtml}
      </div>
    </section>

    <section class="chart-grid-3">
      ${renderChartPanel('channel', '渠道分布')}
      ${renderChartPanel('sentiment', '情感态度')}
      ${renderChartPanel('contentSplit', '内容结构')}
    </section>

    <section class="split-grid">
      ${renderChartPanel('trend', '时间趋势')}
      <article class="panel">
        <header class="panel-header">
          <h3>节奏拆解</h3>
          <p class="panel-subtitle">传播阶段</p>
        </header>
        ${stageContent}
      </article>
    </section>

    ${deepAnalysisHtml}

    <section class="panel">
      <header class="panel-header">
        <h3>核心关注点随时间的变化</h3>
        <p class="panel-subtitle">BERTopic 主题演化</p>
      </header>
      <p class="bertopic-intro">${escapeHtml(bertopicOverviewText.value)}</p>
      <div class="bertopic-insight">
        <p class="bertopic-insight-title">AI 深度解读</p>
        ${bertopicInsightHtml}
      </div>
      ${bertopicNarrativeHtml}
      <div class="bertopic-grid" style="margin-top: 14px;">
        ${renderChartPanel('bertopicTimeline', '主题热度时间轴', '背景浅蓝色区域代表每天的样本总量走势，彩色折线展示了几个核心话题在这些天的讨论热度变化。')}
        <aside class="theme-timeline">
          <header class="panel-header">
            <h3>核心主题时间线</h3>
            <p class="panel-subtitle">包含 ${escapeHtml(formatNumber(themeActivePoints.value.length))} 个主题节点</p>
          </header>
          ${themeTimelineHtml}
        </aside>
      </div>
    </section>

    <section class="chart-grid-2">
      ${renderChartPanel('keyword', '关键词热度')}
      ${renderChartPanel('theme', '主题分布')}
    </section>

    <section class="panel">
      <header class="panel-header">
        <h3>原始依据</h3>
        <p class="panel-subtitle">旧版 report 的文字解读段落与长文上下文。</p>
      </header>
      ${!sourceReadiness.value.explainReady
        ? '<div class="callout"><p class="callout-text">当前区间还没有补齐总体文字解读，导出报告先展示 AI 摘要和统计结果；下方仅列出当前可用的旧版依据。</p></div>'
        : ''}
      ${legacySectionsHtml}
      ${legacyLongformHtml}
    </section>

    <section class="panel">
      <header class="panel-header">
        <h3>结论挖掘</h3>
        <p class="panel-subtitle">从基础分析、文字解读与结构化研判中回收可执行结论。</p>
      </header>
      ${conclusionHtml}
    </section>

    <section class="panel">
      <header class="panel-header">
        <h3>重点结论</h3>
        <p class="panel-subtitle">洞察亮点</p>
      </header>
      ${highlightHtml}
      ${insightHtml}
    </section>
  </main>

  <script>
    const chartOptions = ${chartJson};
    const chartRuntime = ${chartRuntimeJson};
    const instances = [];
    chartRuntime.forEach((item) => {
      if (!item.hasData) return;
      const el = document.getElementById(item.id);
      const option = chartOptions[item.optionKey];
      if (!el || !option) return;
      const chart = echarts.init(el);
      chart.setOption(option, true);
      instances.push(chart);
    });
    window.addEventListener('resize', () => {
      instances.forEach((chart) => chart.resize());
    });
  ${closeScript}
</body>
</html>`
}

const exportHtmlReport = async () => {
  if (!report.value) return
  exporting.value = true
  try {
    const html = buildHtmlDocument()
    const blob = new Blob([html], { type: 'text/html' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `${reportMeta.value.title || 'report'}.html`
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    URL.revokeObjectURL(url)
  } finally {
    exporting.value = false
  }
}
</script>
