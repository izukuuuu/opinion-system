<template>
  <div class="bertopic-run pt-0 pb-12 space-y-6">
    <form class="space-y-6" @submit.prevent="handleRun">
      <!-- Main Configuration -->
      <section class="card-surface space-y-6 p-6">
        <div class="mb-6 flex items-center justify-between">
          <h2 class="text-lg font-semibold text-primary">新建分析任务</h2>
          <button type="button"
            class="flex items-center gap-1.5 text-xs font-medium text-brand-600 hover:text-brand-700 disabled:opacity-50 transition-colors"
            :disabled="topicsState.loading" @click="loadTopics(true)">
            <ArrowPathIcon class="h-3.5 w-3.5" :class="{ 'animate-spin': topicsState.loading }" />
            {{ topicsState.loading ? '同步中...' : '刷新专题列表' }}
          </button>
        </div>

        <div class="grid gap-6 md:grid-cols-2">
          <!-- Topic Selection -->
          <div class="space-y-2">
            <label class="text-xs font-bold text-muted uppercase tracking-wider">专题 Topic *</label>
            <div class="relative">
              <select v-model="form.topic" class="input w-full appearance-none pr-10"
                :disabled="topicsState.loading || topicOptions.length === 0" required>
                <option value="" disabled>请选择分析专题</option>
                <option v-for="option in topicOptions" :key="option.bucket" :value="option.bucket">
                  {{ option.display_name || option.name }}
                </option>
              </select>
              <div class="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-muted">
                <ChevronUpDownIcon class="h-4 w-4" />
              </div>
            </div>
          </div>

          <!-- Date Range -->
          <div class="grid grid-cols-2 gap-4">
            <div class="space-y-2">
              <label class="text-xs font-bold text-muted uppercase tracking-wider">开始日期 Start *</label>
              <input v-model.trim="form.startDate" type="date" class="input w-full" required
                :disabled="availableRange.loading" />
            </div>
            <div class="space-y-2">
              <label class="text-xs font-bold text-muted uppercase tracking-wider">结束日期 End</label>
              <input v-model.trim="form.endDate" type="date" class="input w-full" :disabled="availableRange.loading"
                :min="form.startDate" />
            </div>
          </div>
        </div>

        <!-- Data Availability Hint -->
        <div v-if="availableRange.start || availableRange.error" class="state-banner"
          :class="availableRange.error ? 'state-banner-danger' : 'state-banner-info'">
          <div class="flex items-start gap-3">
            <InformationCircleIcon v-if="!availableRange.error" class="h-5 w-5 shrink-0 state-banner__icon-info" />
            <ExclamationTriangleIcon v-else class="h-5 w-5 shrink-0 state-banner__icon-danger" />
            <div class="space-y-1">
              <p class="font-bold text-primary">数据可用性检查</p>
              <p class="text-xs opacity-90">
                {{ availableRange.error || `当前专题数据覆盖范围：${availableRange.start} ~ ${availableRange.end}` }}
              </p>
            </div>
          </div>
        </div>

        <div class="mt-8 flex items-center justify-between border-t border-soft pt-6">
          <div class="flex items-center gap-4">
            <button type="button"
              class="flex items-center gap-2 text-sm font-medium text-secondary hover:text-primary transition-colors"
              @click="showAdvancedSettings = !showAdvancedSettings">
              <AdjustmentsHorizontalIcon class="h-5 w-5" />
              <span>{{ showAdvancedSettings ? '隐藏高级设置' : '显示高级设置' }}</span>
            </button>
          </div>

          <div class="flex items-center gap-3">
            <button type="button" class="btn btn-ghost text-muted hover:text-primary" @click="resetAll"
              :disabled="runState.running">
              重置
            </button>
            <button type="submit" class="btn btn-primary min-w-[140px]" :disabled="!canSubmit">
              <span v-if="runState.running" class="flex items-center gap-2">
                <ArrowPathIcon class="h-4 w-4 animate-spin" />
                <span>分析中...</span>
              </span>
              <span v-else>开始分析</span>
            </button>
          </div>
        </div>
      </section>

      <!-- Advanced Configuration (Collapsible) -->
      <div v-show="showAdvancedSettings" class="space-y-6 animate-in slide-in-from-top-2 duration-200">

        <section class="card-surface p-6 space-y-5">
          <div class="flex items-start justify-between gap-3">
            <div class="space-y-1">
              <h3 class="text-sm font-bold text-primary flex items-center gap-2">
                <ChatBubbleLeftRightIcon class="h-4 w-4 text-muted" />
                <span>LLM 再聚类与 Drop 提示词</span>
              </h3>
              <p class="text-xs text-secondary">
                这里可以快速补充再聚类与 drop 判定信息；系统会自动注入到最终提示词并随专题保存。
              </p>
            </div>
            <div class="flex items-center gap-2 shrink-0">
              <button type="button" class="btn btn-ghost btn-sm whitespace-nowrap"
                :disabled="bertopicPromptState.loading" @click="loadBertopicPrompt(form.topic)">
                {{ bertopicPromptState.loading ? '加载中…' : '重载配置' }}
              </button>
              <button type="button" class="btn btn-secondary btn-sm whitespace-nowrap" :disabled="!canSavePrompt"
                @click="handleSavePrompt">
                {{ bertopicPromptState.saving ? '保存中…' : '保存修改' }}
              </button>
            </div>
          </div>

          <div class="grid gap-4 md:grid-cols-3">
            <label class="block">
              <span class="text-xs font-bold text-muted uppercase tracking-wider">最大主题数 Max Topics</span>
              <input v-model.number="bertopicPromptState.maxTopics" type="number" min="3" max="50"
                class="input w-full mt-1.5" />
              <span class="text-[11px] text-muted mt-1 block">AI 会自动推断合理的主题数量，此值为一级主题上限。</span>
            </label>
            <label class="block">
              <span class="text-xs font-bold text-muted uppercase tracking-wider">重分类输入上限</span>
              <input v-model.number="bertopicPromptState.reclusterTopicLimit" type="number" min="20" max="200"
                class="input w-full mt-1.5" />
              <span class="text-[11px] text-muted mt-1 block">送入 LLM 的 raw topics 上限，过低会导致覆盖不足。</span>
            </label>
            <label class="block">
              <span class="text-xs font-bold text-muted uppercase tracking-wider">目标覆盖率</span>
              <input v-model.number="bertopicPromptState.reclusterTargetCoverageRatio" type="number" min="0.2"
                max="0.95" step="0.01" class="input w-full mt-1.5" />
              <span class="text-[11px] text-muted mt-1 block">优先纳入高频主题，尽量覆盖更多文档再做汇总。</span>
            </label>
          </div>

          <!-- Dual-Mode Prompt Configuration -->
          <div class="mt-8 space-y-4 pt-2 animate-in slide-in-from-top-2 duration-200">

            <!-- Mode Switcher -->
            <div class="flex items-center justify-between">
              <h3 class="text-sm font-bold text-primary flex items-center gap-2">
                <SparklesIcon class="h-4 w-4 text-brand-600" />
                <span>AI 提炼业务规则</span>
              </h3>
              <div class="mode-switch">
                <button type="button" class="mode-switch__btn"
                  :class="promptMode === 'analyst' ? 'mode-switch__btn--active' : 'mode-switch__btn--idle'"
                  @click="promptMode = 'analyst'">
                  业务调整模式
                </button>
                <button type="button" class="mode-switch__btn mode-switch__btn--with-icon"
                  :class="promptMode === 'expert' ? 'mode-switch__btn--active' : 'mode-switch__btn--idle'"
                  @click="promptMode = 'expert'">
                  <CommandLineIcon class="h-3 w-3" />
                  专家指令引擎
                </button>
              </div>
            </div>

            <!-- Analyst Mode: Business Rules -->
            <div v-show="promptMode === 'analyst'"
              class="space-y-6 bg-brand-50/30 rounded-xl border border-brand-100/50 p-6 relative z-0">

              <!-- Dimension -->
              <div class="space-y-3">
                <div class="flex items-center justify-between gap-2">
                  <label class="text-xs font-bold text-primary flex items-center gap-2">
                    <ViewColumnsIcon class="h-4 w-4 text-brand-500" />
                    聚类主导视角
                  </label>
                  <div class="relative group">
                    <button type="button" class="dimension-info-trigger" aria-label="查看参数说明">
                      <InformationCircleIcon class="h-4 w-4" />
                    </button>
                    <div class="dimension-info-popover">
                      <p class="dimension-info-title">将追加到提示词的说明</p>
                      <div class="dimension-info-code">
                        {{ reclusterDimensionPromptHint }}
                      </div>
                    </div>
                  </div>
                </div>
                <p class="text-[11px] text-secondary">让 AI 根据哪种维度对文档进行最底层的划分。</p>
                <div class="flex flex-wrap items-center gap-2 mt-2">
                  <button type="button" v-for="dim in reclusterDimensionOptions" :key="dim.label" class="pill-btn"
                    :class="bertopicPromptState.reclusterDimension === dim.value
                      ? 'pill-btn--active'
                      : 'pill-btn--idle'" @click="bertopicPromptState.reclusterDimension = dim.value">
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

              <div class="grid gap-6 md:grid-cols-2">
                <!-- Must Separate -->
                <div class="space-y-3">
                  <label class="text-xs font-bold text-primary flex items-center gap-2">
                    <ArrowsPointingOutIcon class="h-4 w-4 text-accent-600" />
                    自定义识别主题
                  </label>
                  <p class="text-[11px] text-secondary">输入关键主题种子，语义相近内容会优先归入同一类，并进入后续命名环节。</p>
                  <div class="rule-input-shell">
                    <div class="flex flex-wrap gap-1.5 mb-2" v-if="bertopicPromptState.mustSeparateRules.length > 0">
                      <span v-for="(rule, idx) in bertopicPromptState.mustSeparateRules" :key="idx"
                        class="chip chip--accent">
                        {{ rule }}
                        <button type="button" @click="bertopicPromptState.mustSeparateRules.splice(idx, 1)"
                          class="chip__remove">
                          <XMarkIcon class="h-3 w-3" />
                        </button>
                      </span>
                    </div>
                    <input type="text" v-model="draftSeparateRule" @keyup.enter="addRule('separate')"
                      class="w-full text-xs border-none bg-transparent focus:ring-0 p-1 placeholder:text-muted"
                      placeholder="输入关键主题（如：戒烟政策执行），按回车添加..." />
                  </div>
                </div>

                <!-- Must Merge -->
                <div class="space-y-3">
                  <label class="text-xs font-bold text-primary flex items-center gap-2">
                    <ArrowsPointingInIcon class="h-4 w-4 text-success-600" />
                    重点合并专题
                  </label>
                  <p class="text-[11px] text-secondary">高度相关的冗余子主题，提示 AI 尽可能合并。</p>
                  <div class="rule-input-shell">
                    <div class="flex flex-wrap gap-1.5 mb-2" v-if="bertopicPromptState.mustMergeRules.length > 0">
                      <span v-for="(rule, idx) in bertopicPromptState.mustMergeRules" :key="idx"
                        class="chip chip--success">
                        {{ rule }}
                        <button type="button" @click="bertopicPromptState.mustMergeRules.splice(idx, 1)"
                          class="chip__remove">
                          <XMarkIcon class="h-3 w-3" />
                        </button>
                      </span>
                    </div>
                    <input type="text" v-model="draftMergeRule" @keyup.enter="addRule('merge')"
                      class="w-full text-xs border-none bg-transparent focus:ring-0 p-1 placeholder:text-muted"
                      placeholder="输入内容特征，按回车添加..." />
                  </div>
                </div>
              </div>

              <!-- Noise Filters Unit -->
              <div class="space-y-6 border-t border-brand-100/50 pt-6 mt-6">
                <div class="flex items-center gap-2 mb-2">
                  <ShieldExclamationIcon class="h-5 w-5 text-danger-500" />
                  <h4 class="text-sm font-bold text-primary">噪声清洗与过滤</h4>
                </div>

                <div class="grid gap-4 lg:grid-cols-2">
                  <!-- Global Filters Toggle -->
                  <div class="space-y-3 rounded-2xl border border-soft bg-surface/70 p-4">
                    <label class="text-xs font-bold text-primary flex items-center gap-2">
                      <GlobeAltIcon class="h-4 w-4 text-secondary/70" />
                      全局通用屏蔽
                    </label>
                    <p class="text-[11px] text-secondary leading-relaxed">系统内置的常态化噪声，适用于绝大多数分析场景。</p>

                    <div class="noise-card">
                      <div v-for="gf in ['明星八卦', '广告推广', '抽奖转发', '求职招聘']" :key="gf" class="global-filter-row">
                        <span class="text-xs font-semibold text-primary">{{ gf }}</span>
                        <button type="button" class="switch-track"
                          :class="bertopicPromptState.globalFilters.includes(gf) ? 'switch-track--on' : 'switch-track--off'"
                          @click="toggleGlobalFilter(gf)">
                          <span class="sr-only">Toggle Global Filter</span>
                          <span aria-hidden="true" class="switch-thumb"
                            :class="bertopicPromptState.globalFilters.includes(gf) ? 'switch-thumb--on' : 'switch-thumb--off'" />
                        </button>
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
                          :disabled="!newFilterCategory">
                          添加
                        </button>
                      </div>
                      <p class="project-filter-hint">可在任一输入框按回车添加</p>
                    </div>
                  </div>
                </div>

                <!-- Contextual Relevance Rules -->
                <div class="space-y-3 pt-3">
                  <label class="text-xs font-bold text-primary flex items-center gap-2">
                    <AdjustmentsHorizontalIcon class="h-4 w-4 text-success-600" />
                    相关性补充指令
                  </label>
                  <p class="text-[11px] text-secondary leading-relaxed">非纯净类别的细粒度甄别（例如：“如果是提及品牌但作为负面竞品对比，一律剔除”）。</p>
                  <div class="rule-input-shell">
                    <div class="flex flex-col gap-1.5 mb-2" v-if="bertopicPromptState.coreDropRules.length > 0">
                      <span v-for="(rule, idx) in bertopicPromptState.coreDropRules" :key="idx"
                        class="chip chip--success-strong">
                        <div class="chip-dot"></div>
                        <span class="flex-1 leading-relaxed">{{ rule }}</span>
                        <button type="button" @click="bertopicPromptState.coreDropRules.splice(idx, 1)"
                          class="chip__remove p-0.5 self-center shrink-0">
                          <XMarkIcon class="h-3.5 w-3.5" />
                        </button>
                      </span>
                    </div>
                    <input type="text" v-model="draftDropRule" @keyup.enter="addRule('drop')"
                      class="w-full text-[11px] border-none bg-transparent focus:ring-0 px-2 py-1 placeholder:text-muted"
                      placeholder="输入相关性甄别条件，按回车添加..." />
                  </div>
                </div>

              </div>
            </div>

            <!-- Expert Mode: Raw Prompts Tabbed -->
            <div v-show="promptMode === 'expert'" class="space-y-4 animate-in fade-in duration-200">
              <div class="state-note state-note-accent">
                <InformationCircleIcon class="h-4 w-4 inline mr-1 -mt-0.5" />
                此时您查看到的是底层大模型真实运作所需的提示模板。<strong>业务调整模式</strong> 中配置的各项规则，最终会被 AI 引擎作为补充段落动态拼接到以下 User Prompt 中。
              </div>

              <!-- Tabs -->
              <div class="flex items-center gap-1 border-b border-soft pb-px relative z-10">
                <button type="button"
                  class="px-4 py-2.5 text-sm font-medium border-b-2 transition-colors flex items-center gap-2 -mb-px"
                  :class="activePromptTab === 'recluster' ? 'border-brand-500 text-brand-600' : 'border-transparent text-secondary hover:text-primary hover:border-soft'"
                  @click="activePromptTab = 'recluster'">
                  <ChatBubbleLeftRightIcon class="h-4 w-4" />
                  再聚类指令
                </button>
                <button type="button"
                  class="px-4 py-2.5 text-sm font-medium border-b-2 transition-colors flex items-center gap-2 -mb-px"
                  :class="activePromptTab === 'keyword' ? 'border-brand-500 text-brand-600' : 'border-transparent text-secondary hover:text-primary hover:border-soft'"
                  @click="activePromptTab = 'keyword'">
                  <DocumentTextIcon class="h-4 w-4" />
                  关键词提取
                </button>
                <button type="button"
                  class="px-4 py-2.5 text-sm font-medium border-b-2 transition-colors flex items-center gap-2 -mb-px"
                  :class="activePromptTab === 'drop' ? 'border-brand-500 text-brand-600' : 'border-transparent text-secondary hover:text-primary hover:border-soft'"
                  @click="activePromptTab = 'drop'">
                  <ShieldExclamationIcon class="h-4 w-4" />
                  噪声清洗属性
                </button>
              </div>

              <!-- Tab Contents -->
              <div class="bg-surface-muted/30 rounded-xl border border-soft p-5 relative z-0">

                <!-- Recluster Tab -->
                <div v-show="activePromptTab === 'recluster'" class="space-y-4 animate-in fade-in py-1">
                  <div class="space-y-4">
                    <label class="block">
                      <span class="text-[11px] font-bold text-muted uppercase tracking-wider">System Prompt (可选)</span>
                      <textarea v-model="bertopicPromptState.reclusterSystemPrompt" rows="2"
                        class="input run-textarea w-full mt-1.5 resize-y font-mono text-xs leading-relaxed" />
                    </label>
                    <label class="block">
                      <span class="text-[11px] font-bold text-muted uppercase tracking-wider">User Prompt 主体 *</span>
                      <textarea v-model="bertopicPromptState.reclusterUserPrompt" rows="10"
                        class="input run-textarea w-full mt-1.5 resize-y font-mono text-xs leading-relaxed" />
                    </label>
                  </div>
                  <div
                    class="bg-brand-50/50 rounded-lg p-3 border border-brand-100/50 text-[11px] text-brand-700/80 space-y-1">
                    <p class="font-semibold text-brand-700">可用变量：</p>
                    <p class="font-mono">{TARGET_TOPICS}, {input_data}, {topic_list}, {business_rules_hint},
                      {iteration_hint}</p>
                  </div>
                </div>

                <!-- Keyword Tab -->
                <div v-show="activePromptTab === 'keyword'" class="space-y-4 animate-in fade-in py-1">
                  <div class="space-y-4">
                    <label class="block">
                      <span class="text-[11px] font-bold text-muted uppercase tracking-wider">关键词 System Prompt
                        (可选)</span>
                      <textarea v-model="bertopicPromptState.keywordSystemPrompt" rows="2"
                        class="input run-textarea w-full mt-1.5 resize-y font-mono text-xs leading-relaxed" />
                    </label>
                    <label class="block">
                      <span class="text-[11px] font-bold text-muted uppercase tracking-wider">关键词 User Prompt *</span>
                      <textarea v-model="bertopicPromptState.keywordUserPrompt" rows="8"
                        class="input run-textarea w-full mt-1.5 resize-y font-mono text-xs leading-relaxed" />
                    </label>
                  </div>
                  <div
                    class="bg-brand-50/50 rounded-lg p-3 border border-brand-100/50 text-[11px] text-brand-700/80 space-y-1">
                    <p class="font-semibold text-brand-700">可用变量：</p>
                    <p class="font-mono">{cluster_name}, {topics}, {topics_csv}, {topics_json}, {description}</p>
                  </div>
                </div>

                <!-- Drop Rule Tab -->
                <div v-show="activePromptTab === 'drop'" class="space-y-4 animate-in fade-in py-1">
                  <div class="flex items-start justify-between gap-4">
                    <div class="space-y-1">
                      <p class="text-xs text-secondary">在此设置模型判断是否丢弃主题的基础参数约定。核心降噪指令会拼接于此上方。</p>
                    </div>
                    <button type="button" class="btn-secondary px-3 py-1.5 text-xs"
                      @click="restoreDefaultDropRulePrompt">
                      恢复通用模板
                    </button>
                  </div>
                  <div class="space-y-4">
                    <label class="block">
                      <span class="text-[11px] font-bold text-muted uppercase tracking-wider">基础判定规则 *</span>
                      <textarea v-model="bertopicPromptState.dropRulePrompt" rows="12"
                        class="input run-textarea w-full mt-1.5 resize-y font-mono text-xs leading-relaxed" />
                    </label>
                  </div>
                  <div
                    class="bg-brand-50/50 rounded-lg p-3 border border-brand-100/50 text-[11px] text-brand-700/80 space-y-1">
                    <p class="font-semibold text-brand-700">可用变量：</p>
                    <p class="font-mono">{FOCUS_TOPIC}</p>
                  </div>
                </div>

              </div>
            </div>
          </div>

          <div v-if="bertopicPromptState.error || bertopicPromptState.message" class="state-banner text-xs"
            :class="bertopicPromptState.error ? 'state-banner-danger' : 'state-banner-success'">
            {{ bertopicPromptState.error || bertopicPromptState.message }}
          </div>
        </section>

        <section class="card-surface p-6 space-y-4">
          <div class="flex items-start justify-between gap-3">
            <div class="space-y-1">
              <h3 class="text-sm font-bold text-primary flex items-center gap-2">
                <DocumentTextIcon class="h-4 w-4 text-muted" />
                <span>项目停用词配置</span>
              </h3>
              <p class="text-xs text-secondary">
                仅对当前专题生效，会和全局 `configs/stopwords.txt` 合并后一起参与 BERTopic 分词。
              </p>
            </div>
            <div class="flex items-center gap-2 shrink-0">
              <button type="button" class="btn btn-ghost btn-sm whitespace-nowrap"
                :disabled="bertopicPromptState.loading || !form.topic.trim()" @click="loadBertopicPrompt(form.topic)">
                {{ bertopicPromptState.loading ? '加载中…' : '重载配置' }}
              </button>
              <button type="button" class="btn btn-secondary btn-sm whitespace-nowrap" :disabled="!canSavePrompt"
                @click="handleSavePrompt">
                {{ bertopicPromptState.saving ? '保存中…' : '保存项目停用词' }}
              </button>
            </div>
          </div>

          <div class="rounded-xl border border-amber-200/60 bg-amber-50/70 p-4 text-sm text-amber-900">
            <p class="font-semibold">编辑说明</p>
            <p class="mt-1 leading-6">
              一行一个停用词。这里保存的是当前专题的局部停用词，不会影响其他项目；运行时会自动与全局停用词去重合并。
            </p>
          </div>

          <div class="flex flex-wrap items-center gap-4 text-xs text-secondary">
            <span>配置文件：{{ bertopicPromptState.path || 'configs/prompt/topic_bertopic/<topic>.yaml' }}</span>
            <span>存储字段：settings.project_stopwords</span>
            <span>当前行数：{{ projectStopwordCount }}</span>
          </div>

          <textarea v-model="bertopicPromptState.projectStopwordsText" rows="12"
            class="input min-h-[320px] w-full resize-y font-mono text-sm leading-6" placeholder="一行一个项目停用词" />
        </section>

        <section class="card-surface p-6 space-y-4">
          <div class="space-y-1">
            <h3 class="text-sm font-bold text-primary flex items-center gap-2">
              <FunnelIcon class="h-4 w-4 text-muted" />
              <span>专题相关性预过滤</span>
            </h3>
            <p class="text-xs text-secondary">
              在 BERTopic 前先用嵌入相似度过滤明显离题文档，减少噪声混入。
            </p>
          </div>

          <div class="grid gap-4 lg:grid-cols-4">
            <label class="runtime-field">
              <span class="runtime-field-label">启用预过滤</span>
              <span class="runtime-field-key">pre_filter_enabled</span>
              <div class="runtime-toggle-row">
                <input v-model="bertopicPromptState.preFilterEnabled" type="checkbox" class="checkbox-custom" />
                <span class="runtime-toggle-text">启用</span>
              </div>
            </label>
            <label class="runtime-field">
              <span class="runtime-field-label">最低相似度</span>
              <span class="runtime-field-key">similarity_floor</span>
              <input v-model.number="bertopicPromptState.preFilterSimilarityFloor" type="number" min="0" max="0.95"
                step="0.01" class="input runtime-input w-full" />
            </label>
            <label class="runtime-field">
              <span class="runtime-field-label">最大丢弃比例</span>
              <span class="runtime-field-key">max_drop_ratio</span>
              <input v-model.number="bertopicPromptState.preFilterMaxDropRatio" type="number" min="0" max="0.9"
                step="0.01" class="input runtime-input w-full" />
            </label>
            <div class="rounded-2xl border border-soft bg-surface/60 px-4 py-3 text-[11px] text-secondary leading-5">
              <p>推荐起点：`0.24 / 0.35`。</p>
              <p>如果误杀相关文本，先降低最低相似度；如果噪声仍多，再提高相似度或收紧丢弃比例。</p>
            </div>
          </div>

          <label class="block">
            <span class="text-[11px] font-bold text-muted uppercase tracking-wider">查询增强词</span>
            <textarea v-model="bertopicPromptState.preFilterQueryHint" rows="3"
              class="input run-textarea w-full mt-1.5 resize-y text-xs leading-relaxed"
              placeholder="可补充专题锚点，例如：吸烟、戒烟、控烟政策、二手烟、无烟环境、烟草监管" />
          </label>

          <label class="block">
            <span class="text-[11px] font-bold text-muted uppercase tracking-wider">排除词 / 负向约束</span>
            <textarea v-model="bertopicPromptState.preFilterNegativeHint" rows="3"
              class="input run-textarea w-full mt-1.5 resize-y text-xs leading-relaxed"
              placeholder="命中这些词且未命中专题锚点时会优先剔除" />
          </label>
        </section>

        <!-- Runtime Parameters -->
        <section class="runtime-compact card-surface p-4 md:p-5">
          <div class="mb-3 flex items-center justify-between">
            <h3 class="flex items-center gap-2 text-sm font-bold text-primary">
              <CpuChipIcon class="h-4 w-4 text-muted" />
              <span>算法参数配置</span>
            </h3>
            <button type="button" class="text-xs text-brand-600 hover:text-brand-700" @click="resetRunParams"
              :disabled="runState.running">
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
                  <select v-model="form.runParams.umap.metric" class="input runtime-input w-full">
                    <option value="cosine">cosine</option>
                    <option value="euclidean">euclidean</option>
                    <option value="manhattan">manhattan</option>
                  </select>
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
                  <select v-model="form.runParams.hdbscan.metric" class="input runtime-input w-full">
                    <option value="euclidean">euclidean</option>
                    <option value="manhattan">manhattan</option>
                    <option value="cosine">cosine</option>
                  </select>
                </label>
                <label class="runtime-field">
                  <span class="runtime-field-label">簇选择算法</span>
                  <span class="runtime-field-key">selection_method</span>
                  <select v-model="form.runParams.hdbscan.cluster_selection_method" class="input runtime-input w-full">
                    <option value="eom">eom (叶节点过多时合并)</option>
                    <option value="leaf">leaf (保留所有叶节点)</option>
                  </select>
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
                    <input v-model="form.runParams.bertopic.calculate_probabilities" type="checkbox"
                      class="checkbox-custom" />
                    <span class="runtime-toggle-text">启用</span>
                  </div>
                </label>
                <label class="runtime-field">
                  <span class="runtime-field-label">输出详细日志</span>
                  <span class="runtime-field-key">verbose</span>
                  <div class="runtime-toggle-row">
                    <input v-model="form.runParams.bertopic.verbose" type="checkbox" class="checkbox-custom" />
                    <span class="runtime-toggle-text">启用</span>
                  </div>
                </label>
              </div>
            </div>
          </div>
        </section>

      </div>

      <!-- Logs -->
      <section v-if="logs.length > 0" class="card-surface p-6">
        <h3 class="text-sm font-bold text-muted uppercase tracking-widest mb-4">运行日志</h3>
        <AnalysisLogList :logs="logs" class="max-h-[300px] overflow-y-auto" empty-label="等待执行..." />
      </section>

      <!-- Failure Warning -->
      <section v-if="logs.some(log => log.status === 'error')"
        class="state-banner state-banner-danger animate-in slide-in-from-top-1">
        <div class="flex items-start gap-3">
          <ExclamationCircleIcon class="h-6 w-6 shrink-0" />
          <div>
            <p class="font-bold">任务执行中断</p>
            <p class="text-sm mt-1">{{logs.find(log => log.status === 'error')?.message || '发生未知错误'}}</p>
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
import { computed, watch, onMounted, ref } from 'vue'
import {
  ArrowPathIcon,
  ChevronUpDownIcon,
  CheckBadgeIcon,
  InformationCircleIcon,
  SparklesIcon,
  ViewColumnsIcon,
  CommandLineIcon,
  ArrowsPointingInIcon,
  ArrowsPointingOutIcon,
  ArchiveBoxXMarkIcon,
  XMarkIcon,
  ExclamationTriangleIcon,
  ExclamationCircleIcon,
  AdjustmentsHorizontalIcon,
  DocumentTextIcon,
  ShieldExclamationIcon,
  ArrowRightIcon,
  CpuChipIcon,
  ChatBubbleLeftRightIcon,
  FunnelIcon,
  XCircleIcon,
  TrashIcon,
  FolderOpenIcon,
  GlobeAltIcon
} from '@heroicons/vue/24/outline'
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
const activePromptTab = ref('recluster')
const promptMode = ref('analyst') // 'analyst' vs 'expert'

