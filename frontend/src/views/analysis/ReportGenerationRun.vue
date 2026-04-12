<template>
  <div class="space-y-6 pb-12">
    <section class="card-surface space-y-5 p-6">
      <div class="flex flex-wrap items-center justify-between gap-3">
        <div class="space-y-1">
          <h2 class="text-xl font-semibold text-primary">运行报告</h2>
          <p class="text-sm text-secondary">选择数据集并执行舆情报告生成任务</p>
        </div>
        <div class="flex flex-wrap items-center gap-2">
          <button type="button" class="btn-secondary inline-flex items-center gap-2" :disabled="topicsState.loading"
            @click="loadTopics">
            <ArrowPathIcon class="h-4 w-4" :class="topicsState.loading ? 'animate-spin' : ''" />{{ topicsState.loading ?
              '刷新中…' : '刷新专题' }}
          </button>
          <button type="button" class="btn-secondary inline-flex items-center gap-2"
            :disabled="historyState.loading || !reportForm.topic" @click="handleRefreshHistory">
            <ClockIcon class="h-4 w-4" />{{ historyState.loading ? '读取中…' : '刷新记录' }}
          </button>
        </div>
      </div>

      <div class="grid gap-4 xl:grid-cols-[1.15fr,1fr,1fr,1fr,0.8fr]">
        <label class="space-y-2 text-secondary"><span class="text-xs font-semibold text-muted">专题</span>
          <AppSelect :options="topicSelectOptions" :value="reportForm.topic"
            :disabled="topicsState.loading || !topicOptions.length" @change="reportForm.topic = $event" />
          <p v-if="topicsState.error" class="text-xs text-danger">{{ topicsState.error }}</p>
        </label>
        <label class="space-y-2 text-secondary"><span class="text-xs font-semibold text-muted">历史记录</span>
          <AppSelect :options="historySelectOptions" :value="selectedHistoryId"
            :disabled="historyState.loading || !reportHistory.length"
            :placeholder="historyState.loading ? '加载历史中…' : reportHistory.length ? '选择历史记录' : '暂无历史记录'"
            @change="handleSelectHistory" />
          <p v-if="historyState.error" class="text-xs text-muted">{{ historyState.error }}</p>
        </label>
        <label class="space-y-2 text-secondary"><span class="text-xs font-semibold text-muted">开始日期</span><input
            v-model="reportForm.start" type="date" class="input" /></label>
        <label class="space-y-2 text-secondary"><span class="text-xs font-semibold text-muted">结束日期</span><input
            v-model="reportForm.end" type="date" class="input" /></label>
        <label class="space-y-2 text-secondary"><span class="text-xs font-semibold text-muted">模式</span>
          <AppSelect :options="modeSelectOptions" :value="reportForm.mode" @change="reportForm.mode = $event" />
          <p class="text-xs text-muted">“深入”会加强本地归档、基础分析和 BERTopic 结果的交叉研读，不会额外发起外部网页检索。</p>
        </label>
      </div>

      <div class="rounded-[1.75rem] border border-soft bg-brand-soft/30 p-4">
        <div class="flex flex-wrap items-end justify-between gap-3">
          <div class="space-y-2">
            <p class="text-xs font-semibold uppercase tracking-[0.24em] text-muted">本次范围</p>
            <p class="text-sm text-secondary">建议优先复用已有区间；缺少前置结果时会自动补齐。</p>
            <p class="text-xs text-muted">建议范围：{{ availableRange.start || '--' }} → {{ availableRange.end || '--'
              }}<span v-if="availableRange.loading" class="ml-2 animate-pulse">检查中…</span><span
                v-else-if="availableRange.error" class="ml-2 text-danger">{{ availableRange.error }}</span><span
                v-else-if="availableRange.notice" class="ml-2 text-warning">{{ availableRange.notice }}</span></p>
          </div>
          <div class="flex flex-wrap gap-2">
            <button type="button" class="btn-primary inline-flex items-center gap-2" :disabled="taskState.creating"
              @click="handleCreateTask">
              <SparklesIcon class="h-4 w-4" :class="taskState.creating ? 'animate-pulse' : ''" />{{ taskState.creating ?
                '提交中…' : primaryActionLabel }}
            </button>
            <button type="button" class="btn-secondary inline-flex items-center gap-2" :disabled="!taskState.id"
              @click="handleRefreshTask">
              <ArrowPathIcon class="h-4 w-4" />刷新状态
            </button>
            <button type="button" class="btn-secondary inline-flex items-center gap-2" :disabled="!canCancelTask"
              @click="handleCancelTask">
              <StopIcon class="h-4 w-4" />停止任务
            </button>
            <button type="button" class="btn-secondary inline-flex items-center gap-2" :disabled="!canRetryTask"
              @click="handleRetryTask">
              <ArrowPathIcon class="h-4 w-4" />重新运行
            </button>
          </div>
        </div>
      </div>

      <div v-if="taskState.error || reportState.error"
        class="rounded-2xl border border-danger/40 bg-danger-soft px-4 py-3 text-sm text-danger">{{ taskState.error ||
          reportState.error }}</div>
    </section>

    <section v-if="!runVm.hasTask" class="card-surface space-y-4 p-6">
      <p class="text-xs font-semibold uppercase tracking-[0.24em] text-muted">运行面板</p>
      <h3 class="text-3xl font-semibold tracking-tight text-primary">创建任务后，这里会持续显示本轮分析进度。</h3>
      <p class="max-w-3xl text-sm leading-7 text-secondary">你会先看到阶段推进、关键动态和当前结果。需要更多细节时，再打开执行节点或调试详情。</p>
      <div class="grid gap-3 lg:grid-cols-3">
        <article v-for="item in idleCards" :key="item.title" class="rounded-3xl bg-base-soft px-5 py-5">
          <p class="text-xs font-semibold uppercase tracking-[0.18em] text-muted">{{ item.kicker }}</p>
          <p class="mt-3 text-base font-semibold text-primary">{{ item.title }}</p>
          <p class="mt-2 text-sm leading-6 text-secondary">{{ item.body }}</p>
        </article>
      </div>
    </section>

    <section v-else class="card-surface overflow-hidden p-0">
      <header class="border-b border-soft bg-brand-soft/20 px-5 py-5">
        <div class="flex flex-wrap items-start justify-between gap-4">
          <div class="space-y-2">
            <div class="flex flex-wrap items-center gap-2 text-xs">
              <span class="rounded-full px-3 py-1 font-semibold" :class="badgeClass(runVm.runSummary.statusTone)">{{
                runVm.runSummary.statusText }}</span>
              <span class="text-muted">{{ runVm.runSummary.modeText }}</span>
              <span class="text-muted">范围 {{ runVm.runSummary.rangeText }}</span>
              <span class="text-muted">{{ runVm.runSummary.connectionText }}</span>
            </div>
            <div>
              <h3 class="text-2xl font-semibold text-primary">{{ runVm.runSummary.title }}</h3>
              <p class="mt-1 text-sm text-secondary">{{ runVm.runSummary.headline }}</p>
              <p class="mt-1 text-xs text-muted">{{ runVm.runSummary.subline }}</p>
            </div>
          </div>
          <div class="flex flex-wrap gap-2">
            <button v-if="runVm.canIntervene" type="button" class="btn-primary inline-flex items-center gap-2"
              @click="openDebugDrawer(hasPendingApprovals ? 'approvals' : 'events')">
              <ExclamationTriangleIcon class="h-4 w-4" />{{ hasPendingApprovals ? `需要介入 (${pendingApprovalCount})` :
              '查看失败详情' }}
            </button>
            <button type="button" class="btn-secondary inline-flex items-center gap-2" @click="agentsDrawerOpen = true">
              <RectangleStackIcon class="h-4 w-4" />执行节点
            </button>
            <button type="button" class="btn-secondary inline-flex items-center gap-2"
              @click="openDebugDrawer('events')">
              <WrenchScrewdriverIcon class="h-4 w-4" />调试详情
            </button>
            <button type="button" class="btn-secondary inline-flex items-center gap-2" :disabled="!canOpenResults"
              @click="goToResultsPage">
              <DocumentTextIcon class="h-4 w-4" />语义报告
            </button>
            <button type="button" class="btn-secondary inline-flex items-center gap-2" :disabled="!canOpenAiResults"
              @click="goToAiResultsPage">
              <DocumentDuplicateIcon class="h-4 w-4" />正式文稿
            </button>
          </div>
        </div>
        <div class="mt-4 space-y-2">
          <div class="flex items-center justify-between gap-3 text-xs"><span class="text-secondary">主任务进度</span><span
              class="font-semibold text-primary">{{ runVm.runSummary.progress }}%</span></div>
          <div class="h-2.5 overflow-hidden rounded-full bg-base-soft">
            <div
              class="h-full rounded-full bg-gradient-to-r from-[rgb(var(--color-brand-600))] to-[rgb(var(--color-accent-500))]"
              :style="{ width: `${runVm.runSummary.progress}%` }" />
          </div>
        </div>
      </header>

      <div class="grid gap-0 xl:grid-cols-[minmax(0,1.35fr),minmax(300px,0.85fr)]">
        <main class="space-y-4 p-5">
          <section class="rounded-[1.75rem] bg-surface p-5">
            <div class="mb-4 flex items-center justify-between gap-3">
              <div>
                <p class="text-xs font-semibold uppercase tracking-[0.24em] text-muted">阶段进度</p>
                <h4 class="text-lg font-semibold text-primary">本轮进度</h4>
              </div><span class="text-xs text-muted">{{ runVm.stageTimeline.length }} 个阶段</span>
            </div>
            <ol class="space-y-3">
              <li v-for="stage in runVm.stageTimeline" :key="stage.id"
                class="grid grid-cols-[12px,minmax(0,1fr)] gap-3">
                <div class="mt-2 h-full w-1 rounded-full" :class="stageLineClass(stage.status)" />
                <article class="rounded-3xl px-4 py-4" :class="stageCardClass(stage.status)">
                  <div class="flex items-start justify-between gap-3">
                    <div class="min-w-0">
                      <div class="flex items-center gap-3"><span
                          class="inline-flex h-8 w-8 items-center justify-center rounded-full bg-surface text-sm font-semibold text-primary">{{
                          stage.order }}</span>
                        <p class="text-base font-semibold text-primary">{{ stage.label }}</p>
                      </div>
                      <p class="mt-3 text-sm text-secondary">{{ stage.description }}</p>
                      <p class="mt-2 text-xs text-muted">{{ stage.detail }}</p>
                    </div>
                    <span class="rounded-full px-3 py-1 text-xs font-semibold" :class="badgeClass(stage.status)">{{
                      stage.statusText }}</span>
                  </div>
                </article>
              </li>
            </ol>
          </section>

          <section class="rounded-[1.75rem] bg-surface p-5">
            <div class="mb-4 flex items-center justify-between gap-3">
              <div>
                <p class="text-xs font-semibold uppercase tracking-[0.24em] text-muted">关键动态</p>
                <h4 class="text-lg font-semibold text-primary">刚刚发生了什么</h4>
              </div><span class="text-xs text-muted">最近 {{ runVm.timelineEvents.length }} 条</span>
            </div>
            <div v-if="runVm.timelineEvents.length" class="space-y-3">
              <article v-for="event in runVm.timelineEvents" :key="event.id || `${event.type}-${event.timestamp}`"
                class="grid grid-cols-[10px,minmax(0,1fr)] gap-3">
                <div class="mt-2 h-2 w-2 rounded-full" :class="dotClass(event.primaryStatus)" />
                <div>
                  <div class="flex flex-wrap items-center gap-3">
                    <p class="text-sm font-semibold text-primary">{{ event.title }}</p><span
                      class="text-[11px] text-muted">{{ event.label }}</span><span class="text-[11px] text-muted">{{
                        event.timestampLabel }}</span>
                  </div>
                  <p v-if="event.message" class="mt-1 text-sm text-secondary">{{ event.message }}</p>
                  <p v-if="event.nextStep" class="mt-2 text-xs text-muted">下一步：{{ event.nextStep }}</p>
                </div>
              </article>
            </div>
            <div v-else class="rounded-3xl bg-base-soft px-4 py-5 text-sm text-secondary">创建任务后，这里会显示关键事件。</div>
          </section>
        </main>

        <aside class="space-y-4 border-t border-soft bg-brand-soft/10 p-5 xl:border-l xl:border-t-0">
          <section class="rounded-[1.75rem] bg-surface p-5">
            <p class="text-xs font-semibold uppercase tracking-[0.24em] text-muted">运行状态</p>
            <p class="mt-3 text-base font-semibold text-primary">{{ runVm.graphObservability.currentStageLabel }}</p>
            <p class="mt-2 text-sm leading-6 text-secondary">{{ runVm.graphObservability.currentStageMessage }}</p>
            <div class="mt-4 grid gap-2 sm:grid-cols-2">
              <article class="rounded-3xl bg-base-soft px-4 py-3">
                <p class="text-xs font-semibold uppercase tracking-[0.18em] text-muted">当前节点</p>
                <p class="mt-2 text-sm text-secondary">{{ runVm.graphObservability.currentNodeLabel }}</p>
              </article>
              <article class="rounded-3xl bg-base-soft px-4 py-3">
                <p class="text-xs font-semibold uppercase tracking-[0.18em] text-muted">当前执行者</p>
                <p class="mt-2 text-sm text-secondary">{{ runVm.graphObservability.currentActorLabel }}</p>
              </article>
              <article class="rounded-3xl bg-base-soft px-4 py-3">
                <p class="text-xs font-semibold uppercase tracking-[0.18em] text-muted">下一步</p>
                <p class="mt-2 text-sm text-secondary">{{ runVm.graphObservability.nextStep }}</p>
              </article>
              <article class="rounded-3xl bg-base-soft px-4 py-3">
                <p class="text-xs font-semibold uppercase tracking-[0.18em] text-muted">当前线程</p>
                <p class="mt-2 text-sm text-secondary">{{ runVm.graphObservability.threadLabel }}</p>
                <p class="mt-2 text-xs text-muted">{{ runVm.graphObservability.connectionLabel }}</p>
              </article>
            </div>
          </section>
          <section class="rounded-[1.75rem] bg-surface p-5">
            <p class="text-xs font-semibold uppercase tracking-[0.24em] text-muted">路由与分派</p>
            <p class="mt-3 text-sm leading-6 text-secondary">{{ runVm.graphObservability.routerSummary }}</p>
            <div class="mt-4 space-y-3">
              <article class="rounded-3xl bg-base-soft px-4 py-4">
                <p class="text-xs font-semibold uppercase tracking-[0.18em] text-muted">已分派节点</p>
                <p class="mt-2 text-sm text-secondary">{{ runVm.graphObservability.dispatchTargets.length ?
                  runVm.graphObservability.dispatchTargets.join('、') : '当前还没有 specialist 分派记录。' }}</p>
                <p v-if="runVm.graphObservability.dispatchCount" class="mt-2 text-xs text-muted">本轮已生成 {{
                  runVm.graphObservability.dispatchCount }} 个分派。</p>
              </article>
              <article v-if="runVm.graphObservability.routerFacets.length" class="rounded-3xl bg-base-soft px-4 py-4">
                <p class="text-xs font-semibold uppercase tracking-[0.18em] text-muted">关注维度</p>
                <p class="mt-2 text-sm text-secondary">{{ runVm.graphObservability.routerFacets.join('、') }}</p>
              </article>
              <article v-if="runVm.graphObservability.dispatchArtifacts.length"
                class="rounded-3xl bg-base-soft px-4 py-4">
                <p class="text-xs font-semibold uppercase tracking-[0.18em] text-muted">预计覆盖</p>
                <p class="mt-2 text-sm text-secondary">{{ runVm.graphObservability.dispatchArtifacts.join('、') }}</p>
              </article>
            </div>
          </section>
          <section class="rounded-[1.75rem] bg-surface p-5">
            <p class="text-xs font-semibold uppercase tracking-[0.24em] text-muted">裁决摘要</p>
            <div class="mt-4 space-y-3">
              <article class="rounded-3xl bg-base-soft px-4 py-4">
                <div class="flex items-start justify-between gap-3">
                  <div>
                    <p class="text-xs font-semibold uppercase tracking-[0.18em] text-muted">当前判定</p>
                    <p class="mt-2 text-base font-semibold text-primary">{{
                      runVm.decisionObservability.utilityDecisionLabel }}</p>
                  </div>
                  <span class="rounded-full px-3 py-1 text-xs font-semibold"
                    :class="badgeClass(runVm.decisionObservability.hasPendingApproval ? 'running' : (runVm.decisionObservability.utilityDecision === 'pass' ? 'completed' : 'pending'))">{{
                      runVm.decisionObservability.utilityDecision }}</span>
                </div>
                <p class="mt-3 text-sm leading-6 text-secondary">{{ runVm.decisionObservability.finalReason ||
                  '当前还没有决策说明。' }}</p>
              </article>
              <article class="rounded-3xl bg-base-soft px-4 py-4">
                <p class="text-xs font-semibold uppercase tracking-[0.18em] text-muted">下一步动作</p>
                <p class="mt-2 text-sm text-secondary">{{ runVm.decisionObservability.nextAction }}</p>
              </article>
              <article class="rounded-3xl bg-base-soft px-4 py-4">
                <p class="text-xs font-semibold uppercase tracking-[0.18em] text-muted">缺失维度</p>
                <p class="mt-2 text-sm text-secondary">{{ runVm.decisionObservability.missingDimensions.length ?
                  runVm.decisionObservability.missingDimensions.slice(0, 3).join('、') : '当前没有缺失维度。' }}</p>
              </article>
              <article class="rounded-3xl bg-base-soft px-4 py-4">
                <p class="text-xs font-semibold uppercase tracking-[0.18em] text-muted">回退与审查</p>
                <p class="mt-2 text-sm text-secondary">{{ runVm.decisionObservability.fallbackSummary }}</p>
                <p class="mt-2 text-xs text-muted">审批状态：{{ runVm.decisionObservability.approvalDecision }}</p>
              </article>
            </div>
          </section>
          <section class="rounded-[1.75rem] bg-surface p-5">
            <p class="text-xs font-semibold uppercase tracking-[0.24em] text-muted">当前产物</p>
            <p v-if="runVm.artifactObservability.upcomingLine" class="mt-3 text-sm text-secondary">{{
              runVm.artifactObservability.upcomingLine }}</p>
            <div class="mt-4 space-y-2">
              <article v-for="artifact in runVm.artifactObservability.items" :key="artifact.key"
                class="rounded-3xl bg-base-soft px-4 py-4">
                <div class="flex items-start justify-between gap-3">
                  <div>
                    <p class="text-sm font-semibold text-primary">{{ artifact.label }}</p>
                    <p class="mt-1 text-xs text-secondary">{{ artifact.description }}</p>
                  </div>
                  <span class="rounded-full px-3 py-1 text-xs font-semibold"
                    :class="artifact.ready ? 'bg-success-soft text-success' : (artifact.isCurrent ? 'bg-brand-soft text-brand' : 'bg-base-soft text-secondary')">{{
                    artifact.statusText }}</span>
                </div>
                <div class="mt-3 grid gap-2 text-xs text-muted">
                  <p>生成时间：{{ artifact.createdAtLabel }}</p>
                  <p>来源链：{{ artifact.sourceLabel }}</p>
                  <p v-if="artifact.reviewState">审批状态：{{ artifact.reviewState }}</p>
                  <p v-if="artifact.fallbackState">回退情况：{{ artifact.fallbackState }}</p>
                </div>
              </article>
            </div>
          </section>
          <section class="rounded-[1.75rem] bg-surface p-5">
            <p class="text-xs font-semibold uppercase tracking-[0.24em] text-muted">审批与恢复</p>
            <div class="mt-4 rounded-3xl bg-base-soft px-4 py-4">
              <div class="flex items-start justify-between gap-3">
                <div>
                  <p class="text-sm font-semibold text-primary">{{ runVm.approvalObservability.compactStatus }}</p>
                  <p class="mt-2 text-sm leading-6 text-secondary">{{ runVm.approvalObservability.reason }}</p>
                </div>
                <button v-if="runVm.approvalObservability.canOpenPanel" type="button" class="btn-secondary"
                  @click="openDebugDrawer('approvals')">查看详情</button>
              </div>
              <div class="mt-3 grid gap-2 text-xs text-muted">
                <p v-if="runVm.approvalObservability.affectedLabel">受影响内容：{{ runVm.approvalObservability.affectedLabel
                  }}</p>
                <p v-if="runVm.approvalObservability.actionSummary">可选动作：{{ runVm.approvalObservability.actionSummary }}
                </p>
                <p v-if="runVm.approvalObservability.interruptLabel">最近 interrupt：{{ runVm.approvalObservability.interruptLabel }}</p>
                <p v-if="runVm.approvalObservability.checkpointLabel">恢复定位：{{ runVm.approvalObservability.checkpointLabel }}</p>
                <p v-if="runVm.approvalObservability.resumeLabel">恢复点：{{ runVm.approvalObservability.resumeLabel }}</p>
              </div>
            </div>
          </section>
          <section class="rounded-[1.75rem] bg-surface p-5">
            <p class="text-xs font-semibold uppercase tracking-[0.24em] text-muted">运行诊断</p>
            <div class="mt-4 grid gap-2 sm:grid-cols-2">
              <article class="rounded-3xl bg-base-soft px-4 py-3">
                <p class="text-xs font-semibold uppercase tracking-[0.18em] text-muted">运行面</p>
                <p class="mt-2 text-sm text-secondary">{{ runVm.runtimeDiagnostics.runtimeModeLabel }}</p>
              </article>
              <article class="rounded-3xl bg-base-soft px-4 py-3">
                <p class="text-xs font-semibold uppercase tracking-[0.18em] text-muted">Checkpoint</p>
                <p class="mt-2 text-sm text-secondary">{{ runVm.runtimeDiagnostics.checkpointBackendLabel }}</p>
              </article>
              <article class="rounded-3xl bg-base-soft px-4 py-3 sm:col-span-2">
                <p class="text-xs font-semibold uppercase tracking-[0.18em] text-muted">恢复定位</p>
                <p class="mt-2 text-sm text-secondary">{{ runVm.runtimeDiagnostics.checkpointLocatorLabel }}</p>
              </article>
              <article class="rounded-3xl bg-base-soft px-4 py-3">
                <p class="text-xs font-semibold uppercase tracking-[0.18em] text-muted">最近 Interrupt</p>
                <p class="mt-2 text-sm text-secondary">{{ runVm.runtimeDiagnostics.latestInterruptLabel }}</p>
              </article>
              <article class="rounded-3xl bg-base-soft px-4 py-3">
                <p class="text-xs font-semibold uppercase tracking-[0.18em] text-muted">Tracing</p>
                <p class="mt-2 text-sm text-secondary">{{ runVm.runtimeDiagnostics.tracingLabel }}</p>
              </article>
            </div>
          </section>
          <section v-if="runVm.inspector.failure" class="rounded-[1.75rem] bg-danger-soft px-5 py-5">
            <p class="text-xs font-semibold uppercase tracking-[0.24em] text-danger">失败焦点</p>
            <p class="mt-3 text-base font-semibold text-primary">{{ runVm.inspector.failure.title }}</p>
            <p class="mt-2 text-sm leading-6 text-secondary">{{ runVm.inspector.failure.message }}</p>
            <p v-if="runVm.inspector.failure.nextStep" class="mt-3 text-xs text-danger">下一步：{{
              runVm.inspector.failure.nextStep }}</p>
          </section>
        </aside>
      </div>
    </section>

    <Transition name="fade">
      <div v-if="agentsDrawerOpen" class="fixed inset-0 z-40 bg-black/20" @click.self="agentsDrawerOpen = false">
        <aside class="ml-auto flex h-full w-full max-w-[420px] flex-col border-l border-soft bg-surface">
          <div class="flex items-start justify-between gap-3 border-b border-soft px-5 py-4">
            <div>
              <p class="text-xs font-semibold uppercase tracking-[0.24em] text-muted">执行节点</p>
              <h3 class="text-lg font-semibold text-primary">执行节点明细</h3>
            </div><button type="button"
              class="inline-flex h-8 w-8 items-center justify-center rounded-full text-muted hover:bg-base-soft hover:text-primary"
              @click="agentsDrawerOpen = false">
              <XMarkIcon class="h-4 w-4" />
            </button>
          </div>
          <div class="flex-1 space-y-3 overflow-auto px-5 py-4">
            <article v-for="agent in runVm.agentDrawer" :key="agent.id" class="rounded-3xl bg-base-soft px-4 py-4">
              <div class="flex items-start justify-between gap-3">
                <div>
                  <p class="text-sm font-semibold text-primary">{{ agent.displayName }}</p>
                  <p class="mt-1 text-xs text-secondary">{{ agent.message || '等待启动' }}</p>
                </div><span class="rounded-full px-3 py-1 text-xs font-semibold" :class="badgeClass(agent.status)">{{
                  agent.rawStatus === 'done' ? '完成' : todoStatusLabel(agent.status) }}</span>
              </div>
              <div class="mt-3 flex flex-wrap gap-3 text-[11px] text-muted"><span v-if="agent.startedAt">开始 {{
                formatTimestamp(agent.startedAt) }}</span><span v-if="agent.updatedAt">更新 {{
                    formatTimestamp(agent.updatedAt) }}</span><span>动作 {{ agent.toolCallCount }}</span><span>回执 {{
                    agent.toolResultCount }}</span></div>
            </article>
          </div>
        </aside>
      </div>
    </Transition>

    <Transition name="slide-up">
      <div v-if="debugDrawerOpen"
        class="fixed inset-x-3 bottom-3 z-50 flex max-h-[80vh] flex-col overflow-hidden rounded-[1.5rem] border border-soft bg-surface shadow-[0_24px_80px_rgba(28,37,44,0.12)]">
        <div class="flex items-start justify-between gap-3 border-b border-soft px-5 py-4">
          <div>
            <p class="text-xs font-semibold uppercase tracking-[0.24em] text-muted">调试详情</p>
            <h3 class="text-lg font-semibold text-primary">原始事件、介入动作和运行快照</h3>
          </div><button type="button"
            class="inline-flex h-8 w-8 items-center justify-center rounded-full text-muted hover:bg-base-soft hover:text-primary"
            @click="debugDrawerOpen = false">
            <XMarkIcon class="h-4 w-4" />
          </button>
        </div>
        <div class="flex gap-2 px-5 pt-4"><button type="button" class="rounded-full px-3 py-1.5 text-xs font-semibold"
            :class="debugTab === 'events' ? 'bg-brand-soft text-brand' : 'bg-base-soft text-secondary'"
            @click="debugTab = 'events'">事件</button><button type="button"
            class="rounded-full px-3 py-1.5 text-xs font-semibold"
            :class="debugTab === 'todos' ? 'bg-brand-soft text-brand' : 'bg-base-soft text-secondary'"
            @click="debugTab = 'todos'">清单</button><button type="button"
            class="rounded-full px-3 py-1.5 text-xs font-semibold"
            :class="debugTab === 'approvals' ? 'bg-brand-soft text-brand' : 'bg-base-soft text-secondary'"
            @click="debugTab = 'approvals'">审批</button><button type="button"
            class="rounded-full px-3 py-1.5 text-xs font-semibold"
            :class="debugTab === 'raw' ? 'bg-brand-soft text-brand' : 'bg-base-soft text-secondary'"
            @click="debugTab = 'raw'">JSON</button></div>
        <div class="flex-1 overflow-auto px-5 py-4">
          <div v-if="debugTab === 'events'" class="space-y-3">
            <article v-for="event in runVm.debugEvents" :key="event.id || `${event.type}-${event.timestamp}`"
              class="rounded-3xl bg-base-soft px-4 py-4">
              <div class="flex flex-wrap items-center gap-3"><span class="rounded-full px-3 py-1 text-xs font-semibold"
                  :class="badgeClass(event.primaryStatus)">{{ event.label }}</span>
                <p class="text-sm font-semibold text-primary">{{ event.title }}</p><span
                  class="text-[11px] text-muted">{{ event.timestampLabel }}</span><span v-if="event.actorLabel"
                  class="text-[11px] text-muted">{{ event.actorLabel }}</span>
              </div>
              <p v-if="event.message" class="mt-2 text-sm leading-6 text-secondary">{{ event.message }}</p>
              <ul v-if="event.detailLines.length" class="mt-3 space-y-2">
                <li v-for="line in event.detailLines" :key="`${event.id}-${line}`"
                  class="rounded-2xl bg-surface px-3 py-2 text-xs text-secondary">{{ line }}</li>
              </ul>
              <p v-if="event.nextStep" class="mt-3 text-xs text-muted">下一步：{{ event.nextStep }}</p>
            </article>
            <div v-if="!runVm.debugEvents.length" class="rounded-3xl bg-base-soft px-4 py-5 text-sm text-secondary">
              还没有原始事件。</div>
          </div>
          <div v-else-if="debugTab === 'todos'" class="space-y-4">
            <div class="rounded-3xl bg-base-soft px-4 py-4">
              <div class="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <p class="text-sm font-semibold text-primary">当前任务清单</p>
                  <p class="mt-2 text-sm leading-6 text-secondary">{{ runVm.todoObservability.summary }}</p>
                </div>
                <span class="rounded-full bg-surface px-3 py-1 text-xs font-semibold text-secondary">{{
                  runVm.todoObservability.totalCount }} 项</span>
              </div>
              <div class="mt-3 grid gap-2 text-xs text-muted sm:grid-cols-2">
                <p>最近更新：{{ runVm.todoObservability.updatedAtLabel }}</p>
                <p v-if="runVm.todoObservability.updatedBy">更新节点：{{ runVm.todoObservability.updatedBy }}</p>
                <p v-if="runVm.todoObservability.updatedMessage" class="sm:col-span-2">说明：{{ runVm.todoObservability.updatedMessage }}</p>
              </div>
            </div>
            <article v-for="item in runVm.todoObservability.items" :key="item.id"
              class="rounded-3xl border px-4 py-4"
              :class="item.isCurrent ? 'border-brand-soft bg-brand-soft/20' : 'border-soft bg-base-soft'">
              <div class="flex items-start justify-between gap-3">
                <div class="min-w-0">
                  <div class="flex items-center gap-3">
                    <span
                      class="inline-flex h-8 w-8 items-center justify-center rounded-full bg-surface text-sm font-semibold text-primary">{{
                      item.order }}</span>
                    <p class="text-sm font-semibold text-primary">{{ item.label }}</p>
                  </div>
                  <p class="mt-3 text-xs text-muted">{{ item.isCurrent ? '当前正在推进这一项。' : '状态会随着最新事件自动刷新。' }}</p>
                </div>
                <span class="rounded-full px-3 py-1 text-xs font-semibold" :class="badgeClass(item.status)">{{
                  item.statusText }}</span>
              </div>
            </article>
            <div v-if="!runVm.todoObservability.items.length" class="rounded-3xl bg-base-soft px-4 py-5 text-sm text-secondary">
              当前还没有任务清单。</div>
          </div>
          <div v-else-if="debugTab === 'approvals'" class="space-y-4">
            <article v-for="approval in runVm.approvals" :key="approval.approval_id"
              class="rounded-3xl bg-base-soft px-4 py-4">
              <div class="flex flex-wrap items-center gap-2">
                <p class="text-base font-semibold text-primary">{{ approval.title || '待确认事项' }}</p><span
                  class="rounded-full px-3 py-1 text-xs font-semibold"
                  :class="approvalBadgeClass(approval.status, approval.decision)">{{
                    approvalStatusLabel(approval.status, approval.decision) }}</span>
              </div>
              <p class="mt-2 text-sm leading-6 text-secondary">{{ approval.summary || '请确认是否继续执行。' }}</p>
              <div v-if="approval.action?.markdown_preview" class="mt-4 rounded-3xl bg-surface px-4 py-4">
                <p class="text-xs font-semibold uppercase tracking-[0.18em] text-muted">文稿预览</p>
                <pre
                  class="mt-2 whitespace-pre-wrap break-words text-xs leading-6 text-secondary">{{ approval.action.markdown_preview }}</pre>
              </div>
              <div v-if="canEditApproval(approval)" class="mt-4 space-y-2"><label class="space-y-2 text-secondary"><span
                    class="text-xs font-semibold text-muted">如需改写，可在这里直接编辑文稿</span><textarea
                    v-model="approvalEdits[approval.approval_id]" class="input min-h-[140px] resize-y"
                    :placeholder="approval.action?.markdown_preview || '输入调整后的文稿内容'" /></label></div>
              <div v-if="approval.status !== 'resolved'" class="mt-4 flex flex-wrap gap-2"><button type="button"
                  class="btn-primary" :disabled="processingApprovalId === approval.approval_id"
                  @click="handleApproval(approval, 'approve')">{{ processingApprovalId === approval.approval_id ? '处理中…'
                  : '确认继续' }}</button><button v-if="canEditApproval(approval)" type="button" class="btn-secondary"
                  :disabled="processingApprovalId === approval.approval_id || !approvalEdits[approval.approval_id]?.trim()"
                  @click="handleApproval(approval, 'edit')">提交修改</button><button type="button" class="btn-secondary"
                  :disabled="processingApprovalId === approval.approval_id"
                  @click="handleApproval(approval, 'reject')">暂不继续</button></div>
            </article>
            <div v-if="!runVm.approvals.length" class="rounded-3xl bg-base-soft px-4 py-5 text-sm text-secondary">
              当前没有待处理的介入项。</div>
          </div>
          <div v-else class="space-y-4">
            <div class="grid gap-2 text-sm text-secondary sm:grid-cols-2">
              <p>任务 ID：{{ taskState.id || '--' }}</p>
              <p>线程 ID：{{ taskState.threadId || '--' }}</p>
              <p>连接方式：{{ runVm.runSummary.connectionText }}</p>
              <p>Worker PID：{{ taskState.workerPid || '--' }}</p>
              <p>运行面：{{ runVm.runtimeDiagnostics.runtimeModeLabel }}</p>
              <p>Checkpoint：{{ runVm.runtimeDiagnostics.checkpointBackendLabel }}</p>
              <p class="sm:col-span-2">恢复定位：{{ runVm.runtimeDiagnostics.checkpointLocator || '--' }}</p>
              <p>最近 Interrupt：{{ runVm.runtimeDiagnostics.latestInterruptLabel }}</p>
              <p>Tracing：{{ runVm.runtimeDiagnostics.tracingLabel }}</p>
            </div>
            <pre
              class="overflow-auto rounded-3xl bg-base-soft p-4 text-xs leading-6 text-secondary">{{ rawTaskJson }}</pre>
          </div>
        </div>
      </div>
    </Transition>
  </div>
