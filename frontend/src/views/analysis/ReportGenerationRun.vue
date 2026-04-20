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

      <div class="grid gap-4 xl:grid-cols-[1.15fr,1fr,1fr,1fr,0.8fr,auto]">
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
          <p class="text-xs text-muted">"深入"会加强本地归档、基础分析和 BERTopic 结果的交叉研读。</p>
        </label>
        <label class="flex flex-col justify-center gap-2 text-secondary">
          <span class="text-xs font-semibold text-muted">跳过校验</span>
          <div class="flex items-center gap-2">
            <input type="checkbox" v-model="reportForm.skipValidation" class="h-4 w-4 cursor-pointer accent-brand" />
            <span class="text-xs text-muted">静默忽略</span>
          </div>
          <p class="text-xs text-muted">跳过效用门禁和结构校验。</p>
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
            <button v-if="canResumeBeforeFailure" type="button" class="btn-secondary inline-flex items-center gap-2"
              @click="handleResumeBeforeFailure">
              <ArrowPathIcon class="h-4 w-4" />从失败前继续
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
        <div class="mt-5 -mb-5">
          <TabSwitch :tabs="mainTabs" :active="activeMainTab" @change="activeMainTab = $event" />
        </div>
      </header>

      <div v-if="activeMainTab === 'home'" class="grid gap-0 xl:grid-cols-[minmax(0,1.35fr),minmax(300px,0.85fr)]">
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
                <p class="text-xs font-semibold uppercase tracking-[0.18em] text-muted">处理模块</p>
                <p class="mt-2 text-sm text-secondary">{{ runVm.graphObservability.currentNodeLabel }}</p>
              </article>
              <article class="rounded-3xl bg-base-soft px-4 py-3">
                <p class="text-xs font-semibold uppercase tracking-[0.18em] text-muted">负责人</p>
                <p class="mt-2 text-sm text-secondary">{{ runVm.graphObservability.currentActorLabel }}</p>
              </article>
              <article class="rounded-3xl bg-base-soft px-4 py-3">
                <p class="text-xs font-semibold uppercase tracking-[0.18em] text-muted">下一步</p>
                <p class="mt-2 text-sm text-secondary">{{ runVm.graphObservability.nextStep }}</p>
              </article>
              <article class="rounded-3xl bg-base-soft px-4 py-3">
                <p class="text-xs font-semibold uppercase tracking-[0.18em] text-muted">任务标识</p>
                <p class="mt-2 text-sm text-secondary">{{ runVm.graphObservability.threadLabel }}</p>
                <p class="mt-2 text-xs text-muted">{{ runVm.graphObservability.connectionLabel }}</p>
              </article>
            </div>
          </section>
          <section class="rounded-[1.75rem] bg-surface p-5">
            <p class="text-xs font-semibold uppercase tracking-[0.24em] text-muted">任务分派</p>
            <p class="mt-3 text-sm leading-6 text-secondary">{{ runVm.graphObservability.routerSummary }}</p>
            <div class="mt-4 space-y-3">
              <article class="rounded-3xl bg-base-soft px-4 py-4">
                <p class="text-xs font-semibold uppercase tracking-[0.18em] text-muted">已分派任务</p>
                <p class="mt-2 text-sm text-secondary">{{ runVm.graphObservability.dispatchTargets.length ?
                  runVm.graphObservability.dispatchTargets.join('、') : '当前还没有分派记录。' }}</p>
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
            <p class="text-xs font-semibold uppercase tracking-[0.24em] text-muted">进展判断</p>
            <div class="mt-4 space-y-3">
              <article class="rounded-3xl bg-base-soft px-4 py-4">
                <div class="flex items-start justify-between gap-3">
                  <div>
                    <p class="text-xs font-semibold uppercase tracking-[0.18em] text-muted">当前状态</p>
                    <p class="mt-2 text-base font-semibold text-primary">{{
                      runVm.decisionObservability.utilityDecisionLabel }}</p>
                  </div>
                  <span class="rounded-full px-3 py-1 text-xs font-semibold"
                    :class="badgeClass(runVm.decisionObservability.hasPendingApproval ? 'running' : (runVm.decisionObservability.utilityDecision === 'pass' ? 'completed' : 'pending'))">{{
                      runVm.decisionObservability.utilityDecision }}</span>
                </div>
                <p class="mt-3 text-sm leading-6 text-secondary">{{ runVm.decisionObservability.finalReason ||
                  '当前还没有状态说明。' }}</p>
              </article>
              <article class="rounded-3xl bg-base-soft px-4 py-4">
                <p class="text-xs font-semibold uppercase tracking-[0.18em] text-muted">下一步</p>
                <p class="mt-2 text-sm text-secondary">{{ runVm.decisionObservability.nextAction }}</p>
              </article>
              <article class="rounded-3xl bg-base-soft px-4 py-4">
                <p class="text-xs font-semibold uppercase tracking-[0.18em] text-muted">待补充内容</p>
                <p class="mt-2 text-sm text-secondary">{{ runVm.decisionObservability.missingDimensions.length ?
                  runVm.decisionObservability.missingDimensions.slice(0, 3).join('、') : '暂无待补充内容。' }}</p>
              </article>
              <article class="rounded-3xl bg-base-soft px-4 py-4">
                <p class="text-xs font-semibold uppercase tracking-[0.18em] text-muted">调整记录</p>
                <p class="mt-2 text-sm text-secondary">{{ runVm.decisionObservability.fallbackSummary }}</p>
                <p class="mt-2 text-xs text-muted">确认状态：{{ runVm.decisionObservability.approvalDecision }}</p>
              </article>
            </div>
          </section>
          <section class="rounded-[1.75rem] bg-surface p-5">
            <p class="text-xs font-semibold uppercase tracking-[0.24em] text-muted">生成结果</p>
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
                  <p>数据来源：{{ artifact.sourceLabel }}</p>
                  <p v-if="artifact.reviewState">确认状态：{{ artifact.reviewState }}</p>
                  <p v-if="artifact.fallbackState">调整情况：{{ artifact.fallbackState }}</p>
                </div>
              </article>
            </div>
          </section>
          <section class="rounded-[1.75rem] bg-surface p-5">
            <p class="text-xs font-semibold uppercase tracking-[0.24em] text-muted">人工确认</p>
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
                <p v-if="runVm.approvalObservability.affectedLabel">涉及内容：{{ runVm.approvalObservability.affectedLabel
                  }}</p>
                <p v-if="runVm.approvalObservability.actionSummary">可选操作：{{ runVm.approvalObservability.actionSummary }}
                </p>
                <p v-if="runVm.approvalObservability.interruptLabel">暂停点：{{ runVm.approvalObservability.interruptLabel }}</p>
                <p v-if="runVm.approvalObservability.checkpointLabel">记录点：{{ runVm.approvalObservability.checkpointLabel }}</p>
                <p v-if="runVm.approvalObservability.resumeLabel">恢复位置：{{ runVm.approvalObservability.resumeLabel }}</p>
              </div>
            </div>
          </section>
          <section class="rounded-[1.75rem] bg-surface p-5">
            <p class="text-xs font-semibold uppercase tracking-[0.24em] text-muted">运行详情</p>
            <div class="mt-4 grid gap-2 sm:grid-cols-2">
              <article class="rounded-3xl bg-base-soft px-4 py-3">
                <p class="text-xs font-semibold uppercase tracking-[0.18em] text-muted">运行方式</p>
                <p class="mt-2 text-sm text-secondary">{{ runVm.runtimeDiagnostics.runtimeModeLabel }}</p>
              </article>
              <article class="rounded-3xl bg-base-soft px-4 py-3">
                <p class="text-xs font-semibold uppercase tracking-[0.18em] text-muted">状态记录</p>
                <p class="mt-2 text-sm text-secondary">{{ runVm.runtimeDiagnostics.checkpointBackendLabel }}</p>
              </article>
              <article class="rounded-3xl bg-base-soft px-4 py-3 sm:col-span-2">
                <p class="text-xs font-semibold uppercase tracking-[0.18em] text-muted">恢复位置</p>
                <p class="mt-2 text-sm text-secondary">{{ runVm.runtimeDiagnostics.checkpointLocatorLabel }}</p>
              </article>
              <article class="rounded-3xl bg-base-soft px-4 py-3">
                <p class="text-xs font-semibold uppercase tracking-[0.18em] text-muted">最近暂停</p>
                <p class="mt-2 text-sm text-secondary">{{ runVm.runtimeDiagnostics.latestInterruptLabel }}</p>
              </article>
              <article class="rounded-3xl bg-base-soft px-4 py-3">
                <p class="text-xs font-semibold uppercase tracking-[0.18em] text-muted">追踪状态</p>
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
            <div v-if="canRetryTask || canResumeBeforeFailure" class="mt-4 flex gap-2">
              <button v-if="canResumeBeforeFailure" type="button" class="btn-primary text-xs" @click="handleResumeBeforeFailure">
                从失败前继续
              </button>
              <button v-else type="button" class="btn-primary text-xs" @click="handleRequeue">
                从 checkpoint 续跑
              </button>
              <button type="button" class="btn-secondary text-xs" @click="handleSkipValidation">跳过校验，强制继续</button>
            </div>
          </section>
        </aside>
      </div>

      <div v-else-if="activeMainTab === 'agents'" class="space-y-3 p-5">
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
        <div v-if="!runVm.agentDrawer.length" class="rounded-3xl bg-base-soft px-4 py-5 text-sm text-secondary">当前还没有执行节点。</div>
      </div>

      <div v-else-if="activeMainTab === 'debug'" class="flex flex-col">
        <div class="border-b border-soft px-5 pt-4 pb-0">
          <TabSwitch :tabs="debugTabs" :active="debugTab" @change="debugTab = $event" />
        </div>
        <div class="space-y-3 p-5">
          <div v-if="debugTab === 'events'" class="space-y-3">
            <article v-for="event in runVm.debugEvents" :key="event.id || `${event.type}-${event.timestamp}`"
              class="rounded-3xl bg-base-soft px-4 py-4">
              <div class="flex flex-wrap items-center gap-3"><span class="rounded-full px-3 py-1 text-xs font-semibold"
                  :class="badgeClass(event.primaryStatus)">{{ event.label }}</span>
                <p class="text-sm font-semibold text-primary">{{ event.title }}</p><span
                  class="text-[11px] text-muted">{{ event.timestampLabel }}</span><span v-if="event.actorLabel"
                  class="text-[11px] text-muted">{{ event.actorLabel }}</span>
              </div>
              <p v-if="event.message" class="mt-2 break-all text-sm leading-6 text-secondary">{{ event.message }}</p>
              <ul v-if="event.detailLines.length" class="mt-3 space-y-2">
                <li v-for="line in event.detailLines" :key="`${event.id}-${line}`"
                  class="break-all rounded-2xl bg-surface px-3 py-2 text-xs text-secondary">{{ line }}</li>
              </ul>
              <p v-if="event.nextStep" class="mt-3 break-all text-xs text-muted">下一步：{{ event.nextStep }}</p>
            </article>
            <div v-if="!runVm.debugEvents.length" class="rounded-3xl bg-base-soft px-4 py-5 text-sm text-secondary">
              还没有原始事件。</div>
          </div>
          <div v-else-if="debugTab === 'todos'" class="space-y-4">
            <div class="rounded-3xl bg-base-soft px-4 py-4">
              <div class="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <p class="text-sm font-semibold text-primary">总控任务清单</p>
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
              当前还没有总控任务清单。</div>
            <div class="rounded-3xl bg-base-soft px-4 py-4">
              <div class="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <p class="text-sm font-semibold text-primary">当前子代理计划</p>
                  <p class="mt-2 text-sm leading-6 text-secondary">{{ runVm.subagentTodoObservability.summary }}</p>
                </div>
                <span class="rounded-full bg-surface px-3 py-1 text-xs font-semibold text-secondary">{{
                  runVm.subagentTodoObservability.totalCount }} 项</span>
              </div>
              <div class="mt-3 grid gap-2 text-xs text-muted sm:grid-cols-2">
                <p>最近更新：{{ runVm.subagentTodoObservability.updatedAtLabel }}</p>
                <p v-if="runVm.subagentTodoObservability.updatedBy">更新节点：{{ runVm.subagentTodoObservability.updatedBy }}</p>
                <p v-if="runVm.subagentTodoObservability.updatedMessage" class="sm:col-span-2">说明：{{ runVm.subagentTodoObservability.updatedMessage }}</p>
              </div>
            </div>
            <article v-for="item in runVm.subagentTodoObservability.items" :key="`subagent-${item.id}`"
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
                  <p class="mt-3 text-xs text-muted">{{ item.isCurrent ? '当前子代理正在推进这一项。' : '子代理计划会随着最新节点事件自动刷新。' }}</p>
                </div>
                <span class="rounded-full px-3 py-1 text-xs font-semibold" :class="badgeClass(item.status)">{{
                  item.statusText }}</span>
              </div>
            </article>
            <div v-if="!runVm.subagentTodoObservability.items.length" class="rounded-3xl bg-base-soft px-4 py-5 text-sm text-secondary">
              当前没有子代理内部计划。</div>
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
              <div v-if="canEditApproval(approval)" class="mt-4 space-y-3">
                <label class="space-y-2 text-secondary">
                  <span class="text-xs font-semibold text-muted">重写批注</span>
                  <textarea v-model="approvalEdits[approval.approval_id]" class="input min-h-[120px] resize-y"
                    :placeholder="approval.action?.review_placeholder || '说明这一轮需要保留、移除或降调的内容'" />
                </label>
                <div class="grid gap-3 md:grid-cols-2">
                  <label class="space-y-2 text-secondary">
                    <span class="text-xs font-semibold text-muted">重写重点</span>
                    <input v-model="approvalRewriteFocus[approval.approval_id]" type="text" class="input"
                      placeholder="逗号分隔，例如：delete_untraced, cautious tone" />
                  </label>
                  <label class="space-y-2 text-secondary">
                    <span class="text-xs font-semibold text-muted">语气目标</span>
                    <input v-model="approvalToneTarget[approval.approval_id]" type="text" class="input"
                      placeholder="例如：cautious" />
                  </label>
                  <label class="space-y-2 text-secondary">
                    <span class="text-xs font-semibold text-muted">必须保留</span>
                    <input v-model="approvalMustKeep[approval.approval_id]" type="text" class="input"
                      placeholder="逗号分隔，填写关键句或关键点" />
                  </label>
                  <label class="space-y-2 text-secondary">
                    <span class="text-xs font-semibold text-muted">必须移除</span>
                    <input v-model="approvalMustRemove[approval.approval_id]" type="text" class="input"
                      placeholder="逗号分隔，填写需要删除的句子或表述" />
                  </label>
                </div>
                <div v-if="approval.action?.semantic_interrupt" class="rounded-3xl bg-surface px-4 py-4 text-xs text-secondary">
                  <p class="font-semibold text-primary">当前 rewrite 信息</p>
                  <p class="mt-2">当前回合：{{ approval.action.semantic_interrupt?.rewrite_round || 0 }}</p>
                  <p class="mt-2">允许操作：{{ (approval.action.semantic_interrupt?.allowed_rewrite_ops || []).join('、') || '未提供' }}</p>
                  <p class="mt-2">问题单元：{{ (approval.action.semantic_interrupt?.offending_unit_ids || []).join('、') || '未提供' }}</p>
                </div>
              </div>
              <div v-if="approval.status !== 'resolved'" class="mt-4 flex flex-wrap gap-2"><button type="button"
                  class="btn-primary" :disabled="processingApprovalId === approval.approval_id"
                  @click="handleApproval(approval, 'approve')">{{ processingApprovalId === approval.approval_id ? '处理中…'
                  : '确认继续' }}</button><button v-if="canEditApproval(approval)" type="button" class="btn-secondary"
                  :disabled="processingApprovalId === approval.approval_id || !approvalEdits[approval.approval_id]?.trim()"
                  @click="handleApproval(approval, 'rewrite')">要求重写</button><button type="button" class="btn-secondary"
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
    </section>
  </div>
