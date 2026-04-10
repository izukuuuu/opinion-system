<template>
  <div class="bertopic-run space-y-6 pb-12">
    <AnalysisPageHeader
      eyebrow="BERTopic 主题分析"
      title="运行分析"
      description="选择专题、时间范围与智能体策略，然后提交主题分析任务。"
    />

    <form class="space-y-6" @submit.prevent="handleRun">
      <AnalysisSectionCard
        title="基础配置"
        description="先选择专题与时间范围。系统会自动检查当前专题的数据覆盖区间，并在提交前完成基础校验。"
      >
        <div class="space-y-6">
          <div class="grid gap-6 xl:grid-cols-[minmax(0,1.1fr)_minmax(320px,0.9fr)]">
            <div class="space-y-2">
              <div class="flex items-center justify-between gap-3">
                <label class="text-xs font-semibold uppercase tracking-[0.2em] text-muted">分析专题</label>
                <button
                  type="button"
                  class="analysis-toolbar__action analysis-toolbar__action--ghost px-3 py-1.5 text-xs focus-ring-accent"
                  :disabled="topicsState.loading"
                  @click="loadTopics(true)"
                >
                  <ArrowPathIcon class="h-4 w-4" :class="{ 'animate-spin': topicsState.loading }" />
                  <span>{{ topicsState.loading ? '同步中…' : '刷新专题' }}</span>
                </button>
              </div>
              <AppSelect
                :options="topicSelectOptions"
                :value="form.topic"
                :disabled="topicsState.loading || topicOptions.length === 0"
                @change="handleTopicChange"
              />
              <p class="text-xs text-secondary">选择要执行 BERTopic 的专题，运行前会自动加载对应配置。</p>
            </div>

            <div class="space-y-2">
              <label class="text-xs font-semibold uppercase tracking-[0.2em] text-muted">分析时间范围</label>
              <div class="grid gap-3 sm:grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] sm:items-center">
                <label class="space-y-2">
                  <span class="text-xs font-medium text-muted">开始日期</span>
                  <input
                    v-model.trim="form.startDate"
                    type="date"
                    class="input h-12 w-full"
                    required
                    :disabled="availableRange.loading"
                  />
                </label>
                <span class="hidden text-muted sm:inline">→</span>
                <label class="space-y-2">
                  <span class="text-xs font-medium text-muted">结束日期</span>
                  <input
                    v-model.trim="form.endDate"
                    type="date"
                    class="input h-12 w-full"
                    :disabled="availableRange.loading"
                    :min="form.startDate"
                  />
                </label>
              </div>
              <p class="text-xs text-secondary">未填写结束日期时，默认分析从开始日期起的全部可用数据。</p>
            </div>
          </div>

          <div
            v-if="availableRange.start || availableRange.error"
            class="state-banner"
            :class="availableRange.error ? 'state-banner-danger' : 'state-banner-info'"
          >
            <div class="flex items-start gap-3">
              <InformationCircleIcon v-if="!availableRange.error" class="h-5 w-5 shrink-0 state-banner__icon-info" />
              <ExclamationTriangleIcon v-else class="h-5 w-5 shrink-0 state-banner__icon-danger" />
              <div class="space-y-1">
                <p class="font-semibold text-primary">数据可用性检查</p>
                <p class="text-xs opacity-90">
                  {{ availableRange.error || `当前专题数据覆盖范围：${availableRange.start} ~ ${availableRange.end}` }}
                </p>
              </div>
            </div>
          </div>

          <div class="run-footer">
            <div class="space-y-2">
              <button
                type="button"
                class="analysis-toolbar__action analysis-toolbar__action--pill bertopic-toggle focus-ring-accent"
                @click="showAdvancedSettings = !showAdvancedSettings"
              >
                <CpuChipIcon class="h-4 w-4" />
                <span>{{ showAdvancedSettings ? '收起智能体配置' : '展开智能体配置' }}</span>
                <ChevronDownIcon class="h-4 w-4 transition-transform duration-200" :class="{ 'rotate-180': showAdvancedSettings }" />
              </button>
              <p class="text-xs text-secondary">默认配置可直接运行；展开后可继续细调聚类、过滤与命名规则。</p>
            </div>

            <div class="flex flex-wrap items-center gap-3">
              <button
                type="button"
                class="btn btn-ghost text-muted hover:text-primary"
                @click="resetAll"
                :disabled="runState.running"
              >
                重置
              </button>
              <button type="submit" class="btn btn-primary min-w-[148px]" :disabled="!canSubmit">
                <span v-if="runState.running" class="flex items-center gap-2">
                  <ArrowPathIcon class="h-4 w-4 animate-spin" />
                  <span>分析中…</span>
                </span>
                <span v-else>开始分析</span>
              </button>
            </div>
          </div>
          </div>
        </AnalysisSectionCard>

      <AnalysisSectionCard
        v-if="showAdvancedSettings"
        title="智能体工作流配置"
        description="按阶段调整聚类策略、过滤规则与命名提示。没有特殊需求时，保留默认值即可。"
        tone="soft"
      >
        <div class="space-y-4">
          <div class="workflow-summary">
            <div class="workflow-summary__icon">
              <SparklesIcon class="h-5 w-5" />
            </div>
            <div class="min-w-0 space-y-1">
              <div class="workflow-summary__title-row">
                <span class="workflow-summary__title">多智能体工作流</span>
                <span class="analysis-chip analysis-chip--hero">5 个阶段</span>
                <span class="analysis-chip analysis-chip--hero">顺序执行</span>
              </div>
              <p class="workflow-summary__description">
                从聚类范围判断、主题收敛到关键词润色，按固定阶段逐步收紧结果，避免一次性堆叠过多人工参数。
              </p>
            </div>
            <div class="analysis-toolbar workflow-summary__actions">
              <button
                type="button"
                class="analysis-toolbar__action analysis-toolbar__action--ghost px-3 py-1.5 text-xs focus-ring-accent"
                :disabled="bertopicPromptState.loading || !form.topic.trim()"
                @click="loadBertopicPrompt(form.topic)"
              >
                {{ bertopicPromptState.loading ? '加载中…' : '重载配置' }}
              </button>
              <button
                type="button"
                class="analysis-toolbar__action analysis-toolbar__action--pill px-3.5 py-1.5 text-xs focus-ring-accent"
                :disabled="!canSavePrompt"
                @click="handleSavePrompt"
              >
                {{ bertopicPromptState.saving ? '保存中…' : '保存配置' }}
              </button>
            </div>
          </div>

          <div
            v-if="bertopicPromptState.error || bertopicPromptState.message"
            class="state-banner text-xs"
            :class="bertopicPromptState.error ? 'state-banner-danger' : 'state-banner-success'"
          >
            {{ bertopicPromptState.error || bertopicPromptState.message }}
          </div>

          <div class="pipeline-flow">

          <!-- ── Agent 1: Scope Analyst ── -->
          <div class="agent-card agent-card-scope">
            <button type="button" class="agent-card-header" @click="agentExpanded[1] = !agentExpanded[1]">
              <div class="agent-step agent-step-scope">1</div>
              <div class="flex-1 min-w-0 text-left">
                <div class="agent-name-row">
                  <span class="agent-en">Scope Analyst</span>
                  <span class="agent-zh">范围分析师</span>
                </div>
                <p class="agent-desc">基于原始主题的词袋与样本分布，动态推荐合理的聚类数量上限，避免"一刀切"。</p>
              </div>
              <ChevronDownIcon class="agent-chevron" :class="{ 'rotate-180': agentExpanded[1] }" />
            </button>
            <div v-show="agentExpanded[1]" class="agent-config">
              <div class="grid gap-4 md:grid-cols-3">
                <label class="block">
                  <span class="config-label">最大主题数 Max Topics</span>
                  <input v-model.number="bertopicPromptState.maxTopics" type="number" min="3" max="50"
                    class="input w-full mt-1.5" />
                  <span class="config-hint">AI 会自动推断合理的主题数量，此值为一级主题上限（3–50）。</span>
                </label>
                <label class="block">
                  <span class="config-label">重分类输入上限</span>
                  <input v-model.number="bertopicPromptState.reclusterTopicLimit" type="number" min="20" max="200"
                    class="input w-full mt-1.5" />
                  <span class="config-hint">送入 LLM 的 raw topics 上限，过低会导致覆盖不足（20–200）。</span>
                </label>
                <label class="block">
                  <span class="config-label">目标覆盖率</span>
                  <input v-model.number="bertopicPromptState.reclusterTargetCoverageRatio" type="number" min="0.2"
                    max="0.95" step="0.01" class="input w-full mt-1.5" />
                  <span class="config-hint">优先纳入高频主题，尽量覆盖更多文档再做汇总（0.2–0.95）。</span>
                </label>
              </div>
            </div>
          </div>

          <!-- Connector -->
          <div class="pipeline-connector">
            <div class="connector-line"></div>
          </div>

          <!-- ── Core Refinement Loop ── -->
          <div class="loop-wrapper">
            <div class="loop-header">
              <div class="loop-header-left">
                <div class="loop-icon">
                  <ArrowPathIcon class="h-3.5 w-3.5" />
                </div>
                <span class="loop-title">Core Refinement Loop</span>
                <span class="loop-badge">Max 3 Iters</span>
              </div>
              <div class="retry-rail">
                <ArrowUturnUpIcon class="h-3 w-3" />
                <span>RETRY</span>
              </div>
            </div>

            <div class="loop-body">

              <!-- Agent 2: Cluster Strategist -->
              <div class="agent-card agent-card-cluster">
                <button type="button" class="agent-card-header" @click="agentExpanded[2] = !agentExpanded[2]">
                  <div class="agent-step agent-step-cluster">2</div>
                  <div class="flex-1 min-w-0 text-left">
                    <div class="agent-name-row">
                      <span class="agent-en">Cluster Strategist</span>
                      <span class="agent-zh">聚类策略师</span>
                    </div>
                    <p class="agent-desc">整合由主导视角、手工种子词、强制合并构成的业务规则，将碎片化主题进行高维语义聚类。</p>
                  </div>
                  <ChevronDownIcon class="agent-chevron" :class="{ 'rotate-180': agentExpanded[2] }" />
                </button>
                <div v-show="agentExpanded[2]" class="agent-config">

                  <!-- Mode Switch -->
                  <div class="flex items-center justify-between mb-4">
                    <span class="text-xs font-semibold text-secondary">配置模式</span>
                    <TabSwitch
                      :tabs="promptModeTabs"
                      :active="promptMode"
                      size="sm"
                      @change="promptMode = $event"
                    />
                  </div>

                  <!-- Analyst Mode -->
                  <div v-show="promptMode === 'analyst'" class="space-y-5">
                    <!-- Dimension -->
                    <div class="space-y-3">
                      <div class="flex items-center justify-between gap-2">
                        <label class="text-xs font-bold text-primary flex items-center gap-2">
                          <ViewColumnsIcon class="h-4 w-4 text-brand" />
                          聚类主导视角
                        </label>
                        <div class="relative group">
                          <button type="button" class="dimension-info-trigger" aria-label="查看参数说明">
                            <InformationCircleIcon class="h-4 w-4" />
                          </button>
                          <div class="dimension-info-popover">
                            <p class="dimension-info-title">将追加到提示词的说明</p>
                            <div class="dimension-info-code">{{ reclusterDimensionPromptHint }}</div>
                          </div>
                        </div>
                      </div>
                      <p class="text-[11px] text-secondary">让 AI 根据哪种维度对文档进行最底层的划分。</p>
                      <div class="flex flex-wrap items-center gap-2 mt-2">
                        <button type="button" v-for="dim in reclusterDimensionOptions" :key="dim.label"
                          class="pill-btn"
                          :class="bertopicPromptState.reclusterDimension === dim.value ? 'pill-btn--active' : 'pill-btn--idle'"
                          @click="bertopicPromptState.reclusterDimension = dim.value">
                          {{ dim.label }}
                        </button>
                      </div>
                      <div class="dimension-explain-grid">
                        <div v-for="dim in reclusterDimensionOptions" :key="`explain-${dim.label}`"
                          class="dimension-explain-item"
                          :class="bertopicPromptState.reclusterDimension === dim.value ? 'dimension-explain-item--active' : ''">
                          <p class="dimension-explain-title">{{ dim.label }}</p>
                          <p class="dimension-explain-text">{{ dim.description }}</p>
                        </div>
                      </div>
                    </div>

                    <div class="grid gap-4 md:grid-cols-2">
                      <!-- Must Separate -->
                      <div class="space-y-2">
                        <label class="text-xs font-bold text-primary flex items-center gap-2">
                          <ArrowsPointingOutIcon class="h-4 w-4 text-brand" />
                          自定义识别主题
                        </label>
                        <p class="text-[11px] text-secondary">输入关键主题种子，语义相近内容优先归入同一类。</p>
                        <div class="rule-input-shell">
                          <div class="flex flex-wrap gap-1.5 mb-2" v-if="bertopicPromptState.mustSeparateRules.length > 0">
                            <span v-for="(rule, idx) in bertopicPromptState.mustSeparateRules" :key="idx"
                              class="chip chip--accent">
                              {{ rule }}
                              <button type="button" @click="bertopicPromptState.mustSeparateRules.splice(idx, 1)"
                                class="chip__remove"><XMarkIcon class="h-3 w-3" /></button>
                            </span>
                          </div>
                          <input type="text" v-model="draftSeparateRule" @keyup.enter="addRule('separate')"
                            class="w-full text-xs border-none bg-transparent focus:ring-0 p-1 placeholder:text-muted"
                            placeholder="输入关键主题，按回车添加..." />
                        </div>
                      </div>

                      <!-- Must Merge -->
                      <div class="space-y-2">
                        <label class="text-xs font-bold text-primary flex items-center gap-2">
                          <ArrowsPointingInIcon class="h-4 w-4 text-success" />
                          重点合并专题
                        </label>
                        <p class="text-[11px] text-secondary">高度相关的冗余子主题，提示 AI 尽可能合并。</p>
                        <div class="rule-input-shell">
                          <div class="flex flex-wrap gap-1.5 mb-2" v-if="bertopicPromptState.mustMergeRules.length > 0">
                            <span v-for="(rule, idx) in bertopicPromptState.mustMergeRules" :key="idx"
                              class="chip chip--success">
                              {{ rule }}
                              <button type="button" @click="bertopicPromptState.mustMergeRules.splice(idx, 1)"
                                class="chip__remove"><XMarkIcon class="h-3 w-3" /></button>
                            </span>
                          </div>
                          <input type="text" v-model="draftMergeRule" @keyup.enter="addRule('merge')"
                            class="w-full text-xs border-none bg-transparent focus:ring-0 p-1 placeholder:text-muted"
                            placeholder="输入内容特征，按回车添加..." />
                        </div>
                      </div>
                    </div>
                  </div>

                  <!-- Expert Mode: Recluster Prompt -->
                  <div v-show="promptMode === 'expert'" class="space-y-4">
                    <div class="state-note state-note-accent text-xs">
                      <InformationCircleIcon class="h-4 w-4 inline mr-1 -mt-0.5" />
                      以下是再聚类底层提示词模板，业务调整模式中配置的规则会动态注入到 User Prompt 中。
                    </div>
                    <label class="block">
                      <span class="config-label">System Prompt (可选)</span>
                      <textarea
                        v-model="bertopicPromptState.reclusterSystemPrompt"
                        rows="2"
                        class="input run-textarea w-full mt-1.5 resize-y font-mono text-xs leading-relaxed"
                      ></textarea>
                    </label>
                    <label class="block">
                      <span class="config-label">User Prompt 主体 *</span>
                      <textarea
                        v-model="bertopicPromptState.reclusterUserPrompt"
                        rows="10"
                        class="input run-textarea w-full mt-1.5 resize-y font-mono text-xs leading-relaxed"
                      ></textarea>
                    </label>
                    <div class="workflow-note workflow-note--brand space-y-1">
                      <p class="font-semibold">可用变量：</p>
                      <p class="font-mono">{TARGET_TOPICS}, {input_data}, {topic_list}, {business_rules_hint}, {iteration_hint}</p>
                    </div>
                  </div>
                </div>
              </div>

              <!-- Loop connector with RETRY annotation -->
              <div class="loop-connector">
                <div class="connector-line"></div>
                <div class="retry-annotation">
                  <ArrowUturnUpIcon class="h-3 w-3" />
                  <span>触发大主题保护 · 最大丢弃率限制兜底后重试</span>
                </div>
              </div>

              <!-- Agent 3: Relevance Judge -->
              <div class="agent-card agent-card-judge">
                <button type="button" class="agent-card-header" @click="agentExpanded[3] = !agentExpanded[3]">
                  <div class="agent-step agent-step-judge">3</div>
                  <div class="flex-1 min-w-0 text-left">
                    <div class="agent-name-row">
                      <span class="agent-en">Relevance Judge</span>
                      <span class="agent-zh">相关性裁判</span>
                    </div>
                    <p class="agent-desc">搭载 Sentence-BERT 语义向量审查，对不相关的残余底料执行一票否决，触发大主题保护及最大丢弃率限制兜底。</p>
                  </div>
                  <ChevronDownIcon class="agent-chevron" :class="{ 'rotate-180': agentExpanded[3] }" />
                </button>
                <div v-show="agentExpanded[3]" class="agent-config">
                  <div class="grid gap-4 lg:grid-cols-4 mb-4">
                    <label class="runtime-field">
                      <span class="runtime-field-label">启用预过滤</span>
                      <span class="runtime-field-key">pre_filter_enabled</span>
                      <div class="runtime-toggle-row">
                        <AppCheckbox v-model="bertopicPromptState.preFilterEnabled" />
                        <span class="runtime-toggle-text">启用</span>
                      </div>
                    </label>
                    <label class="runtime-field">
                      <span class="runtime-field-label">最低相似度</span>
                      <span class="runtime-field-key">similarity_floor</span>
                      <input v-model.number="bertopicPromptState.preFilterSimilarityFloor" type="number" min="0"
                        max="0.95" step="0.01" class="input runtime-input w-full" />
                    </label>
                    <label class="runtime-field">
                      <span class="runtime-field-label">最大丢弃比例</span>
                      <span class="runtime-field-key">max_drop_ratio</span>
                      <input v-model.number="bertopicPromptState.preFilterMaxDropRatio" type="number" min="0" max="0.9"
                        step="0.01" class="input runtime-input w-full" />
                    </label>
                    <div class="rounded-2xl border border-soft bg-surface/60 px-4 py-3 text-[11px] text-secondary leading-5">
                      <p>推荐起点：<code>0.24 / 0.35</code></p>
                      <p>误杀相关文本→降低相似度；噪声仍多→提高相似度或收紧丢弃比例。</p>
                    </div>
                  </div>
                  <div class="grid gap-4 md:grid-cols-2">
                    <label class="block">
                      <span class="config-label">查询增强词</span>
                      <textarea
                        v-model="bertopicPromptState.preFilterQueryHint"
                        rows="3"
                        class="input run-textarea w-full mt-1.5 resize-y text-xs leading-relaxed"
                        placeholder="补充专题锚点，例如：吸烟、戒烟、控烟政策、二手烟..."
                      ></textarea>
                    </label>
                    <label class="block">
                      <span class="config-label">排除词 / 负向约束</span>
                      <textarea
                        v-model="bertopicPromptState.preFilterNegativeHint"
                        rows="3"
                        class="input run-textarea w-full mt-1.5 resize-y text-xs leading-relaxed"
                        placeholder="命中这些词且未命中专题锚点时会优先剔除"
                      ></textarea>
                    </label>
                  </div>
                </div>
              </div>

              <!-- Loop connector -->
              <div class="loop-connector">
                <div class="connector-line"></div>
              </div>

              <!-- Agent 4: Custom Filter Judge -->
              <div class="agent-card agent-card-filter">
                <button type="button" class="agent-card-header" @click="agentExpanded[4] = !agentExpanded[4]">
                  <div class="agent-step agent-step-filter">4</div>
                  <div class="flex-1 min-w-0 text-left">
                    <div class="agent-name-row">
                      <span class="agent-en">Custom Filter Judge</span>
                      <span class="agent-zh">定制过滤器</span>
                    </div>
                    <p class="agent-desc">执行系统级及项目级的排除规则（如：排除"无关噪音"），逐一对聚类执行语义核对裁剪。</p>
                  </div>
                  <ChevronDownIcon class="agent-chevron" :class="{ 'rotate-180': agentExpanded[4] }" />
                </button>
                <div v-show="agentExpanded[4]" class="agent-config space-y-5">
                  <div class="grid gap-4 lg:grid-cols-2">
                    <!-- Global Filters -->
                    <div class="space-y-3 rounded-2xl border border-soft bg-surface/70 p-4">
                      <label class="text-xs font-bold text-primary flex items-center gap-2">
                        <GlobeAltIcon class="h-4 w-4 text-secondary/70" />
                        全局通用屏蔽
                      </label>
                      <p class="text-[11px] text-secondary leading-relaxed">系统内置的常态化噪声，适用于绝大多数分析场景。</p>
                      <div class="noise-card">
                        <div v-for="(gf, gfIndex) in ['明星八卦', '广告推广', '抽奖转发', '求职招聘']" :key="gf"
                          class="global-filter-row">
                          <span class="text-xs font-semibold text-primary">{{ gf }}</span>
                          <AppCheckbox
                            :id="`global-filter-switch-${gfIndex}`"
                            :model-value="bertopicPromptState.globalFilters.includes(gf)"
                            :aria-label="`切换${gf}`"
                            input-class="shadow-none"
                            @change="toggleGlobalFilter(gf)"
                          />
                        </div>
                      </div>
                    </div>

                    <!-- Project Filters -->
                    <div class="space-y-3 rounded-2xl border border-soft bg-surface/70 p-4">
                      <label class="text-xs font-bold text-primary flex items-center gap-2">
                        <FolderOpenIcon class="h-4 w-4 text-secondary/70" />
                        本项目专项屏蔽
                      </label>
                      <p class="text-[11px] text-secondary leading-relaxed">仅针对当前专题添加的独立黑名单。</p>
                      <div class="rule-input-shell project-filter-shell">
                        <div class="flex flex-col gap-1.5 mb-2" v-if="bertopicPromptState.projectFilters.length > 0">
                          <span v-for="(pf, idx) in bertopicPromptState.projectFilters" :key="idx" class="chip-row">
                            <span class="chip-row__content" :title="pf.description || pf.category">
                              <span class="chip-row__category">{{ getProjectFilterCategory(pf) }}</span>
                              <span v-if="getProjectFilterDescription(pf)" class="chip-row__description">
                                {{ getProjectFilterDescription(pf) }}
                              </span>
                            </span>
                            <button type="button" @click="bertopicPromptState.projectFilters.splice(idx, 1)"
                              class="text-danger rounded-full shrink-0">
                              <XMarkIcon class="h-3 w-3" />
                            </button>
                          </span>
                        </div>
                        <div class="project-filter-form">
                          <input type="text" v-model.trim="newFilterCategory" @keyup.enter="addFilter"
                            class="input project-filter-input" placeholder="类别名称，如：本地资讯" />
                          <div class="input-inline-shell">
                            <input type="text" v-model.trim="newFilterDescription" @keyup.enter="addFilter"
                              class="w-full text-xs border-none bg-transparent focus:ring-0 p-0 placeholder:text-muted/70"
                              placeholder="补充特征限制（可选）..." />
                          </div>
                          <button type="button" @click="addFilter" class="btn-secondary project-filter-submit"
                            :disabled="!newFilterCategory">添加</button>
                        </div>
                        <p class="project-filter-hint">可在任一输入框按回车添加</p>
                      </div>
                    </div>
                  </div>

                  <!-- Core Drop Rules -->
                  <div class="space-y-2">
                    <label class="text-xs font-bold text-primary flex items-center gap-2">
                      <AdjustmentsHorizontalIcon class="h-4 w-4 text-danger" />
                      相关性补充指令
                    </label>
                    <p class="text-[11px] text-secondary leading-relaxed">非纯净类别的细粒度甄别（例如："如果是提及品牌但作为负面竞品对比，一律剔除"）。</p>
                    <div class="rule-input-shell">
                      <div class="flex flex-col gap-1.5 mb-2" v-if="bertopicPromptState.coreDropRules.length > 0">
                        <span v-for="(rule, idx) in bertopicPromptState.coreDropRules" :key="idx"
                          class="chip chip--success-strong">
                          <div class="chip-dot"></div>
                          <span class="flex-1 leading-relaxed">{{ rule }}</span>
                          <button type="button" @click="bertopicPromptState.coreDropRules.splice(idx, 1)"
                            class="chip__remove p-0.5 self-center shrink-0"><XMarkIcon class="h-3.5 w-3.5" /></button>
                        </span>
                      </div>
                      <input type="text" v-model="draftDropRule" @keyup.enter="addRule('drop')"
                        class="w-full text-[11px] border-none bg-transparent focus:ring-0 px-2 py-1 placeholder:text-muted"
                        placeholder="输入相关性甄别条件，按回车添加..." />
                    </div>
                  </div>

                  <!-- Drop Rule Prompt (Expert) -->
                  <div v-show="promptMode === 'expert'" class="space-y-3 border-t border-soft pt-4">
                    <div class="flex items-center justify-between">
                      <span class="config-label">基础判定规则 (Drop Rule Prompt)</span>
                      <button type="button" class="btn-secondary px-3 py-1.5 text-xs"
                        @click="restoreDefaultDropRulePrompt">恢复通用模板</button>
                    </div>
                    <textarea
                      v-model="bertopicPromptState.dropRulePrompt"
                      rows="12"
                      class="input run-textarea w-full resize-y font-mono text-xs leading-relaxed"
                    ></textarea>
                    <div class="workflow-note workflow-note--danger">
                      <p class="font-semibold">可用变量：</p>
                      <p class="font-mono">{FOCUS_TOPIC}</p>
                    </div>
                  </div>
                </div>
              </div>

            </div><!-- /loop-body -->
          </div><!-- /loop-wrapper -->

          <!-- Connector to Agent 5 -->
          <div class="pipeline-connector">
            <div class="connector-line"></div>
          </div>

          <!-- ── Agent 5: Naming & Keywords (Optional) ── -->
          <div class="agent-card agent-card-naming relative">
            <div class="optional-badge">Optional</div>
            <button type="button" class="agent-card-header" @click="agentExpanded[5] = !agentExpanded[5]">
              <div class="agent-step agent-step-naming">5</div>
              <div class="flex-1 min-w-0 text-left">
                <div class="agent-name-row">
                  <span class="agent-en">Naming &amp; Keywords</span>
                  <span class="agent-zh">文采润色师</span>
                </div>
                <p class="agent-desc">对经过层层筛选的高质量聚类进行最终语义化包装，生成高可读性的名称和精准摘要标签。</p>
              </div>
              <ChevronDownIcon class="agent-chevron" :class="{ 'rotate-180': agentExpanded[5] }" />
            </button>
            <div v-show="agentExpanded[5]" class="agent-config space-y-4">
              <label class="block">
                <span class="config-label">关键词 System Prompt (可选)</span>
                <textarea
                  v-model="bertopicPromptState.keywordSystemPrompt"
                  rows="2"
                  class="input run-textarea w-full mt-1.5 resize-y font-mono text-xs leading-relaxed"
                ></textarea>
              </label>
              <label class="block">
                <span class="config-label">关键词 User Prompt *</span>
                <textarea
                  v-model="bertopicPromptState.keywordUserPrompt"
                  rows="8"
                  class="input run-textarea w-full mt-1.5 resize-y font-mono text-xs leading-relaxed"
                ></textarea>
              </label>
              <div class="workflow-note workflow-note--success space-y-1">
                <p class="font-semibold">可用变量：</p>
                <p class="font-mono">{cluster_name}, {topics}, {topics_csv}, {topics_json}, {description}</p>
              </div>
            </div>
          </div>

          </div>
        </div>
      </AnalysisSectionCard>

      <AnalysisSectionCard
        v-if="showAdvancedSettings"
        title="项目停用词"
        description="仅对当前专题生效，会与共享停用词设置一并参与分词。"
        tone="soft"
      >
        <div class="space-y-4">
          <div class="flex justify-end">
            <span class="analysis-chip analysis-chip--hero">当前行数：{{ projectStopwordCount }}</span>
          </div>
          <textarea
            v-model="bertopicPromptState.projectStopwordsText"
            rows="12"
            class="input min-h-[320px] w-full resize-y font-mono text-sm leading-6"
            placeholder="一行一个项目停用词"
          ></textarea>
        </div>
      </AnalysisSectionCard>

      <AnalysisSectionCard
        v-if="showAdvancedSettings"
        title="底层算法参数"
        description="仅在需要微调聚类效果时再修改。多数场景保持默认值即可。"
        tone="soft"
      >
        <div class="runtime-compact space-y-5">
          <div class="flex items-center justify-between gap-3">
            <div class="flex items-center gap-2 text-sm font-semibold text-primary">
              <CpuChipIcon class="h-4 w-4 text-muted" />
              <span>当前运行参数</span>
            </div>
            <button
              type="button"
              class="analysis-toolbar__action analysis-toolbar__action--ghost px-3 py-1.5 text-xs focus-ring-accent"
              @click="resetRunParams"
              :disabled="runState.running"
            >
              恢复默认值
            </button>
          </div>
          <div class="space-y-5">
            <!-- CountVectorizer -->
            <div>
              <h4 class="runtime-group-title">CountVectorizer (词向量化)</h4>
              <div class="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                <label class="runtime-field">
                  <span class="runtime-field-label">最小词组长度</span>
                  <span class="runtime-field-key">ngram_min</span>
                  <input v-model.number="form.runParams.vectorizer.ngram_min" type="number" min="1"
                    class="input runtime-input w-full" />
                </label>
                <label class="runtime-field">
                  <span class="runtime-field-label">最大词组长度</span>
                  <span class="runtime-field-key">ngram_max</span>
                  <input v-model.number="form.runParams.vectorizer.ngram_max" type="number" min="1"
                    class="input runtime-input w-full" />
                </label>
                <label class="runtime-field">
                  <span class="runtime-field-label">最小词频过滤</span>
                  <span class="runtime-field-key">min_df</span>
                  <input v-model.number="form.runParams.vectorizer.min_df" type="number" min="0" step="0.1"
                    class="input runtime-input w-full" />
                </label>
                <label class="runtime-field">
                  <span class="runtime-field-label">最大词频过滤</span>
                  <span class="runtime-field-key">max_df</span>
                  <input v-model.number="form.runParams.vectorizer.max_df" type="number" min="0" step="0.1"
                    class="input runtime-input w-full" />
                </label>
              </div>
            </div>
            <!-- UMAP -->
            <div>
              <h4 class="runtime-group-title">UMAP (降维)</h4>
              <div class="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                <label class="runtime-field">
                  <span class="runtime-field-label">近邻数量</span>
                  <span class="runtime-field-key">n_neighbors</span>
                  <input v-model.number="form.runParams.umap.n_neighbors" type="number" min="2"
                    class="input runtime-input w-full" />
                </label>
                <label class="runtime-field">
                  <span class="runtime-field-label">降维目标维度</span>
                  <span class="runtime-field-key">n_components</span>
                  <input v-model.number="form.runParams.umap.n_components" type="number" min="2"
                    class="input runtime-input w-full" />
                </label>
                <label class="runtime-field">
                  <span class="runtime-field-label">点间最小距离</span>
                  <span class="runtime-field-key">min_dist</span>
                  <input v-model.number="form.runParams.umap.min_dist" type="number" min="0" step="0.05"
                    class="input runtime-input w-full" />
                </label>
                <label class="runtime-field">
                  <span class="runtime-field-label">距离度量</span>
                  <span class="runtime-field-key">metric</span>
                  <AppSelect
                    :options="umapMetricOptions"
                    :value="form.runParams.umap.metric"
                    @change="form.runParams.umap.metric = $event"
                  />
                </label>
                <label class="runtime-field">
                  <span class="runtime-field-label">随机种子</span>
                  <span class="runtime-field-key">random_state</span>
                  <input v-model.number="form.runParams.umap.random_state" type="number"
                    class="input runtime-input w-full" />
                </label>
              </div>
            </div>
            <!-- HDBSCAN -->
            <div>
              <h4 class="runtime-group-title">HDBSCAN (聚类)</h4>
              <div class="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                <label class="runtime-field">
                  <span class="runtime-field-label">最小聚类规模</span>
                  <span class="runtime-field-key">min_cluster_size</span>
                  <input v-model.number="form.runParams.hdbscan.min_cluster_size" type="number" min="2"
                    class="input runtime-input w-full" />
                </label>
                <label class="runtime-field">
                  <span class="runtime-field-label">核心点邻域样本</span>
                  <span class="runtime-field-key">min_samples</span>
                  <input v-model.number="form.runParams.hdbscan.min_samples" type="number" min="1"
                    class="input runtime-input w-full" />
                </label>
                <label class="runtime-field">
                  <span class="runtime-field-label">距离度量</span>
                  <span class="runtime-field-key">metric</span>
                  <AppSelect
                    :options="hdbscanMetricOptions"
                    :value="form.runParams.hdbscan.metric"
                    @change="form.runParams.hdbscan.metric = $event"
                  />
                </label>
                <label class="runtime-field">
                  <span class="runtime-field-label">簇选择算法</span>
                  <span class="runtime-field-key">selection_method</span>
                  <AppSelect
                    :options="hdbscanSelectionMethodOptions"
                    :value="form.runParams.hdbscan.cluster_selection_method"
                    @change="form.runParams.hdbscan.cluster_selection_method = $event"
                  />
                </label>
              </div>
            </div>
            <!-- BERTopic -->
            <div>
              <h4 class="runtime-group-title">BERTopic (主题建模)</h4>
              <div class="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                <label class="runtime-field">
                  <span class="runtime-field-label">主题词展示数</span>
                  <span class="runtime-field-key">top_n_words</span>
                  <input v-model.number="form.runParams.bertopic.top_n_words" type="number" min="5"
                    class="input runtime-input w-full" />
                </label>
                <label class="runtime-field">
                  <span class="runtime-field-label">计算文档-主题概率</span>
                  <span class="runtime-field-key">calculate_probabilities</span>
                  <div class="runtime-toggle-row">
                    <AppCheckbox v-model="form.runParams.bertopic.calculate_probabilities" />
                    <span class="runtime-toggle-text">启用</span>
                  </div>
                </label>
                <label class="runtime-field">
                  <span class="runtime-field-label">输出详细日志</span>
                  <span class="runtime-field-key">verbose</span>
                  <div class="runtime-toggle-row">
                    <AppCheckbox v-model="form.runParams.bertopic.verbose" />
                    <span class="runtime-toggle-text">启用</span>
                  </div>
                </label>
              </div>
            </div>
          </div>
        </div>
      </AnalysisSectionCard>

      <AnalysisSectionCard
        v-if="logs.length > 0"
        title="运行日志"
        description="展示最近一次提交后返回的运行状态。"
        tone="soft"
      >
        <AnalysisLogList :logs="logs" class="max-h-[300px] overflow-y-auto" empty-label="等待执行…" />
      </AnalysisSectionCard>

      <!-- Failure Warning -->
      <section v-if="logs.some(log => log.status === 'error')"
        class="state-banner state-banner-danger animate-in slide-in-from-top-1">
        <div class="flex items-start gap-3">
          <ExclamationCircleIcon class="h-6 w-6 shrink-0" />
          <div>
            <p class="font-bold">任务执行中断</p>
            <p class="text-sm mt-1">{{ logs.find(log => log.status === 'error')?.message || '发生未知错误' }}</p>
          </div>
        </div>
      </section>

      <!-- Success Result -->
      <section v-if="lastResult" class="state-banner state-banner-success p-6 animate-in slide-in-from-bottom-2">
        <div class="flex items-center gap-5">
          <div class="result-badge">
            <CheckBadgeIcon class="h-8 w-8" />
          </div>
          <div class="space-y-1">
            <h2 class="text-xl font-bold text-primary">分析完成</h2>
            <p class="text-sm text-secondary">主题模型已成功构建，相关数据资产已生成。</p>
          </div>
          <div class="ml-auto">
            <router-link :to="`/topic/bertopic/view`" class="btn btn-primary">
              查看分析报告
              <ArrowRightIcon class="h-4 w-4 ml-1" />
            </router-link>
          </div>
        </div>
      </section>
    </form>
  </div>