const draftSeparateRule = ref('')
const draftMergeRule = ref('')
const draftDropRule = ref('')

const showAdvancedSettings = ref(false)
const newFilterCategory = ref('')
const newFilterDescription = ref('')

const reclusterDimensionOptions = [
  {
    label: '默认 (综合语义)',
    value: '',
    description: '按整体语义自动归类，不强制单一分析维度，适合首次探索。'
  },
  {
    label: '业务场景',
    value: '业务场景',
    description: '优先按使用场景、业务流程或问题上下文进行分组。'
  },
  {
    label: '情感倾向',
    value: '情感倾向',
    description: '优先按正向、负向、中性等情绪态度进行聚类。'
  },
  {
    label: '对象实体',
    value: '对象实体',
    description: '优先按人物、机构、品牌、产品等被讨论对象进行划分。'
  }
]

const reclusterDimensionGuides = {
  业务场景: [
    '优先按业务链路阶段、用户诉求场景、问题处理环节进行一级分组。',
    '同一组需要能解释为同一业务情境下的同类问题或动作。',
    '若语义接近但业务动作不同，应拆分为不同类别。'
  ],
  情感倾向: [
    '优先按情绪极性与立场方向分组（正向/负向/中性/争议）。',
    '同组内情绪基调应一致，不要把对立情绪合并。',
    '事实陈述类内容需先判断语气倾向再归类。'
  ],
  对象实体: [
    '优先按被讨论对象分组（品牌/机构/人物/产品/渠道）。',
    '不同对象即使议题接近，也优先分开。',
    '对象指代不明时，先根据上下文补全主实体再聚类。'
  ]
}