</template>

<script setup>
import { computed, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ArrowPathIcon, ClockIcon, DocumentDuplicateIcon, DocumentTextIcon, ExclamationTriangleIcon, SparklesIcon, StopIcon } from '@heroicons/vue/24/outline'
import AppSelect from '../../components/AppSelect.vue'
import TabSwitch from '../../components/TabSwitch.vue'
import { useReportGeneration } from '../../composables/useReportGeneration'
import { buildRunConsoleViewModel, formatTimestamp, todoStatusLabel } from '../../utils/reportRunModels'

const router = useRouter()
const approvalEdits = reactive({})
const approvalRewriteFocus = reactive({})
const approvalMustKeep = reactive({})
const approvalMustRemove = reactive({})
const approvalToneTarget = reactive({})
const processingApprovalId = ref('')
const activeMainTab = ref('home')
const debugTab = ref('events')
const mainTabs = [
  { value: 'home', label: '主页' },
  { value: 'agents', label: '执行节点' },
  { value: 'debug', label: '调试详情' },
]
const debugTabs = [
  { value: 'events', label: '事件' },
  { value: 'todos', label: '清单' },
  { value: 'approvals', label: '审批' },
  { value: 'raw', label: 'JSON' },
]
const idleCards = [{ kicker: '开始前', title: '先确定分析范围', body: '选择专题、日期和模式后，再开始这一轮分析。' }, { kicker: '运行中', title: '跟进阶段推进', body: '这里会显示阶段进度、关键动态和当前结果。' }, { kicker: '需要更多细节', title: '再看节点和调试信息', body: '需要排查时，再打开执行节点或调试详情。' }]