</template>

<script setup>
import { computed, watch, onMounted, ref, reactive } from 'vue'
import {
  ArrowPathIcon,
  ChevronDownIcon,
  CheckBadgeIcon,
  InformationCircleIcon,
  SparklesIcon,
  ViewColumnsIcon,
  CommandLineIcon,
  ArrowsPointingInIcon,
  ArrowsPointingOutIcon,
  XMarkIcon,
  ExclamationTriangleIcon,
  ExclamationCircleIcon,
  AdjustmentsHorizontalIcon,
  DocumentTextIcon,
  ArrowRightIcon,
  CpuChipIcon,
  FolderOpenIcon,
  GlobeAltIcon,
  ArrowUturnUpIcon
} from '@heroicons/vue/24/outline'
import AppCheckbox from '@/components/AppCheckbox.vue'
import AppSelect from '@/components/AppSelect.vue'
import TabSwitch from '@/components/TabSwitch.vue'
import AnalysisPageHeader from '@/components/analysis/AnalysisPageHeader.vue'
import AnalysisSectionCard from '@/components/analysis/AnalysisSectionCard.vue'
import { useTopicBertopicAnalysis } from '@/composables/useTopicBertopicAnalysis'
import { useActiveProject } from '@/composables/useActiveProject'
import AnalysisLogList from '@/components/analysis/AnalysisLogList.vue'