const yamlQuote = (value) => {
  return `"${String(value ?? '').replace(/\\/g, '\\\\').replace(/"/g, '\\"')}"`
}

const reclusterDimensionPromptHint = computed(() => {
  const value = String(bertopicPromptState.reclusterDimension || '').trim()
  const seedTopics = (bertopicPromptState.mustSeparateRules || [])
    .map(item => String(item || '').trim())
    .filter(Boolean)
  const mergeHints = (bertopicPromptState.mustMergeRules || [])
    .map(item => String(item || '').trim())
    .filter(Boolean)

  if (!value && seedTopics.length === 0 && mergeHints.length === 0) {
    return '当前未配置业务规则，不会追加 business_rules 提示块。'
  }

  const lines = ['business_rules:']
  if (value) {
    const guides = reclusterDimensionGuides[value] || [
      '请先按该视角完成一级分组，再在组内做语义细分。',
      '同组需具备一致且可解释的共同特征，不可仅按表层关键词合并。',
      '类别命名需体现该视角，避免泛化命名。'
    ]
    lines.push(
      '  recluster_strategy:',
      `    perspective: ${yamlQuote(value)}`,
      '    objective: "先按主导视角完成一级聚类，再在组内做语义细分与命名。"',
      '    guide:',
      ...guides.map(item => `      - ${yamlQuote(item)}`)
    )
  }

  if (seedTopics.length > 0) {
    lines.push('  custom_topic_recognition:', '    seed_topics:')
    seedTopics.forEach(item => {
      lines.push(`      - ${yamlQuote(item)}`)
    })
    lines.push(
      '    assignment_rule:',
      '      - "与 seed_topics 语义高度相近的原始主题，优先归入同一类别。"',
      '      - "该类别与其他聚类流程一致，需进入后续命名与关键词生成阶段。"',
      '      - "若同时命中多个 seed_topics，按语义最贴近者归类并在描述中体现边界。"'
    )
  }

  if (mergeHints.length > 0) {
    lines.push('  should_merge:')
    mergeHints.forEach(item => {
      lines.push(`    - ${yamlQuote(item)}`)
    })
  }

  lines.push(
    '  execution_requirements:',
    '    - "优先保证组内语义一致性，再控制组间边界清晰。"',
    '    - "custom_topic_recognition.seed_topics 仅定义归类锚点，不直接作为最终类别名。"',
    '    - "与 should_merge 冲突时，优先满足 seed_topics 的归类锚定。"',
    '    - "输出类别命名需可解释，并与主导视角保持一致。"'
  )
  return lines.join('\n')
})