const { topicsState, topicOptions, reportForm, availableRange, reportState, historyState, taskState, reportHistory, selectedHistoryId, activeTask, loadTopics, loadHistory, createReportTask, loadReportTask, cancelReportTask, retryReportTask, requeueReportTask, resumeBeforeFailureReportTask, resolveReportApproval, applyHistorySelection } = useReportGeneration()
const runVm = computed(() => buildRunConsoleViewModel(taskState))
const rawTaskJson = computed(() => JSON.stringify(activeTask.value || {}, null, 2))
const hasPendingApprovals = computed(() => runVm.value.approvals.some((item) => String(item?.status || '').trim() !== 'resolved'))
const pendingApprovalCount = computed(() => runVm.value.approvals.filter((item) => String(item?.status || '').trim() !== 'resolved').length)
const primaryActionLabel = computed(() => (taskState.id && ['queued', 'running', 'waiting_approval'].includes(taskState.status) ? '继续查看任务' : '创建任务'))
const canCancelTask = computed(() => Boolean(taskState.id && ['queued', 'running', 'waiting_approval'].includes(taskState.status)))
const canRetryTask = computed(() => Boolean(taskState.id && ['failed', 'cancelled'].includes(taskState.status)))
const resumeBeforeFailureCapability = computed(() => (
  taskState.resumeCapabilities?.resume_before_failure && typeof taskState.resumeCapabilities.resume_before_failure === 'object'
    ? taskState.resumeCapabilities.resume_before_failure
    : {}
))
const canResumeBeforeFailure = computed(() => Boolean(taskState.id && ['failed', 'cancelled'].includes(taskState.status) && resumeBeforeFailureCapability.value?.enabled))
const canOpenResults = computed(() => Boolean(taskState.artifactManifest?.structured_projection?.status === 'ready'))
const canOpenAiResults = computed(() => Boolean(taskState.artifactManifest?.full_markdown?.status === 'ready'))
const topicSelectOptions = computed(() => topicOptions.value.map((option) => ({ value: option, label: option })))
const historySelectOptions = computed(() => reportHistory.value.map((record) => ({ value: record.id, label: `${record.start} → ${record.end}` })))
const modeSelectOptions = [{ value: 'fast', label: '快速' }, { value: 'research', label: '深入（本地档案）' }]