</template>

<script setup>
import { computed, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ArrowPathIcon, ClockIcon, DocumentDuplicateIcon, DocumentTextIcon, ExclamationTriangleIcon, RectangleStackIcon, SparklesIcon, StopIcon, WrenchScrewdriverIcon, XMarkIcon } from '@heroicons/vue/24/outline'
import AppSelect from '../../components/AppSelect.vue'
import { useReportGeneration } from '../../composables/useReportGeneration'
import { buildRunConsoleViewModel, formatTimestamp, todoStatusLabel } from '../../utils/reportRunModels'

const router = useRouter()
const approvalEdits = reactive({})
const processingApprovalId = ref('')
const agentsDrawerOpen = ref(false)
const debugDrawerOpen = ref(false)
const debugTab = ref('events')
const idleCards = [{ kicker: '开始前', title: '先确定分析范围', body: '选择专题、日期和模式后，再开始这一轮分析。' }, { kicker: '运行中', title: '跟进阶段推进', body: '这里会显示阶段进度、关键动态和当前结果。' }, { kicker: '需要更多细节', title: '再看节点和调试信息', body: '需要排查时，再打开执行节点或调试详情。' }]

const { topicsState, topicOptions, reportForm, availableRange, reportState, historyState, taskState, reportHistory, selectedHistoryId, activeTask, loadTopics, loadHistory, createReportTask, loadReportTask, cancelReportTask, retryReportTask, resolveReportApproval, applyHistorySelection } = useReportGeneration()
const runVm = computed(() => buildRunConsoleViewModel(taskState))
const rawTaskJson = computed(() => JSON.stringify(activeTask.value || {}, null, 2))
const hasPendingApprovals = computed(() => runVm.value.approvals.some((item) => String(item?.status || '').trim() !== 'resolved'))
const pendingApprovalCount = computed(() => runVm.value.approvals.filter((item) => String(item?.status || '').trim() !== 'resolved').length)
const primaryActionLabel = computed(() => (taskState.id && ['queued', 'running', 'waiting_approval'].includes(taskState.status) ? '继续查看任务' : '创建任务'))
const canCancelTask = computed(() => Boolean(taskState.id && ['queued', 'running', 'waiting_approval'].includes(taskState.status)))
const canRetryTask = computed(() => Boolean(taskState.id && ['failed', 'cancelled'].includes(taskState.status)))
const canOpenResults = computed(() => Boolean(taskState.id && taskState.threadId && taskState.artifactManifest?.structured_projection?.status === 'ready'))
const canOpenAiResults = computed(() => Boolean(taskState.id && taskState.threadId && taskState.artifactManifest?.full_markdown?.status === 'ready'))
const topicSelectOptions = computed(() => topicOptions.value.map((option) => ({ value: option, label: option })))
const historySelectOptions = computed(() => reportHistory.value.map((record) => ({ value: record.id, label: `${record.start} → ${record.end}` })))
const modeSelectOptions = [{ value: 'fast', label: '快速' }, { value: 'research', label: '深入（本地档案）' }]