const splitProjectFilterText = (text = '') => {
  const raw = String(text || '').trim()
  if (!raw) return { category: '', description: '' }
  const parts = raw
    .split(/\s*[\/／|｜]\s*/g)
    .map(part => part.trim())
    .filter(Boolean)
  if (parts.length <= 1) {
    return { category: raw, description: '' }
  }
  return {
    category: parts[0],
    description: parts.slice(1).join(' / ')
  }
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
  if (parsed.category !== rawCategory && parsed.description) {
    return parsed.description
  }
  return ''
}

const toggleGlobalFilter = (gf) => {
  const idx = bertopicPromptState.globalFilters.indexOf(gf)
  if (idx === -1) {
    bertopicPromptState.globalFilters.push(gf)
  } else {
    bertopicPromptState.globalFilters.splice(idx, 1)
  }
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

  const exists = bertopicPromptState.projectFilters.some((item) => {
    const itemCategory = String(item?.category || '').trim()
    const itemDescription = String(item?.description || '').trim()
    return itemCategory === category && itemDescription === description
  })
  if (exists) {
    newFilterCategory.value = ''
    newFilterDescription.value = ''
    return
  }

  bertopicPromptState.projectFilters.push({
    category,
    description
  })
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
    if (val && !bertopicPromptState.mustSeparateRules.includes(val)) {
      bertopicPromptState.mustSeparateRules.push(val)
    }
    draftSeparateRule.value = ''
  } else if (type === 'merge') {
    const val = draftMergeRule.value.trim()
    if (val && !bertopicPromptState.mustMergeRules.includes(val)) {
      bertopicPromptState.mustMergeRules.push(val)
    }
    draftMergeRule.value = ''
  } else if (type === 'drop') {
    const val = draftDropRule.value.trim()
    if (val && !bertopicPromptState.coreDropRules.includes(val)) {
      bertopicPromptState.coreDropRules.push(val)
    }
    draftDropRule.value = ''
  }
}