const {
  topicsState,
  topicOptions,
  form,
  bertopicPromptState,
  hasPromptDraftChanges,
  availableRange,
  runState,
  lastResult,
  logs,
  loadTopics,
  loadBertopicPrompt,
  saveBertopicPrompt,
  resetState,
  runBertopicAnalysis,
  resetRunParams
} = useTopicBertopicAnalysis()

const { activeProjectName } = useActiveProject()
const promptMode = ref('analyst')
const promptModeTabs = [
  { value: 'analyst', label: '业务调整模式' },
  { value: 'expert', label: '专家指令引擎', icon: CommandLineIcon }
]

const draftSeparateRule = ref('')
const draftMergeRule = ref('')
const draftDropRule = ref('')

const showAdvancedSettings = ref(false)
const newFilterCategory = ref('')
const newFilterDescription = ref('')

// Agent accordion state – all open by default
const agentExpanded = reactive({ 1: true, 2: true, 3: true, 4: true, 5: false })

const reclusterDimensionOptions = [
  { label: '默认 (综合语义)', value: '', description: '按整体语义自动归类，不强制单一分析维度，适合首次探索。' },
  { label: '业务场景', value: '业务场景', description: '优先按使用场景、业务流程或问题上下文进行分组。' },
  { label: '情感倾向', value: '情感倾向', description: '优先按正向、负向、中性等情绪态度进行聚类。' },
  { label: '对象实体', value: '对象实体', description: '优先按人物、机构、品牌、产品等被讨论对象进行划分。' }
]