const badgeClass = (status) => ({ completed: 'bg-success-soft text-success', failed: 'bg-danger-soft text-danger', running: 'bg-brand-soft text-brand', pending: 'bg-base-soft text-secondary' }[status] || 'bg-base-soft text-secondary')
const dotClass = (status) => ({ completed: 'bg-success-soft', failed: 'bg-danger-soft', running: 'bg-brand-soft', pending: 'bg-base-soft' }[status] || 'bg-base-soft')
const stageLineClass = (status) => ({ completed: 'bg-success-soft', failed: 'bg-danger-soft', running: 'bg-brand-soft', pending: 'bg-base-soft' }[status] || 'bg-base-soft')
const stageCardClass = (status) => ({ completed: 'bg-success-soft', failed: 'bg-danger-soft', running: 'bg-brand-soft', pending: 'bg-base-soft' }[status] || 'bg-base-soft')
const approvalStatusLabel = (status, decision) => (status === 'resolved' && decision === 'approve' ? '已确认' : status === 'resolved' && decision === 'edit' ? '已修改' : status === 'resolved' && decision === 'reject' ? '已拒绝' : '待处理')
const approvalBadgeClass = (status, decision) => (status === 'resolved' && decision === 'approve' ? 'bg-success-soft text-success' : status === 'resolved' && decision === 'edit' ? 'bg-brand-soft text-brand' : status === 'resolved' && decision === 'reject' ? 'bg-danger-soft text-danger' : 'bg-warning-soft text-warning')
const canEditApproval = (approval) => {
  const toolName = String(approval?.tool_name || '').trim()
  return toolName === 'graph_interrupt'
}
const openDebugDrawer = (target = 'events') => { debugTab.value = target; debugDrawerOpen.value = true }