onMounted(() => {
  loadTopics(true)
})

watch(
  activeProjectName,
  (value) => {
    if (!value) return
    form.project = value
    if (!form.topic) {
      const matched = topicOptions.value.find(t =>
        t.name === value || t.display_name === value || t.bucket === value
      )
      if (matched) {
        form.topic = matched.bucket
      }
    }
    if (form.topic) {
      loadBertopicPrompt(form.topic)
    }
  },
  { immediate: true }
)

const canSavePrompt = computed(() => {
  return Boolean(
    form.topic.trim() &&
    !bertopicPromptState.loading &&
    !bertopicPromptState.saving
  )
})

const projectStopwordCount = computed(() => {
  return String(bertopicPromptState.projectStopwordsText || '')
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
    .length
})

const canSubmit = computed(() => {
  return Boolean(
    form.topic.trim() &&
    form.startDate.trim() &&
    !runState.running &&
    !availableRange.loading &&
    !bertopicPromptState.saving &&
    !bertopicPromptState.loading
  )
})



const resetAll = () => {
  form.startDate = ''
  form.endDate = ''
  resetState()
}

const handleRun = async () => {
  try {
    if (hasPromptDraftChanges.value) {
      await saveBertopicPrompt({ topic: form.topic })
    }

    await runBertopicAnalysis({
      topic: form.topic,
      startDate: form.startDate,
      endDate: form.endDate
    })
  } catch {
    // 错误处理已在日志组件体现
  }
}