const reclusterDimensionGuides = {
  业务场景: ['优先按业务链路阶段、用户诉求场景、问题处理环节进行一级分组。', '同一组需要能解释为同一业务情境下的同类问题或动作。', '若语义接近但业务动作不同，应拆分为不同类别。'],
  情感倾向: ['优先按情绪极性与立场方向分组（正向/负向/中性/争议）。', '同组内情绪基调应一致，不要把对立情绪合并。', '事实陈述类内容需先判断语气倾向再归类。'],
  对象实体: ['优先按被讨论对象分组（品牌/机构/人物/产品/渠道）。', '不同对象即使议题接近，也优先分开。', '对象指代不明时，先根据上下文补全主实体再聚类。']
}

const yamlQuote = (value) => `"${String(value ?? '').replace(/\\/g, '\\\\').replace(/"/g, '\\"')}"`

const reclusterDimensionPromptHint = computed(() => {
  const value = String(bertopicPromptState.reclusterDimension || '').trim()
  const seedTopics = (bertopicPromptState.mustSeparateRules || []).map(i => String(i || '').trim()).filter(Boolean)
  const mergeHints = (bertopicPromptState.mustMergeRules || []).map(i => String(i || '').trim()).filter(Boolean)

  if (!value && seedTopics.length === 0 && mergeHints.length === 0) {
    return '当前未配置业务规则，不会追加 business_rules 提示块。'
  }

  const lines = ['business_rules:']
  if (value) {
    const guides = reclusterDimensionGuides[value] || ['请先按该视角完成一级分组，再在组内做语义细分。', '同组需具备一致且可解释的共同特征，不可仅按表层关键词合并。', '类别命名需体现该视角，避免泛化命名。']
    lines.push('  recluster_strategy:', `    perspective: ${yamlQuote(value)}`, '    objective: "先按主导视角完成一级聚类，再在组内做语义细分与命名。"', '    guide:', ...guides.map(i => `      - ${yamlQuote(i)}`))
  }
  if (seedTopics.length > 0) {
    lines.push('  custom_topic_recognition:', '    seed_topics:', ...seedTopics.map(i => `      - ${yamlQuote(i)}`), '    assignment_rule:', '      - "与 seed_topics 语义高度相近的原始主题，优先归入同一类别。"', '      - "该类别与其他聚类流程一致，需进入后续命名与关键词生成阶段。"', '      - "若同时命中多个 seed_topics，按语义最贴近者归类并在描述中体现边界。"')
  }
  if (mergeHints.length > 0) {
    lines.push('  should_merge:', ...mergeHints.map(i => `    - ${yamlQuote(i)}`))
  }
  lines.push('  execution_requirements:', '    - "优先保证组内语义一致性，再控制组间边界清晰。"', '    - "custom_topic_recognition.seed_topics 仅定义归类锚点，不直接作为最终类别名。"', '    - "与 should_merge 冲突时，优先满足 seed_topics 的归类锚定。"', '    - "输出类别命名需可解释，并与主导视角保持一致。"')
  return lines.join('\n')
})