async function handleApproval(approval, decision) { if (!taskState.id || !approval?.approval_id) return; const payload = { decision }; const edited = String(approvalEdits[approval.approval_id] || '').trim(); if (decision === 'edit' && canEditApproval(approval) && edited) payload.edited_action = { markdown: edited }; processingApprovalId.value = approval.approval_id; try { await resolveReportApproval(taskState.id, approval.approval_id, payload) } finally { processingApprovalId.value = '' } }
async function handleCreateTask() { await createReportTask() }
async function handleRefreshHistory() { const topic = String(reportForm.topic || '').trim(); if (topic) await loadHistory(topic) }
async function handleRefreshTask() { if (taskState.id) await loadReportTask(taskState.id) }
async function handleCancelTask() { await cancelReportTask() }
async function handleRetryTask() { await retryReportTask() }
async function handleSelectHistory(historyId) { if (historyId) await applyHistorySelection(historyId, { shouldLoad: false }) }
function goToResultsPage() { if (canOpenResults.value) router.push({ name: 'report-generation-view' }) }
function goToAiResultsPage() { if (canOpenAiResults.value) router.push({ name: 'report-generation-ai' }) }
</script>

<style scoped>
.fade-enter-active,
.fade-leave-active,
.slide-up-enter-active,
.slide-up-leave-active {
  transition: all 0.2s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

.slide-up-enter-from,
.slide-up-leave-to {
  opacity: 0;
  transform: translateY(16px);
}
</style>