const handleSavePrompt = async () => {
  try {
    await saveBertopicPrompt({ topic: form.topic })
  } catch {
    // 错误提示由状态区域显示
  }
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

.bertopic-run :deep(.checkbox-custom) {
  position: relative;
  display: inline-grid;
  place-items: center;
  border-color: var(--color-border-soft);
  background-color: var(--color-surface);
}

.bertopic-run :deep(.checkbox-custom::after) {
  content: '';
  width: 0.45rem;
  height: 0.25rem;
  border-left: 2px solid var(--color-surface);
  border-bottom: 2px solid var(--color-surface);
  transform: rotate(-45deg) scale(0);
  transform-origin: center;
  transition: transform 0.15s ease;
}

.bertopic-run :deep(.checkbox-custom:checked::after) {
  transform: rotate(-45deg) scale(1);
}

.run-textarea {
  line-height: 1.55;
}

.runtime-compact .runtime-group-title {
  margin-bottom: 0.4rem;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--color-text-muted);
}

.runtime-compact .runtime-field {
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
}

.runtime-compact .runtime-field-label {
  display: block;
  font-size: 12px;
  font-weight: 600;
  line-height: 1.2;
  color: var(--color-text-primary);
}

.runtime-compact .runtime-field-key {
  display: block;
  font-size: 10px;
  line-height: 1.2;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  color: var(--color-text-muted);
}