const splitProjectFilterText = (text = '') => {
  const raw = String(text || '').trim()
  if (!raw) return { category: '', description: '' }
  const parts = raw.split(/\s*[\/／|｜]\s*/g).map(p => p.trim()).filter(Boolean)
  if (parts.length <= 1) return { category: raw, description: '' }
  return { category: parts[0], description: parts.slice(1).join(' / ') }
}

const getProjectFilterCategory = (item) => {
  const rawCategory = String(item?.category || '').trim()
  if (!rawCategory) return '未命名类别'
  return splitProjectFilterText(rawCategory).category || rawCategory
}

const getProjectFilterDescription = (item) => {
  const rawDescription = String(item?.description || '').trim()
  if (rawDescription) return rawDescription
  const rawCategory = String(item?.category || '').trim()
  if (!rawCategory) return ''
  const parsed = splitProjectFilterText(rawCategory)
  return (parsed.category !== rawCategory && parsed.description) ? parsed.description : ''
}

const toggleGlobalFilter = (gf) => {
  const idx = bertopicPromptState.globalFilters.indexOf(gf)
  idx === -1 ? bertopicPromptState.globalFilters.push(gf) : bertopicPromptState.globalFilters.splice(idx, 1)
}

const addFilter = () => {
  const rawCategory = (newFilterCategory.value || '').trim()
  const rawDescription = (newFilterDescription.value || '').trim()
  if (!rawCategory) return
  let category = rawCategory
  let description = rawDescription
  if (!description) {
    const parsed = splitProjectFilterText(rawCategory)
    category = parsed.category || rawCategory
    description = parsed.description || ''
  }
  if (!category) return
  const exists = bertopicPromptState.projectFilters.some(i => String(i?.category || '').trim() === category && String(i?.description || '').trim() === description)
  if (!exists) bertopicPromptState.projectFilters.push({ category, description })
  newFilterCategory.value = ''
  newFilterDescription.value = ''
}