const badgeClass = (status) => ({ completed: 'bg-success-soft text-success', failed: 'bg-danger-soft text-danger', running: 'bg-brand-soft text-brand', pending: 'bg-base-soft text-secondary' }[status] || 'bg-base-soft text-secondary')
const dotClass = (status) => ({ completed: 'bg-success-soft', failed: 'bg-danger-soft', running: 'bg-brand-soft', pending: 'bg-base-soft' }[status] || 'bg-base-soft')
const stageLineClass = (status) => ({ completed: 'bg-success-soft', failed: 'bg-danger-soft', running: 'bg-brand-soft', pending: 'bg-base-soft' }[status] || 'bg-base-soft')
const stageCardClass = (status) => ({ completed: 'bg-success-soft', failed: 'bg-danger-soft', running: 'bg-brand-soft', pending: 'bg-base-soft' }[status] || 'bg-base-soft')
const approvalStatusLabel = (status, decision) => (status === 'resolved' && decision === 'approve' ? '已确认' : status === 'resolved' && decision === 'rewrite' ? '已要求重写' : status === 'resolved' && decision === 'reject' ? '已拒绝' : '待处理')
const approvalBadgeClass = (status, decision) => (status === 'resolved' && decision === 'approve' ? 'bg-success-soft text-success' : status === 'resolved' && decision === 'rewrite' ? 'bg-brand-soft text-brand' : status === 'resolved' && decision === 'reject' ? 'bg-danger-soft text-danger' : 'bg-warning-soft text-warning')
const canEditApproval = (approval) => {
  const toolName = String(approval?.tool_name || '').trim()
  return toolName === 'graph_interrupt'
}
const parseApprovalList = (value) => String(value || '').split(/[\n,，]/).map((item) => item.trim()).filter(Boolean)
const openDebugDrawer = (target = 'events') => { debugTab.value = target; activeMainTab.value = 'debug' }