.runtime-compact :deep(.runtime-input) {
  min-height: 2.05rem;
  padding: 0.4rem 0.8rem;
  border-radius: 0.875rem;
  font-size: 0.82rem;
}

.runtime-compact .runtime-toggle-row {
  display: flex;
  align-items: center;
  gap: 0.45rem;
  padding-top: 0.15rem;
}

.runtime-compact .runtime-toggle-text {
  font-size: 0.75rem;
  color: var(--color-text-secondary);
}

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

.state-note {
  border-width: 1px;
  border-style: solid;
  border-radius: 0.75rem;
  padding: 0.75rem;
  font-size: 11px;
}

.state-note-accent {
  border-color: rgb(var(--color-accent-200) / 1);
  background-color: rgb(var(--color-accent-50) / 0.75);
  color: rgb(var(--color-accent-700) / 1);
}

.mode-switch {
  display: flex;
  align-items: center;
  border: 1px solid var(--color-border-soft);
  border-radius: 0.75rem;
  background-color: rgb(var(--color-brand-100) / 0.4);
  padding: 0.25rem;
}

.mode-switch__btn {
  border: 1px solid transparent;
  border-radius: 0.5rem;
  padding: 0.375rem 0.75rem;
  color: var(--color-text-secondary);
  font-size: 0.75rem;
  font-weight: 600;
  transition: background-color 0.2s ease, color 0.2s ease, border-color 0.2s ease;
}

.mode-switch__btn--with-icon {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
}

.mode-switch__btn--active {
  border-color: rgb(var(--color-brand-200) / 1);
  background-color: var(--color-surface);
  color: rgb(var(--color-brand-700) / 1);
}

.mode-switch__btn--idle:hover {
  color: var(--color-text-primary);
  background-color: rgb(var(--color-brand-100) / 0.3);
}

.pill-btn {
  border: 1px solid var(--color-border-soft);
  border-radius: 999px;
  padding: 0.375rem 0.75rem;
  font-size: 0.75rem;
  font-weight: 600;
  transition: border-color 0.2s ease, color 0.2s ease, background-color 0.2s ease;
}

.pill-btn--active {
  border-color: rgb(var(--color-brand-600) / 1);
  background-color: rgb(var(--color-brand-500) / 1);
  color: var(--color-surface);
}

.pill-btn--idle {
  background-color: var(--color-surface);
  color: var(--color-text-secondary);
}

.pill-btn--idle:hover {
  border-color: rgb(var(--color-brand-300) / 1);
  color: rgb(var(--color-brand-600) / 1);
}