const restoreDefaultDropRulePrompt = () => {
  if (confirm('确定要恢复无关主题的基础判定模板吗？这会覆盖当前的指令。')) {
    bertopicPromptState.dropRulePrompt = bertopicPromptState.defaultDropRulePrompt
  }
}

const addRule = (type) => {
  if (type === 'separate') {
    const val = draftSeparateRule.value.trim()
    if (val && !bertopicPromptState.mustSeparateRules.includes(val)) bertopicPromptState.mustSeparateRules.push(val)
    draftSeparateRule.value = ''
  } else if (type === 'merge') {
    const val = draftMergeRule.value.trim()
    if (val && !bertopicPromptState.mustMergeRules.includes(val)) bertopicPromptState.mustMergeRules.push(val)
    draftMergeRule.value = ''
  } else if (type === 'drop') {
    const val = draftDropRule.value.trim()
    if (val && !bertopicPromptState.coreDropRules.includes(val)) bertopicPromptState.coreDropRules.push(val)
    draftDropRule.value = ''
  }
}

onMounted(() => { loadTopics(true) })

watch(activeProjectName, (value) => {
  if (!value) return
  form.project = value
  if (!form.topic) {
    const matched = topicOptions.value.find(t => t.name === value || t.display_name === value || t.bucket === value)
    if (matched) form.topic = matched.bucket
  }
  if (form.topic) loadBertopicPrompt(form.topic)
}, { immediate: true })

const canSavePrompt = computed(() => Boolean(form.topic.trim() && !bertopicPromptState.loading && !bertopicPromptState.saving))

const projectStopwordCount = computed(() => String(bertopicPromptState.projectStopwordsText || '').split(/\r?\n/).map(l => l.trim()).filter(Boolean).length)

const topicSelectOptions = computed(() =>
  topicOptions.value.map(option => ({
    value: option.bucket,
    label: option.display_name || option.name
  }))
)

const umapMetricOptions = [
  { value: 'cosine', label: 'cosine' },
  { value: 'euclidean', label: 'euclidean' },
  { value: 'manhattan', label: 'manhattan' }
]

const hdbscanMetricOptions = [
  { value: 'euclidean', label: 'euclidean' },
  { value: 'manhattan', label: 'manhattan' },
  { value: 'cosine', label: 'cosine' }
]

const hdbscanSelectionMethodOptions = [
  { value: 'eom', label: 'eom (叶节点过多时合并)' },
  { value: 'leaf', label: 'leaf (保留所有叶节点)' }
]

const handleTopicChange = (value) => {
  form.topic = value
}

const canSubmit = computed(() => Boolean(form.topic.trim() && form.startDate.trim() && !runState.running && !availableRange.loading && !bertopicPromptState.saving && !bertopicPromptState.loading))

const resetAll = () => { form.startDate = ''; form.endDate = ''; resetState() }

const handleRun = async () => {
  try {
    if (hasPromptDraftChanges.value) await saveBertopicPrompt({ topic: form.topic })
    await runBertopicAnalysis({ topic: form.topic, startDate: form.startDate, endDate: form.endDate })
  } catch { /* 错误处理已在日志组件体现 */ }
}

const handleSavePrompt = async () => {
  try { await saveBertopicPrompt({ topic: form.topic }) } catch { /* 错误提示由状态区域显示 */ }
}
</script>

<style scoped>
.bertopic-run :deep(.input) {
  border-radius: 1rem;
  border: 1px solid var(--color-border-soft);
  background-color: var(--color-bg-base-soft);
  box-shadow: none;
}

.bertopic-run :deep(.input:focus) {
  border-color: rgb(var(--color-brand-400) / 1);
  background-color: var(--color-surface);
  box-shadow: 0 0 0 2px rgb(var(--color-brand-500) / 0.2);
}
.bertopic-run :deep(.btn-primary) {
  background-color: rgb(var(--color-brand-600) / 1);
  box-shadow: none;
}

.bertopic-run :deep(.btn-primary:hover:not(:disabled)) {
  background-color: rgb(var(--color-brand-500) / 1);
}

.bertopic-run :deep(.btn-secondary),
.bertopic-run :deep(.btn-ghost) {
  box-shadow: none;
}

.run-textarea {
  line-height: 1.55;
}

.run-footer {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  border-top: 1px solid var(--color-border-soft);
  padding-top: 1.25rem;
}

.bertopic-toggle {
  min-height: 2.75rem;
}

.workflow-summary {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  gap: 1rem;
  align-items: center;
  border: 1px solid rgb(var(--color-brand-200) / 0.75);
  border-radius: 1.25rem;
  background: linear-gradient(135deg, rgb(var(--color-brand-100) / 0.4), rgb(var(--color-accent-50) / 0.35));
  padding: 1rem 1.125rem;
}

.workflow-summary__icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 2.5rem;
  height: 2.5rem;
  border-radius: 0.95rem;
  border: 1px solid rgb(var(--color-brand-200) / 1);
  background-color: rgb(var(--color-brand-100) / 0.9);
  color: rgb(var(--color-brand-700) / 1);
}

.workflow-summary__title-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem;
}

.workflow-summary__title {
  font-size: 0.95rem;
  font-weight: 700;
  color: var(--color-text-primary);
}

.workflow-summary__description {
  font-size: 0.8rem;
  line-height: 1.6;
  color: var(--color-text-secondary);
}

.workflow-summary__actions {
  justify-content: flex-end;
}

.pipeline-flow {
  display: flex;
  flex-direction: column;
  gap: 0;
}

.pipeline-connector,
.loop-connector {
  display: flex;
  justify-content: center;
  position: relative;
}

.pipeline-connector {
  height: 1.5rem;
}

.loop-connector {
  min-height: 1.25rem;
}

.connector-line {
  width: 1px;
  height: 100%;
  border-radius: 999px;
  background-color: var(--color-border-soft);
}

.retry-annotation {
  position: absolute;
  left: 50%;
  top: 50%;
  transform: translate(-50%, -50%);
  display: inline-flex;
  align-items: center;
  gap: 0.3rem;
  justify-content: center;
  padding: 0;
  font-size: 10px;
  font-weight: 600;
  color: rgb(var(--color-accent-700) / 1);
  white-space: nowrap;
  text-align: center;
}

.agent-card {
  --agent-accent: rgb(var(--color-brand-700) / 1);
  --agent-border: var(--color-border-soft);
  --agent-surface: rgb(var(--color-brand-100) / 0.26);
  --agent-surface-hover: rgb(var(--color-brand-100) / 0.4);
  position: relative;
  border: 1px solid var(--agent-border);
  border-radius: 1.35rem;
  background-color: var(--color-surface);
  overflow: hidden;
  transition: border-color 0.2s ease, box-shadow 0.2s ease;
}

.agent-card:focus-within {
  box-shadow: 0 0 0 2px rgb(var(--color-brand-200) / 0.3);
}

.agent-card-header {
  display: flex;
  align-items: flex-start;
  gap: 0.875rem;
  width: 100%;
  border: none;
  background-color: var(--agent-surface);
  padding: 1rem 1.125rem;
  text-align: left;
  cursor: pointer;
  transition: background-color 0.15s ease;
}