async function handleApproval(approval, decision) {
  if (!taskState.id || !approval?.approval_id) return
  const approvalId = approval.approval_id
  const payload = { decision }
  if (decision === 'rewrite' && canEditApproval(approval)) {
    payload.review_payload = {
      comment: String(approvalEdits[approvalId] || '').trim(),
      rewrite_focus: parseApprovalList(approvalRewriteFocus[approvalId]),
      must_keep: parseApprovalList(approvalMustKeep[approvalId]),
      must_remove: parseApprovalList(approvalMustRemove[approvalId]),
      tone_target: String(approvalToneTarget[approvalId] || '').trim()
    }
  }
  processingApprovalId.value = approvalId
  try {
    await resolveReportApproval(taskState.id, approvalId, payload)
  } finally {
    processingApprovalId.value = ''
  }
}
async function handleCreateTask() { await createReportTask() }
async function handleRefreshHistory() { const topic = String(reportForm.topic || '').trim(); if (topic) await loadHistory(topic) }
async function handleRefreshTask() { if (taskState.id) await loadReportTask(taskState.id) }
async function handleCancelTask() { await cancelReportTask() }
async function handleRetryTask() { await retryReportTask() }
async function handleRequeue() {
  if (resumeBeforeFailureCapability.value?.enabled) {
    await resumeBeforeFailureReportTask()
    return
  }
  await requeueReportTask()
}
async function handleResumeBeforeFailure() { await resumeBeforeFailureReportTask() }
async function handleSkipValidation() {
  if (resumeBeforeFailureCapability.value?.enabled) {
    await resumeBeforeFailureReportTask()
  } else {
    await retryReportTask()
  }
}
async function handleSelectHistory(historyId) { if (historyId) await applyHistorySelection(historyId, { shouldLoad: false }) }
function goToResultsPage() { if (canOpenResults.value) router.push({ name: 'report-generation-view' }) }
function goToAiResultsPage() { if (canOpenAiResults.value) router.push({ name: 'report-generation-ai' }) }
</script>