.dimension-info-trigger {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 1.5rem;
  height: 1.5rem;
  border: 1px solid var(--color-border-soft);
  border-radius: 999px;
  color: var(--color-text-muted);
  background-color: var(--color-surface);
  transition: color 0.2s ease, border-color 0.2s ease, background-color 0.2s ease;
}

.dimension-info-trigger:hover,
.group:focus-within .dimension-info-trigger {
  color: rgb(var(--color-brand-600) / 1);
  border-color: rgb(var(--color-brand-300) / 1);
  background-color: rgb(var(--color-brand-100) / 0.35);
}

.dimension-info-popover {
  position: absolute;
  top: calc(100% + 0.5rem);
  right: 0;
  width: 22rem;
  max-width: 85vw;
  border: 1px solid var(--color-border-soft);
  border-radius: 0.75rem;
  background-color: var(--color-surface);
  padding: 0.75rem;
  opacity: 0;
  pointer-events: none;
  transform: translateY(-4px);
  transition: opacity 0.2s ease, transform 0.2s ease;
  z-index: 30;
}

.group:hover .dimension-info-popover,
.group:focus-within .dimension-info-popover {
  opacity: 1;
  pointer-events: auto;
  transform: translateY(0);
}

.dimension-info-title {
  font-size: 0.75rem;
  font-weight: 700;
  color: var(--color-text-primary);
  margin-bottom: 0.375rem;
}

.dimension-info-line {
  font-size: 11px;
  line-height: 1.45;
  color: var(--color-text-secondary);
}

.dimension-info-code {
  margin-top: 0.45rem;
  padding: 0.5rem;
  border-radius: 0.5rem;
  border: 1px solid rgb(var(--color-brand-200) / 1);
  background-color: rgb(var(--color-brand-100) / 0.35);
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
  border-radius: 0.75rem;
  background-color: rgb(var(--color-brand-100) / 0.18);
  padding: 0.55rem 0.65rem;
}

.dimension-explain-item--active {
  border-color: rgb(var(--color-brand-300) / 1);
  background-color: rgb(var(--color-brand-100) / 0.45);
}

.dimension-explain-title {
  font-size: 11px;
  font-weight: 700;
  color: var(--color-text-primary);
}

.dimension-explain-text {
  margin-top: 0.2rem;
  font-size: 10px;
  line-height: 1.45;
  color: var(--color-text-secondary);
}

@media (max-width: 767px) {
  .dimension-explain-grid {
    grid-template-columns: minmax(0, 1fr);
  }

  .dimension-info-popover {
    right: -0.25rem;
  }
}

.rule-input-shell {
  border: 1px solid var(--color-border-soft);
  border-radius: 0.75rem;
  background-color: var(--color-surface);
  padding: 0.5rem;
  transition: border-color 0.2s ease, box-shadow 0.2s ease;
}

.rule-input-shell:focus-within {
  border-color: rgb(var(--color-brand-400) / 1);
  box-shadow: 0 0 0 2px rgb(var(--color-brand-500) / 0.16);
}

.noise-card {
  border: 1px solid var(--color-border-soft);
  border-radius: 0.875rem;
  background-color: rgb(var(--color-brand-100) / 0.2);
  overflow: hidden;
}

.global-filter-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  padding: 0.7rem 0.875rem;
}

.global-filter-row+.global-filter-row {
  border-top: 1px solid var(--color-border-soft);
}

.chip {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  border-width: 1px;
  border-style: solid;
  border-radius: 0.5rem;
  padding: 0.25rem 0.5rem;
  font-size: 11px;
  font-weight: 600;
}

.chip--accent {
  border-color: rgb(var(--color-accent-200) / 1);
  background-color: rgb(var(--color-accent-50) / 1);
  color: rgb(var(--color-accent-700) / 1);
}

.chip--success {
  border-color: rgb(var(--color-success-200) / 1);
  background-color: rgb(var(--color-success-50) / 1);
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
  border-radius: 999px;
  margin-top: 0.25rem;
  flex-shrink: 0;
  background-color: rgb(var(--color-success-500) / 1);
}

.chip__remove {
  border-radius: 999px;
}

.chip__remove:hover {
  color: var(--color-text-primary);
}

.switch-track {
  position: relative;
  display: inline-flex;
  width: 2.1rem;
  height: 1.18rem;
  flex-shrink: 0;
  cursor: pointer;
  align-items: center;
  border-radius: 999px;
  border: 1px solid var(--color-border-soft);
  transition: background-color 0.2s ease;
}

.switch-track:focus-visible {
  outline: 2px solid rgb(var(--color-brand-500) / 0.35);
  outline-offset: 2px;
}

.switch-track--on {
  background-color: rgb(var(--color-brand-500) / 1);
  border-color: rgb(var(--color-brand-500) / 1);
}

.switch-track--off {
  background-color: var(--color-surface-muted);
}

.switch-thumb {
  position: absolute;
  left: 0.14rem;
  top: 50%;
  width: 0.9rem;
  height: 0.9rem;
  border-radius: 999px;
  background-color: var(--color-surface);
  border: 1px solid rgb(var(--color-brand-100) / 1);
  transition: transform 0.2s ease;
}

.switch-thumb--off {
  transform: translate3d(0, -50%, 0);
}

.switch-thumb--on {
  transform: translate3d(1.06rem, -50%, 0);
}

.chip-row {
  display: flex;
  width: 100%;
  align-items: flex-start;
  justify-content: space-between;
  gap: 0.5rem;
  border: 1px solid var(--color-border-soft);
  border-radius: 0.5rem;
  background-color: var(--color-bg-base-soft);
  color: var(--color-text-secondary);
  padding: 0.375rem 0.5rem;
  font-size: 11px;
  font-weight: 600;
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
  color: var(--color-text-muted);
  line-height: 1.35;
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
  border-radius: 0.5rem;
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
  border-radius: 0.5rem;
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

@media (max-width: 1023px) {
  .project-filter-form {
    grid-template-columns: minmax(0, 1fr);
  }

  .project-filter-submit {
    justify-self: end;
  }
}

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
</style>