.agent-card-header:hover {
  background-color: var(--agent-surface-hover);
}

.agent-config {
  border-top: 1px solid var(--agent-border);
  padding: 1rem 1.125rem 1.125rem;
  animation: fadeDown 0.18s ease;
}

@keyframes fadeDown {
  from {
    opacity: 0;
    transform: translateY(-4px);
  }

  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.agent-step {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 1.95rem;
  height: 1.95rem;
  margin-top: 0.05rem;
  flex-shrink: 0;
  border: 1px solid var(--agent-border);
  border-radius: 0.7rem;
  background-color: var(--agent-surface-hover);
  color: var(--agent-accent);
  font-size: 0.8rem;
  font-weight: 800;
}

.agent-card-scope {
  --agent-accent: rgb(var(--color-brand-700) / 1);
  --agent-border: rgb(var(--color-brand-200) / 0.95);
  --agent-surface: rgb(var(--color-brand-100) / 0.28);
  --agent-surface-hover: rgb(var(--color-brand-100) / 0.5);
}

.agent-card-cluster {
  --agent-accent: rgb(var(--color-accent-700) / 1);
  --agent-border: rgb(var(--color-accent-200) / 0.95);
  --agent-surface: rgb(var(--color-accent-100) / 0.28);
  --agent-surface-hover: rgb(var(--color-accent-100) / 0.48);
}

.agent-card-judge {
  --agent-accent: rgb(var(--color-warning-700) / 1);
  --agent-border: rgb(var(--color-warning-200) / 1);
  --agent-surface: rgb(var(--color-warning-100) / 0.3);
  --agent-surface-hover: rgb(var(--color-warning-100) / 0.5);
}

.agent-card-filter {
  --agent-accent: rgb(var(--color-danger-700) / 1);
  --agent-border: rgb(var(--color-danger-200) / 1);
  --agent-surface: rgb(var(--color-danger-100) / 0.28);
  --agent-surface-hover: rgb(var(--color-danger-100) / 0.48);
}

.agent-card-naming {
  --agent-accent: rgb(var(--color-success-700) / 1);
  --agent-border: rgb(var(--color-success-200) / 1);
  --agent-surface: rgb(var(--color-success-100) / 0.28);
  --agent-surface-hover: rgb(var(--color-success-100) / 0.48);
}

.agent-name-row {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 0.5rem;
  margin-bottom: 0.2rem;
}

.agent-en {
  font-size: 0.9rem;
  font-weight: 700;
  color: var(--color-text-primary);
}

.agent-zh {
  font-size: 0.75rem;
  font-weight: 600;
  color: var(--color-text-secondary);
}

.agent-desc {
  margin: 0;
  font-size: 12px;
  line-height: 1.55;
  color: var(--color-text-secondary);
}

.agent-chevron {
  width: 1.125rem;
  height: 1.125rem;
  flex-shrink: 0;
  margin-top: 0.25rem;
  color: var(--color-text-muted);
  transition: transform 0.2s ease;
}

/* ── Core Refinement Loop ── */
.loop-wrapper {
  border: 1px dashed rgb(var(--color-accent-200) / 1);
  border-radius: 1.5rem;
  background: linear-gradient(180deg, rgb(var(--color-accent-50) / 0.45), transparent 14rem);
  overflow: hidden;
}

.loop-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  padding: 0.75rem 1rem;
  border-bottom: 1px dashed rgb(var(--color-accent-200) / 0.95);
  background-color: rgb(var(--color-accent-50) / 0.78);
}

.loop-header-left {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.loop-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 1.45rem;
  height: 1.45rem;
  border-radius: 0.5rem;
  background-color: rgb(var(--color-accent-100) / 1);
  color: rgb(var(--color-accent-700) / 1);
}

.loop-title {
  font-size: 0.72rem;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: rgb(var(--color-accent-700) / 1);
}

.loop-badge,
.retry-rail {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  border: 1px solid rgb(var(--color-accent-200) / 1);
  border-radius: 999px;
  background-color: rgb(var(--color-accent-100) / 0.75);
  padding: 0.18rem 0.55rem;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.03em;
  color: rgb(var(--color-accent-700) / 1);
}

.loop-body {
  display: flex;
  flex-direction: column;
  gap: 0;
  padding: 0.875rem;
}

/* ── Optional Badge ── */
.optional-badge {
  position: absolute;
  top: 0.75rem;
  right: 0.875rem;
  border: 1px solid rgb(var(--color-success-200) / 1);
  border-radius: 999px;
  background-color: rgb(var(--color-success-100) / 0.85);
  padding: 0.18rem 0.55rem;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.03em;
  text-transform: uppercase;
  color: rgb(var(--color-success-700) / 1);
}

/* ── Config label / hint ── */
.config-label {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--color-text-muted);
}

.config-hint {
  display: block;
  margin-top: 0.25rem;
  font-size: 11px;
  color: var(--color-text-muted);
}

/* ── Runtime field base ── */
.runtime-field {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
}

.runtime-field-label {
  display: block;
  font-size: 0.82rem;
  font-weight: 700;
  line-height: 1.3;
  color: var(--color-text-primary);
}

.runtime-field-key {
  display: none;
}

:deep(.runtime-input) {
  min-height: 2.05rem;
  padding: 0.4rem 0.8rem;
  border-radius: 0.875rem;
  font-size: 0.82rem;
}

.runtime-toggle-row {
  display: flex;
  align-items: center;
  gap: 0.45rem;
  padding-top: 0.15rem;
}

.runtime-toggle-text {
  font-size: 0.82rem;
  color: var(--color-text-secondary);
}

/* ── Runtime compact ── */
.runtime-compact .runtime-group-title {
  margin-bottom: 0.45rem;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--color-text-muted);
}

.runtime-compact .runtime-field {
  gap: 0.2rem;
}

.runtime-compact .runtime-field-label {
  font-size: 12px;
  font-weight: 600;
  line-height: 1.2;
}

.runtime-compact :deep(.runtime-input) {
  font-size: 0.82rem;
}

.runtime-compact .runtime-toggle-row {
  padding-top: 0.15rem;
}

.runtime-compact .runtime-toggle-text {
  font-size: 0.75rem;
}

/* ── State Banners ── */
.state-banner {
  border-width: 1px;
  border-style: solid;
  border-radius: 1rem;
  padding: 1rem;
}

.state-banner-info {
  border-color: rgb(var(--color-accent-200) / 1);
  background-color: rgb(var(--color-accent-50) / 0.72);
  color: rgb(var(--color-accent-700) / 1);
}

.state-banner-danger {
  border-color: rgb(var(--color-danger-200) / 1);
  background-color: rgb(var(--color-danger-50) / 1);
  color: rgb(var(--color-danger-700) / 1);
}

.state-banner-success {
  border-color: rgb(var(--color-success-200) / 1);
  background-color: rgb(var(--color-success-50) / 0.85);
  color: rgb(var(--color-success-700) / 1);
}

.state-banner__icon-info {
  color: rgb(var(--color-accent-500) / 1);
}

.state-banner__icon-danger {
  color: rgb(var(--color-danger-500) / 1);
}

.state-note,
.workflow-note {
  border-width: 1px;
  border-style: solid;
  border-radius: 0.85rem;
  padding: 0.75rem;
  font-size: 11px;
}

.state-note-accent {
  border-color: rgb(var(--color-accent-200) / 1);
  background-color: rgb(var(--color-accent-50) / 0.75);
  color: rgb(var(--color-accent-700) / 1);
}

.workflow-note--brand {
  border-color: rgb(var(--color-brand-200) / 1);
  background-color: rgb(var(--color-brand-100) / 0.55);
  color: rgb(var(--color-brand-700) / 1);
}

.workflow-note--danger {
  border-color: rgb(var(--color-danger-200) / 1);
  background-color: rgb(var(--color-danger-100) / 0.55);
  color: rgb(var(--color-danger-700) / 1);
}

.workflow-note--success {
  border-color: rgb(var(--color-success-200) / 1);
  background-color: rgb(var(--color-success-100) / 0.55);
  color: rgb(var(--color-success-700) / 1);
}

/* ── Pill Buttons ── */
.pill-btn {
  border: 1px solid var(--color-border-soft);
  border-radius: 999px;
  padding: 0.4rem 0.8rem;
  font-size: 0.75rem;
  font-weight: 600;
  transition: border-color 0.2s ease, color 0.2s ease, background-color 0.2s ease;
}

.pill-btn--active {
  border-color: rgb(var(--color-brand-300) / 1);
  background-color: rgb(var(--color-brand-100) / 0.8);
  color: rgb(var(--color-brand-700) / 1);
}

.pill-btn--idle {
  background-color: var(--color-surface);
  color: var(--color-text-secondary);
}

.pill-btn--idle:hover {
  border-color: rgb(var(--color-brand-200) / 1);
  background-color: rgb(var(--color-brand-100) / 0.35);
  color: rgb(var(--color-brand-700) / 1);
}

/* ── Dimension Popover ── */
.dimension-info-trigger {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 1.5rem;
  height: 1.5rem;
  border: 1px solid var(--color-border-soft);
  border-radius: 999px;
  background-color: var(--color-surface);
  color: var(--color-text-muted);
  transition: color 0.2s ease, border-color 0.2s ease, background-color 0.2s ease;
}

.dimension-info-trigger:hover,
.group:focus-within .dimension-info-trigger {
  border-color: rgb(var(--color-brand-300) / 1);
  background-color: rgb(var(--color-brand-100) / 0.35);
  color: rgb(var(--color-brand-700) / 1);
}

.dimension-info-popover {
  position: absolute;
  top: calc(100% + 0.5rem);
  right: 0;
  z-index: 30;
  width: 22rem;
  max-width: 85vw;
  border: 1px solid var(--color-border-soft);
  border-radius: 0.85rem;
  background: linear-gradient(180deg, var(--color-surface), rgb(var(--color-brand-100) / 0.2));
  padding: 0.75rem;
  opacity: 0;
  pointer-events: none;
  transform: translateY(-4px);
  transition: opacity 0.2s ease, transform 0.2s ease;
}

.group:hover .dimension-info-popover,
.group:focus-within .dimension-info-popover {
  opacity: 1;
  pointer-events: auto;
  transform: translateY(0);
}

.dimension-info-title {
  margin-bottom: 0.375rem;
  font-size: 0.75rem;
  font-weight: 700;
  color: var(--color-text-primary);
}

.dimension-info-code {
  margin-top: 0.45rem;
  border: 1px solid rgb(var(--color-brand-200) / 1);
  border-radius: 0.65rem;
  background-color: rgb(var(--color-brand-100) / 0.4);
  padding: 0.5rem;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 11px;
  line-height: 1.5;
  color: rgb(var(--color-brand-700) / 1);
  white-space: pre-wrap;
}

.dimension-explain-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0.5rem;
  margin-top: 0.25rem;
}

.dimension-explain-item {
  border: 1px solid var(--color-border-soft);
  border-radius: 0.85rem;
  background-color: rgb(var(--color-brand-100) / 0.18);
  padding: 0.6rem 0.7rem;
}

.dimension-explain-item--active {
  border-color: rgb(var(--color-brand-300) / 1);
  background-color: rgb(var(--color-brand-100) / 0.55);
}

.dimension-explain-title {
  font-size: 11px;
  font-weight: 700;
  color: var(--color-text-primary);
}

.dimension-explain-item--active .dimension-explain-title {
  color: rgb(var(--color-brand-700) / 1);
}

.dimension-explain-text {
  margin-top: 0.2rem;
  font-size: 10px;
  line-height: 1.45;
  color: var(--color-text-secondary);
}

/* ── Rule Input Shells ── */
.rule-input-shell {
  border: 1px solid var(--color-border-soft);
  border-radius: 0.85rem;
  background-color: var(--color-bg-base-soft);
  padding: 0.55rem;
  transition: border-color 0.2s ease, box-shadow 0.2s ease;
}

.rule-input-shell:focus-within {
  border-color: rgb(var(--color-brand-300) / 1);
  box-shadow: 0 0 0 2px rgb(var(--color-brand-500) / 0.1);
}

/* ── Noise Cards / Switches ── */
.noise-card {
  border: 1px solid var(--color-border-soft);
  border-radius: 0.95rem;
  background-color: var(--color-bg-base-soft);
  overflow: hidden;
}

.global-filter-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  padding: 0.7rem 0.875rem;
}

.global-filter-row + .global-filter-row {
  border-top: 1px solid var(--color-border-soft);
}

/* ── Chips ── */
.chip {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  border-width: 1px;
  border-style: solid;
  border-radius: 0.6rem;
  padding: 0.25rem 0.5rem;
  font-size: 11px;
  font-weight: 600;
}

.chip--accent {
  border-color: rgb(var(--color-accent-200) / 1);
  background-color: rgb(var(--color-accent-100) / 0.85);
  color: rgb(var(--color-accent-700) / 1);
}

.chip--success {
  border-color: rgb(var(--color-success-200) / 1);
  background-color: rgb(var(--color-success-100) / 0.85);
  color: rgb(var(--color-success-700) / 1);
}

.chip--success-strong {
  align-items: flex-start;
  border-color: rgb(var(--color-success-200) / 1);
  background-color: rgb(var(--color-success-100) / 0.75);
  color: rgb(var(--color-success-700) / 1);
}

.chip-dot {
  width: 0.375rem;
  height: 0.375rem;
  margin-top: 0.25rem;
  flex-shrink: 0;
  border-radius: 999px;
  background-color: rgb(var(--color-success-500) / 1);
}

.chip__remove {
  border-radius: 999px;
}

.chip__remove:hover {
  color: var(--color-text-primary);
}

/* ── Chip Rows (project filters) ── */
.chip-row {
  display: flex;
  width: 100%;
  align-items: flex-start;
  justify-content: space-between;
  gap: 0.5rem;
  border: 1px solid var(--color-border-soft);
  border-radius: 0.65rem;
  background-color: var(--color-bg-base-soft);
  padding: 0.375rem 0.5rem;
  font-size: 11px;
  font-weight: 600;
  color: var(--color-text-secondary);
}

.chip-row__content {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 0.12rem;
}

.chip-row__category {
  font-size: 12px;
  font-weight: 700;
  color: var(--color-text-primary);
  line-height: 1.3;
}

.chip-row__description {
  font-size: 10px;
  line-height: 1.35;
  color: var(--color-text-muted);
  word-break: break-word;
}

.project-filter-form {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1.35fr) auto;
  gap: 0.4rem;
  align-items: center;
}

.project-filter-input {
  width: 100%;
  border: 1px solid var(--color-border-soft);
  border-radius: 0.6rem;
  background-color: var(--color-bg-base-soft);
  padding: 0.4rem 0.55rem;
  font-size: 12px;
  line-height: 1.3;
}

.project-filter-input:focus {
  border-color: rgb(var(--color-brand-300) / 1);
  background-color: var(--color-surface);
  box-shadow: none;
}

.input-inline-shell {
  position: relative;
  display: flex;
  align-items: center;
  border: 1px solid var(--color-border-soft);
  border-radius: 0.6rem;
  background-color: var(--color-bg-base-soft);
  padding: 0.25rem 0.5rem;
}

.input-inline-shell:focus-within {
  border-color: rgb(var(--color-brand-300) / 1);
}

.project-filter-shell {
  background-color: rgb(var(--color-brand-100) / 0.18);
}

.project-filter-submit {
  min-width: 3.25rem;
  padding: 0.42rem 0.75rem;
  font-size: 12px;
  line-height: 1.2;
}

.project-filter-hint {
  margin-top: 0.35rem;
  padding-left: 0.25rem;
  font-size: 10px;
  color: var(--color-text-muted);
}

.project-filter-shell .text-danger {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 1.35rem;
  height: 1.35rem;
  border-radius: 999px;
  color: rgb(var(--color-danger-600) / 1);
  transition: background-color 0.2s ease, color 0.2s ease;
}

.project-filter-shell .text-danger:hover {
  background-color: rgb(var(--color-danger-100) / 1);
  color: rgb(var(--color-danger-700) / 1);
}

/* ── Result Badge ── */
.result-badge {
  display: flex;
  width: 3.5rem;
  height: 3.5rem;
  align-items: center;
  justify-content: center;
  border-radius: 999px;
  border: 1px solid rgb(var(--color-success-200) / 1);
  background-color: rgb(var(--color-success-100) / 0.9);
  color: rgb(var(--color-success-600) / 1);
}

@media (max-width: 1023px) {
  .workflow-summary {
    grid-template-columns: minmax(0, 1fr);
  }

  .workflow-summary__actions {
    justify-content: flex-start;
  }

  .project-filter-form {
    grid-template-columns: minmax(0, 1fr);
  }

  .project-filter-submit {
    justify-self: end;
  }
}

@media (max-width: 767px) {
  .dimension-explain-grid {
    grid-template-columns: minmax(0, 1fr);
  }

  .dimension-info-popover {
    right: -0.25rem;
  }

  .retry-annotation {
    position: static;
    transform: none;
    margin-top: 0.45rem;
    white-space: normal;
  }
}
</style>
