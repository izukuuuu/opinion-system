<template>
  <div class="flex h-full flex-col overflow-hidden bg-white">

    <!-- Top toolbar -->
    <div class="flex flex-wrap items-center gap-2 border-b border-slate-200 bg-slate-50 px-4 py-2.5">
      <!-- Actions -->
      <button
        type="button"
        class="inline-flex items-center gap-1.5 rounded-lg bg-slate-900 px-3 py-1.5 text-xs font-medium text-white transition hover:bg-slate-700"
        @click="openCreateModal"
      >
        <PlusIcon class="h-3.5 w-3.5" />
        新建任务
      </button>
      <button
        type="button"
        class="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 px-3 py-1.5 text-xs text-slate-600 transition hover:bg-slate-100 disabled:opacity-50"
        :disabled="loading"
        @click="fetchTasks"
      >
        <ArrowPathIcon class="h-3.5 w-3.5" :class="loading ? 'animate-spin' : ''" />
        刷新
      </button>

      <div class="mx-1 h-4 w-px bg-slate-200" />

      <!-- Status tabs -->
      <TabSwitch
        :tabs="statusTabsNormalized"
        :active="activeTab"
        @change="activeTab = $event"
      />

      <!-- Right side -->
      <div class="ml-auto flex items-center gap-3">
        <AppCheckbox
          v-model="onlyCurrentProject"
          label-class="gap-1.5 text-xs text-slate-500"
          input-class="shadow-none"
        >
          仅当前项目
        </AppCheckbox>
        <button
          type="button"
          class="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 px-2.5 py-1.5 text-xs text-slate-500 transition hover:bg-slate-100"
          :class="autoRefresh ? 'text-emerald-600' : ''"
          @click="autoRefresh = !autoRefresh"
        >
          <span
            class="inline-block h-1.5 w-1.5 rounded-full"
            :class="autoRefresh ? 'bg-emerald-400 animate-pulse' : 'bg-slate-300'"
          />
          {{ autoRefresh ? '自动刷新' : '已暂停' }}
        </button>
        <!-- Login status badge + button -->
        <div class="flex items-center gap-1.5">
          <span
            class="inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-xs font-medium"
            :class="{
              'border-emerald-200 bg-emerald-50 text-emerald-700': loginState.status === 'ok',
              'border-amber-200 bg-amber-50 text-amber-700': loginState.status === 'logging_in',
              'border-rose-200 bg-rose-50 text-rose-700': loginState.status === 'failed',
              'border-slate-200 bg-slate-50 text-slate-500': loginState.status === 'idle' || !loginState.status,
            }"
          >
            <span
              class="inline-block h-1.5 w-1.5 rounded-full"
              :class="{
                'bg-emerald-400': loginState.status === 'ok',
                'bg-amber-400 animate-pulse': loginState.status === 'logging_in',
                'bg-rose-400': loginState.status === 'failed',
                'bg-slate-300': loginState.status === 'idle' || !loginState.status,
              }"
            />
            {{ loginStatusLabel }}
          </span>
          <button
            type="button"
            class="rounded-lg border border-slate-200 px-2.5 py-1.5 text-xs text-slate-600 transition hover:bg-slate-100 disabled:opacity-50"
            :disabled="loginState.status === 'logging_in' || !settingsState.credentials.configured"
            :title="!settingsState.credentials.configured ? '请先配置账号密码' : ''"
            @click="triggerLogin"
          >
            {{ loginState.status === 'logging_in' ? '登录中…' : '登录' }}
          </button>
        </div>

        <button
          type="button"
          class="rounded-lg border border-slate-200 p-1.5 text-slate-400 transition hover:bg-slate-100"
          @click="goSettings"
          title="NetInsight 设置"
        >
          <Cog6ToothIcon class="h-3.5 w-3.5" />
        </button>
      </div>
    </div>

    <!-- Notification bar -->
    <div
      v-if="!settingsState.credentials.configured"
      class="border-b border-amber-200 bg-amber-50 px-4 py-2 text-xs text-amber-800"
    >
      还没有填写 NetInsight 账号，任务暂时无法运行。点右上角齿轮图标进入设置，填好账号密码再来。
    </div>
    <div
      v-else-if="loginState.status === 'logging_in'"
      class="border-b border-amber-200 bg-amber-50 px-4 py-2.5 text-xs text-amber-900"
    >
      <div class="flex flex-wrap items-center gap-x-4 gap-y-1">
        <span class="inline-flex items-center gap-2 font-medium">
          <span class="inline-block h-1.5 w-1.5 rounded-full bg-amber-500 animate-pulse" />
          正在登录 NetInsight
        </span>
        <span class="text-amber-800">{{ loginState.step || '等待后台返回进度…' }}</span>
        <span class="text-amber-700">
          {{ settingsState.runtime.headless ? '当前为隐藏浏览器窗口模式' : '当前会显示浏览器窗口' }}
        </span>
      </div>
    </div>
    <div
      v-else-if="loginState.status === 'failed'"
      class="border-b border-rose-200 bg-rose-50 px-4 py-2.5 text-xs text-rose-800"
    >
      登录失败：{{ loginState.error || '未知错误' }}
    </div>
    <div
      v-else-if="feedback.message"
      class="border-b px-4 py-2 text-xs"
      :class="feedback.type === 'error' ? 'border-rose-200 bg-rose-50 text-rose-700' : 'border-emerald-200 bg-emerald-50 text-emerald-700'"
    >
      {{ feedback.message }}
    </div>

    <!-- Column headers -->
    <div class="flex items-center gap-3 border-b border-slate-100 bg-slate-50/60 px-4 py-1.5 text-[11px] font-medium uppercase tracking-wider text-slate-400">
      <div class="w-3 flex-none" />
      <div class="min-w-0 flex-1">任务</div>
      <div class="w-48 flex-none hidden lg:block">进度</div>
      <div class="w-28 flex-none hidden sm:block text-right font-mono">已获取 / 计划</div>
      <div class="w-32 flex-none hidden xl:block text-right">更新时间</div>
      <div class="w-40 flex-none text-right">操作</div>
    </div>

    <!-- Task list -->
    <div class="min-h-0 flex-1 overflow-y-auto">
      <div v-if="loading && !tasks.length" class="flex items-center justify-center py-20 text-sm text-slate-400">
        <ArrowPathIcon class="mr-2 h-4 w-4 animate-spin" />
        加载队列状态…
      </div>
      <div v-else-if="error" class="px-5 py-4 text-xs text-rose-700">{{ error }}</div>
      <div v-else-if="!tabFilteredTasks.length" class="flex flex-col items-center justify-center py-20 text-slate-400">
        <QueueListIcon class="h-10 w-10 text-slate-200" />
        <p class="mt-3 text-sm font-medium text-slate-400">
          {{ activeTab === 'all' ? '暂无任务' : `暂无「${statusTabs.find(t => t.key === activeTab)?.label}」任务` }}
        </p>
        <button
          v-if="activeTab === 'all'"
          type="button"
          class="mt-3 text-xs text-sky-600 hover:underline"
          @click="openCreateModal"
        >
          新建第一个任务 →
        </button>
      </div>

      <div v-else class="divide-y divide-slate-100">
        <div v-for="task in tabFilteredTasks" :key="task.id">
          <!-- Compact row -->
          <div
            class="group flex cursor-pointer items-center gap-3 px-4 py-3 transition hover:bg-slate-50"
            :class="expandedTaskId === task.id ? 'bg-slate-50' : ''"
            @click="toggleExpand(task.id)"
          >
            <!-- Status dot -->
            <div class="flex-none">
              <span
                class="block h-2 w-2 rounded-full"
                :class="[statusDotClass(task.status), task.status === 'running' ? 'animate-pulse' : '']"
              />
            </div>

            <!-- Title + tags -->
            <div class="min-w-0 flex-1">
              <div class="flex flex-wrap items-center gap-1.5">
                <span class="truncate text-sm font-medium text-slate-900">{{ task.title || task.id }}</span>
                <span class="shrink-0 rounded px-1.5 py-0.5 text-[10px] font-semibold" :class="statusClass(task.status)">
                  {{ statusLabel(task.status) }}
                </span>
                <span v-if="task.project" class="shrink-0 rounded bg-slate-100 px-1.5 py-0.5 text-[10px] text-slate-500">
                  {{ task.project }}
                </span>
              </div>
              <div class="mt-1 flex flex-wrap items-center gap-1">
                <span
                  v-for="kw in (task.keywords || []).slice(0, 5)"
                  :key="`${task.id}-kw-${kw}`"
                  class="rounded bg-sky-50 px-1.5 py-0.5 text-[10px] text-sky-600"
                >{{ kw }}</span>
                <span v-if="(task.keywords || []).length > 5" class="text-[10px] text-slate-400">
                  +{{ task.keywords.length - 5 }}
                </span>
                <span
                  v-for="pf in (task.platforms || [])"
                  :key="`${task.id}-pf-${pf}`"
                  class="rounded bg-emerald-50 px-1.5 py-0.5 text-[10px] text-emerald-600"
                >{{ pf }}</span>
              </div>
            </div>

            <!-- Progress bar -->
            <div class="w-48 flex-none hidden lg:block">
              <div class="flex items-center justify-between text-[11px]">
                <span class="truncate text-slate-500 max-w-[140px]">
                  {{ task.progress?.message || (task.status === 'queued' ? '等待中' : task.status === 'completed' ? '已完成' : '') }}
                </span>
                <span class="ml-1 shrink-0 font-mono text-slate-600">{{ Number(task.progress?.percentage || 0).toFixed(0) }}%</span>
              </div>
              <div class="mt-1.5 h-1 overflow-hidden rounded-full bg-slate-100">
                <div
                  class="h-full rounded-full transition-all duration-500"
                  :class="progressFillClass(task.status)"
                  :style="{ width: `${Math.max(0, Math.min(100, Number(task.progress?.percentage || 0)))}%` }"
                />
              </div>
            </div>

            <!-- Count -->
            <div class="w-28 flex-none hidden sm:block text-right font-mono text-[12px] text-slate-500">
              <span class="font-semibold text-slate-800">{{ task.progress?.fetched_total ?? 0 }}</span>
              <span class="text-slate-300"> / </span>
              <span>{{ task.progress?.planned_total ?? '?' }}</span>
            </div>

            <!-- Timestamp -->
            <div class="w-32 flex-none hidden xl:block text-right text-[11px] text-slate-400 tabular-nums">
              {{ formatTimestamp(task.updated_at) }}
            </div>

            <!-- Actions (stop propagation so clicks don't expand/collapse) -->
            <div class="flex w-40 flex-none items-center justify-end gap-1" @click.stop>
              <button
                v-if="task.status === 'queued' || task.status === 'running'"
                type="button"
                class="rounded border border-transparent px-2 py-1 text-[11px] text-slate-500 transition hover:border-rose-200 hover:bg-rose-50 hover:text-rose-600"
                @click="cancelTask(task)"
              >
                取消
              </button>
              <button
                v-if="task.status === 'failed' || task.status === 'cancelled' || task.status === 'completed'"
                type="button"
                class="rounded border border-transparent px-2 py-1 text-[11px] text-slate-500 transition hover:border-sky-200 hover:bg-sky-50 hover:text-sky-600"
                @click="retryTask(task)"
              >
                重试
              </button>
              <button
                v-if="task.status !== 'running'"
                type="button"
                class="rounded border border-transparent px-2 py-1 text-[11px] text-slate-500 transition hover:border-slate-300 hover:bg-slate-100"
                @click="deleteTask(task)"
              >
                删除
              </button>
              <ChevronDownIcon
                class="ml-1 h-3.5 w-3.5 flex-none text-slate-300 transition-transform duration-200"
                :class="expandedTaskId === task.id ? 'rotate-180' : ''"
              />
            </div>
          </div>

          <!-- Expanded detail panel -->
          <div v-if="expandedTaskId === task.id" class="border-t border-slate-100 bg-slate-50/50 px-4 py-4">
            <div class="grid gap-4 md:grid-cols-3">

              <!-- Meta info -->
              <div>
                <p class="mb-2 font-mono text-[10px] uppercase tracking-wider text-slate-400">Task Info</p>
                <dl class="space-y-1.5 text-xs">
                  <div class="flex items-start justify-between gap-2">
                    <dt class="shrink-0 text-slate-400">ID</dt>
                    <dd class="break-all font-mono text-slate-600 text-right">{{ task.id }}</dd>
                  </div>
                  <div class="flex items-start justify-between gap-2">
                    <dt class="shrink-0 text-slate-400">时间范围</dt>
                    <dd class="text-slate-700 text-right">{{ task.config?.start_date || '--' }} → {{ task.config?.end_date || '--' }}</dd>
                  </div>
                  <div class="flex items-center justify-between gap-2">
                    <dt class="text-slate-400">计划总量</dt>
                    <dd class="font-mono text-slate-700">{{ task.progress?.planned_total ?? 0 }}</dd>
                  </div>
                  <div class="flex items-center justify-between gap-2">
                    <dt class="text-slate-400">已抓取</dt>
                    <dd class="font-mono text-slate-700">{{ task.progress?.fetched_total ?? 0 }}</dd>
                  </div>
                  <div class="flex items-center justify-between gap-2">
                    <dt class="text-slate-400">去重后</dt>
                    <dd class="font-mono text-slate-700">{{ task.output?.deduplicated_count ?? task.progress?.deduped_total ?? 0 }}</dd>
                  </div>
                  <div class="flex items-center justify-between gap-2">
                    <dt class="text-slate-400">更新时间</dt>
                    <dd class="font-mono text-slate-600">{{ formatTimestamp(task.updated_at) }}</dd>
                  </div>
                </dl>
                <!-- Error -->
                <div v-if="task.error" class="mt-3 rounded border border-rose-200 bg-rose-50 p-2 text-[11px] text-rose-700">
                  {{ task.error }}
                </div>
              </div>

              <!-- Log -->
              <div>
                <p class="mb-2 font-mono text-[10px] uppercase tracking-wider text-slate-400">Recent Log</p>
                <div class="rounded-lg border border-slate-800 bg-slate-950 p-3">
                  <ul v-if="task.events?.length" class="space-y-1.5 font-mono text-[11px] leading-5 text-slate-300">
                    <li v-for="event in task.events.slice(-6).reverse()" :key="`${task.id}-${event.timestamp}-${event.message}`">
                      <span class="text-slate-500">{{ formatTimestamp(event.timestamp) }}</span>
                      <span class="mx-1.5 text-slate-600">|</span>
                      <span>{{ event.message }}</span>
                    </li>
                  </ul>
                  <p v-else class="text-[11px] text-slate-500">暂无事件记录</p>
                </div>
              </div>

              <!-- Output + Downloads -->
              <div>
                <p class="mb-2 font-mono text-[10px] uppercase tracking-wider text-slate-400">Output</p>
                <p class="mb-3 break-all text-[11px] text-slate-500">{{ task.output?.dir || '尚未生成' }}</p>
                <div v-if="task.status === 'completed'" class="flex flex-wrap gap-1.5">
                  <button
                    v-if="taskHasFile(task, 'records.csv')"
                    type="button"
                    class="inline-flex items-center gap-1 rounded border border-slate-700 bg-slate-900 px-2.5 py-1.5 text-[11px] font-medium text-white transition hover:bg-slate-700 disabled:opacity-50"
                    :disabled="downloadingTaskId === task.id"
                    @click="downloadTaskFile(task, 'csv')"
                  >
                    <ArrowDownTrayIcon class="h-3 w-3" />
                    CSV
                  </button>
                  <button
                    v-if="taskHasFile(task, 'records.jsonl')"
                    type="button"
                    class="inline-flex items-center gap-1 rounded border border-slate-200 bg-white px-2.5 py-1.5 text-[11px] font-medium text-slate-700 transition hover:bg-slate-50 disabled:opacity-50"
                    :disabled="downloadingTaskId === task.id"
                    @click="downloadTaskFile(task, 'jsonl')"
                  >
                    <ArrowDownTrayIcon class="h-3 w-3" />
                    JSONL
                  </button>
                  <button
                    v-if="taskHasFile(task, 'meta.json')"
                    type="button"
                    class="inline-flex items-center gap-1 rounded border border-slate-200 bg-white px-2.5 py-1.5 text-[11px] font-medium text-slate-700 transition hover:bg-slate-50 disabled:opacity-50"
                    :disabled="downloadingTaskId === task.id"
                    @click="downloadTaskFile(task, 'meta')"
                  >
                    <ArrowDownTrayIcon class="h-3 w-3" />
                    Meta
                  </button>
                </div>
                <p v-else-if="task.status !== 'completed'" class="text-[11px] text-slate-400">
                  {{ task.status === 'running' ? '任务执行中，完成后可下载…' : task.status === 'queued' ? '任务排队中…' : '无可下载文件' }}
                </p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Footer status bar -->
    <footer class="flex flex-wrap items-center justify-between gap-3 border-t border-slate-200 bg-slate-50 px-4 py-2">
      <div class="flex items-center gap-4 font-mono text-[11px]">
        <span class="text-slate-400">ALL <span class="text-slate-700">{{ taskSummary.total }}</span></span>
        <span class="text-slate-400">ACTIVE <span class="text-sky-600 font-semibold">{{ taskSummary.running }}</span></span>
        <span class="text-slate-400">WAITING <span class="text-slate-600">{{ taskSummary.queued }}</span></span>
        <span class="text-slate-400">DONE <span class="text-emerald-600">{{ taskSummary.completed }}</span></span>
        <span class="text-slate-400">FAIL <span class="text-rose-500">{{ (taskSummary.failed ?? 0) + (taskSummary.cancelled ?? 0) }}</span></span>
      </div>
      <div class="flex items-center gap-3 font-mono text-[11px] text-slate-400">
        <span>默认不关联项目</span>
        <span :class="worker.running ? 'text-emerald-500' : ''">DAEMON: {{ workerStatusLabel }}</span>
      </div>
    </footer>
  </div>

  <AppModal
      v-model="createModalOpen"
      title="新建数据采集任务"
      eyebrow="新建任务"
      width="max-w-3xl"
      confirm-text="开始采集"
      confirm-loading-text="提交中…"
      :confirm-loading="submitting"
      :confirm-disabled="submitting || !canSubmit"
      :scrollable="true"
      @confirm="submitTask"
    >
      <template #description>
        <p class="text-sm text-slate-500">
          请优先确认关键词、平台与时间范围。辅助说明仅用于智能生成配置，不影响你手动填写后的实际采集内容。
        </p>
      </template>

      <div class="space-y-6">
        <div class="grid gap-4 lg:grid-cols-[1.2fr_1fr]">
          <label class="space-y-2 text-sm">
            <span class="font-medium text-slate-700">任务标题</span>
            <input
              v-model.trim="taskForm.title"
              type="text"
              placeholder="例如：小米 SU7 网络舆情监测"
              class="w-full rounded-2xl border border-slate-200 px-4 py-3 text-sm text-slate-700 focus:border-indigo-300 focus:outline-none focus:ring-2 focus:ring-indigo-200"
            />
          </label>
          <label class="space-y-2 text-sm">
            <span class="font-medium text-slate-700">关联项目</span>
            <AppSelect
              :options="projectSelectOptions"
              :value="taskForm.project"
              @change="taskForm.project = $event"
            />
          </label>
        </div>

        <div class="grid gap-4 lg:grid-cols-2">
          <label class="space-y-2 text-sm">
            <span class="font-medium text-slate-700">关键词</span>
            <textarea
              v-model.trim="taskForm.keywordsText"
              rows="5"
              placeholder="支持按行输入或使用逗号分隔，例如：小米SU7, 刹车失灵, 事故"
              class="w-full rounded-2xl border border-slate-200 px-4 py-3 text-sm text-slate-700 focus:border-indigo-300 focus:outline-none focus:ring-2 focus:ring-indigo-200"
            />
          </label>
          <div class="space-y-4 rounded-3xl border border-slate-200 bg-slate-50/80 p-4">
            <div>
              <p class="text-sm font-medium text-slate-700">平台</p>
              <div class="mt-3 grid gap-2 sm:grid-cols-2">
                <AppCheckbox
                  v-for="option in platformOptions"
                  :key="option"
                  v-model="taskForm.platforms"
                  :value="option"
                  class="rounded-2xl border border-slate-200 bg-white px-3 py-2"
                  label-class="gap-2 text-sm text-slate-600"
                  input-class="shadow-none"
                >
                  <span>{{ option }}</span>
                </AppCheckbox>
              </div>
            </div>
            <div class="grid gap-4 sm:grid-cols-2">
              <label class="space-y-2 text-sm">
                <span class="font-medium text-slate-700">开始日期</span>
                <input
                  v-model="taskForm.startDate"
                  type="date"
                  class="w-full rounded-2xl border border-slate-200 px-4 py-3 text-sm text-slate-700 focus:border-indigo-300 focus:outline-none focus:ring-2 focus:ring-indigo-200"
                />
              </label>
              <label class="space-y-2 text-sm">
                <span class="font-medium text-slate-700">结束日期</span>
                <input
                  v-model="taskForm.endDate"
                  type="date"
                  class="w-full rounded-2xl border border-slate-200 px-4 py-3 text-sm text-slate-700 focus:border-indigo-300 focus:outline-none focus:ring-2 focus:ring-indigo-200"
                />
              </label>
            </div>
          </div>
        </div>

        <div class="space-y-3">
          <div class="flex items-center justify-between gap-3">
            <label class="text-sm font-medium text-slate-700">辅助说明（可选）</label>
            <button
              type="button"
              class="rounded-full border border-indigo-200 px-4 py-2 text-xs font-semibold text-indigo-700 transition hover:bg-indigo-50 disabled:cursor-not-allowed disabled:opacity-60"
              :disabled="planning || !taskForm.brief.trim()"
              @click="planTask"
            >
              {{ planning ? '生成中…' : '智能生成配置' }}
            </button>
          </div>
          <textarea
            v-model.trim="taskForm.brief"
            rows="4"
            placeholder="可填写监测对象、时间范围、采集平台或重点议题，供系统辅助生成关键词与参数。"
            class="w-full rounded-2xl border border-slate-200 px-4 py-3 text-sm text-slate-700 focus:border-indigo-300 focus:outline-none focus:ring-2 focus:ring-indigo-200"
          />
        </div>

        <!-- Advanced options (collapsed by default) -->
        <div class="rounded-2xl border border-slate-200">
          <button
            type="button"
            class="flex w-full items-center justify-between px-4 py-3 text-sm text-slate-600 hover:bg-slate-50 rounded-2xl transition"
            @click="showAdvanced = !showAdvanced"
          >
            <span class="font-medium">高级选项</span>
            <ChevronDownIcon class="h-4 w-4 text-slate-400 transition-transform duration-200" :class="showAdvanced ? 'rotate-180' : ''" />
          </button>
          <div v-if="showAdvanced" class="border-t border-slate-200 px-4 pb-4 pt-4 space-y-4">
            <div class="grid gap-4 sm:grid-cols-4">
              <label class="space-y-2 text-sm">
                <span class="font-medium text-slate-700">最多抓取条数</span>
                <input
                  v-model.number="taskForm.totalLimit"
                  type="number"
                  min="1"
                  class="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm text-slate-700 focus:border-indigo-300 focus:outline-none focus:ring-2 focus:ring-indigo-200"
                />
              </label>
              <label class="space-y-2 text-sm">
                <span class="font-medium text-slate-700">每批请求数</span>
                <input
                  v-model.number="taskForm.pageSize"
                  type="number"
                  min="10"
                  class="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm text-slate-700 focus:border-indigo-300 focus:outline-none focus:ring-2 focus:ring-indigo-200"
                />
              </label>
              <label class="space-y-2 text-sm">
                <span class="font-medium text-slate-700">排序</span>
                <AppSelect
                  :options="sortOptions"
                  :value="taskForm.sort"
                  @change="taskForm.sort = $event"
                />
              </label>
              <label class="space-y-2 text-sm">
                <span class="font-medium text-slate-700">内容类型</span>
                <AppSelect
                  :options="infoTypeOptions"
                  :value="taskForm.infoType"
                  @change="taskForm.infoType = $event"
                />
              </label>
            </div>
            <AppCheckbox
              v-model="taskForm.dedupeByContent"
              label-class="gap-2 text-sm text-slate-600"
              input-class="shadow-none"
            >
              自动过滤重复内容
            </AppCheckbox>
          </div>
        </div>
      </div>
    </AppModal>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import TabSwitch from '../../components/TabSwitch.vue'
import {
  ArrowDownTrayIcon,
  ArrowPathIcon,
  ChevronDownIcon,
  Cog6ToothIcon,
  PlusIcon,
  QueueListIcon,
} from '@heroicons/vue/24/outline'

import AppModal from '../../components/AppModal.vue'
import AppCheckbox from '../../components/AppCheckbox.vue'
import AppSelect from '../../components/AppSelect.vue'
import { useActiveProject } from '../../composables/useActiveProject'
import { useApiBase } from '../../composables/useApiBase'

const platformOptions = ['微博', '微信', '新闻网站', '新闻APP', '论坛', '视频', '自媒体号', '全部']

// Select options
const sortOptions = [
  { value: 'comments_desc', label: '按评论热度' },
  { value: 'relevance', label: '按相关度' },
  { value: 'hot', label: '按热度' }
]

const infoTypeOptions = [
  { value: '2', label: '内容' },
  { value: '1', label: '全部' },
  { value: '3', label: '评论' }
]

const projectSelectOptions = computed(() => [
  { value: '', label: '不关联项目' },
  ...projects.value.map(p => ({ value: p.name, label: p.name }))
])

const router = useRouter()
const { backendBase, callApi } = useApiBase()
const { activeProjectName } = useActiveProject()

const loading = ref(false)
const error = ref('')
const tasks = ref([])
const projects = ref([])
const autoRefresh = ref(true)
const onlyCurrentProject = ref(false)
const createModalOpen = ref(false)
const planning = ref(false)
const submitting = ref(false)
const refreshTimer = ref(null)
const downloadingTaskId = ref('')
const activeTab = ref('all')
const expandedTaskId = ref(null)
const showAdvanced = ref(false)
const loginState = ref({ status: 'idle', logged_in_at: null, error: null, username: '' })
const loginPollTimer = ref(null)

const worker = ref({})
const settingsState = reactive({
  credentials: {
    configured: false,
    user: '',
    masked_user: '',
    password_configured: false,
  },
  runtime: {},
  planner: {},
})

const feedback = reactive({
  type: '',
  message: '',
})

const taskForm = reactive({
  title: '',
  project: '',
  brief: '',
  keywordsText: '',
  platforms: [],
  startDate: '',
  endDate: '',
  totalLimit: 500,
  pageSize: 50,
  sort: 'comments_desc',
  infoType: '2',
  dedupeByContent: true,
})

const canSubmit = computed(() => {
  if (!taskForm.title.trim()) return false
  if (!taskForm.startDate || !taskForm.endDate) return false
  if (!parseKeywords(taskForm.keywordsText).length) return false
  if (!taskForm.platforms.length) return false
  return true
})

const projectFiltered = computed(() => {
  if (!onlyCurrentProject.value || !activeProjectName.value) return tasks.value
  return tasks.value.filter((task) => task.project === activeProjectName.value)
})

const statusTabs = computed(() => {
  const base = projectFiltered.value
  return [
    { key: 'all', label: '全部', count: base.length },
    { key: 'running', label: '执行中', count: base.filter((t) => t.status === 'running').length },
    { key: 'queued', label: '排队', count: base.filter((t) => t.status === 'queued').length },
    { key: 'completed', label: '已完成', count: base.filter((t) => t.status === 'completed').length },
    { key: 'failed', label: '失败/取消', count: base.filter((t) => t.status === 'failed' || t.status === 'cancelled').length },
  ]
})

const statusTabsNormalized = computed(() =>
  statusTabs.value.map(t => ({ value: t.key, label: t.label, badge: t.count }))
)

const tabFilteredTasks = computed(() => {
  const base = projectFiltered.value
  if (activeTab.value === 'all') return base
  if (activeTab.value === 'failed') return base.filter((t) => t.status === 'failed' || t.status === 'cancelled')
  return base.filter((t) => t.status === activeTab.value)
})

function toggleExpand(id) {
  expandedTaskId.value = expandedTaskId.value === id ? null : id
}

const loginStatusLabel = computed(() => {
  const s = loginState.value.status
  if (s === 'ok') return `已登录${loginState.value.username ? ' · ' + loginState.value.username : ''}`
  if (s === 'logging_in') return loginState.value.step || '登录中…'
  if (s === 'failed') return '登录失败'
  return '未登录'
})

const workerStatusLabel = computed(() => {
  if (!worker.value?.running) return '离线'
  if (worker.value?.status === 'running') return `运行中${worker.value?.current_task_id ? ` · ${worker.value.current_task_id}` : ''}`
  return '待命'
})

const taskSummary = computed(() => {
  if (!tasks.value.length) {
    return { total: 0, queued: 0, running: 0, completed: 0, failed: 0, cancelled: 0 }
  }
  return tasks.value.reduce(
    (summary, task) => {
      const status = task.status
      summary.total += 1
      if (status in summary) summary[status] += 1
      return summary
    },
    { total: 0, queued: 0, running: 0, completed: 0, failed: 0, cancelled: 0 }
  )
})

function openCreateModal() {
  resetTaskForm()
  showAdvanced.value = false
  createModalOpen.value = true
}

function resetTaskForm() {
  const today = new Date()
  const start = new Date(today)
  start.setDate(today.getDate() - Number(settingsState.planner.default_days || 30) + 1)
  taskForm.title = ''
  taskForm.project = ''
  taskForm.brief = ''
  taskForm.keywordsText = ''
  taskForm.platforms = normalizePlatformsForSubmit(settingsState.planner.default_platforms || ['微博'])
  taskForm.startDate = formatDateInput(start)
  taskForm.endDate = formatDateInput(today)
  taskForm.totalLimit = Number(settingsState.planner.default_total_limit || 500)
  taskForm.pageSize = Number(settingsState.runtime.page_size || 50)
  taskForm.sort = String(settingsState.runtime.sort || 'comments_desc')
  taskForm.infoType = String(settingsState.runtime.info_type || '2')
  taskForm.dedupeByContent = true
}

async function fetchLoginState() {
  try {
    const response = await callApi('/api/netinsight/login', { method: 'GET' })
    loginState.value = response?.data || { status: 'idle' }
  } catch {
    // ignore
  }
}

async function triggerLogin() {
  if (loginState.value.status === 'logging_in') return
  try {
    loginState.value = {
      ...loginState.value,
      status: 'logging_in',
      step: '准备启动…',
      error: null,
    }
    const response = await callApi('/api/netinsight/login', { method: 'POST' })
    loginState.value = response?.data || loginState.value
    startLoginPoll()
  } catch (err) {
    feedback.type = 'error'
    feedback.message = err instanceof Error ? err.message : '登录请求失败'
  }
}

function startLoginPoll() {
  stopLoginPoll()

  const poll = async () => {
    await fetchLoginState()
    if (loginState.value.status !== 'logging_in') {
      stopLoginPoll()
      if (loginState.value.status === 'failed') {
        feedback.type = 'error'
        feedback.message = `登录失败：${loginState.value.error || '未知错误'}（可点击登录重试）`
      } else if (loginState.value.status === 'ok') {
        feedback.type = 'success'
        feedback.message = '登录成功'
      }
    }
  }

  void poll()
  loginPollTimer.value = window.setInterval(() => {
    void poll()
  }, 800)
}

function stopLoginPoll() {
  if (loginPollTimer.value) {
    window.clearInterval(loginPollTimer.value)
    loginPollTimer.value = null
  }
}

async function fetchProjects() {
  try {
    const response = await callApi('/api/projects', { method: 'GET' })
    projects.value = Array.isArray(response.projects) ? response.projects : []
  } catch (err) {
    console.warn(err)
  }
}

async function fetchSettings() {
  try {
    const response = await callApi('/api/settings/netinsight', { method: 'GET' })
    const payload = response?.data || {}
    Object.assign(settingsState.credentials, payload.credentials || {})
    settingsState.runtime = payload.runtime || {}
    settingsState.planner = payload.planner || {}
  } catch (err) {
    console.warn(err)
  }
}

async function fetchTasks() {
  loading.value = true
  error.value = ''
  try {
    const response = await callApi('/api/netinsight/tasks', { method: 'GET' })
    const payload = response?.data || {}
    tasks.value = Array.isArray(payload.tasks) ? payload.tasks : []
    worker.value = payload.worker || {}
  } catch (err) {
    error.value = err instanceof Error ? err.message : '读取任务列表失败'
  } finally {
    loading.value = false
  }
}

async function planTask() {
  if (!taskForm.brief.trim()) return
  planning.value = true
  feedback.type = ''
  feedback.message = ''
  try {
    const response = await callApi('/api/netinsight/tasks/plan', {
      method: 'POST',
      body: JSON.stringify({ brief: taskForm.brief }),
    })
    const plan = response?.data || {}
    taskForm.title = String(plan.title || taskForm.title || '').trim()
    taskForm.keywordsText = Array.isArray(plan.keywords) ? plan.keywords.join('\n') : taskForm.keywordsText
    taskForm.platforms = Array.isArray(plan.platforms) && plan.platforms.length
      ? normalizePlatformsForSubmit(plan.platforms)
      : taskForm.platforms
    taskForm.startDate = String(plan.start_date || taskForm.startDate || '')
    taskForm.endDate = String(plan.end_date || taskForm.endDate || '')
    taskForm.totalLimit = Number(plan.total_limit || taskForm.totalLimit || 500)
    taskForm.pageSize = Number(plan.page_size || taskForm.pageSize || 50)
    taskForm.sort = String(plan.sort || taskForm.sort || 'comments_desc')
    taskForm.infoType = String(plan.info_type || taskForm.infoType || '2')
    taskForm.dedupeByContent = Boolean(plan.dedupe_by_content ?? taskForm.dedupeByContent)
    feedback.type = 'success'
    feedback.message = `已根据任务说明生成建议配置（来源：${plan.planner_source || 'heuristic'}）`
  } catch (err) {
    feedback.type = 'error'
    feedback.message = err instanceof Error ? err.message : '解析任务说明失败'
  } finally {
    planning.value = false
  }
}

async function submitTask() {
  if (!canSubmit.value) return
  submitting.value = true
  feedback.type = ''
  feedback.message = ''
  try {
    const response = await callApi('/api/netinsight/tasks', {
      method: 'POST',
      body: JSON.stringify({
        title: taskForm.title,
        project: taskForm.project,
        query: taskForm.brief,
        summary: taskForm.brief,
        keywords: parseKeywords(taskForm.keywordsText),
        platforms: normalizePlatformsForSubmit(taskForm.platforms),
        start_date: taskForm.startDate,
        end_date: taskForm.endDate,
        total_limit: Number(taskForm.totalLimit || 500),
        page_size: Number(taskForm.pageSize || 50),
        sort: taskForm.sort,
        info_type: taskForm.infoType,
        dedupe_by_content: taskForm.dedupeByContent,
      }),
    })
    createModalOpen.value = false
    feedback.type = 'success'
    feedback.message = `任务 ${response?.data?.task?.id || ''} 已提交到队列`
    await fetchTasks()
  } catch (err) {
    feedback.type = 'error'
    feedback.message = err instanceof Error ? err.message : '创建任务失败'
  } finally {
    submitting.value = false
  }
}

async function cancelTask(task) {
  try {
    await callApi(`/api/netinsight/tasks/${encodeURIComponent(task.id)}/cancel`, {
      method: 'POST',
    })
    feedback.type = 'success'
    feedback.message = `已发送取消请求：${task.title || task.id}`
    await fetchTasks()
  } catch (err) {
    feedback.type = 'error'
    feedback.message = err instanceof Error ? err.message : '取消任务失败'
  }
}

async function retryTask(task) {
  try {
    const response = await callApi(`/api/netinsight/tasks/${encodeURIComponent(task.id)}/retry`, {
      method: 'POST',
    })
    feedback.type = 'success'
    feedback.message = `已创建重试任务：${response?.data?.task?.id || ''}`
    await fetchTasks()
  } catch (err) {
    feedback.type = 'error'
    feedback.message = err instanceof Error ? err.message : '重试任务失败'
  }
}

async function deleteTask(task) {
  try {
    await callApi(`/api/netinsight/tasks/${encodeURIComponent(task.id)}`, {
      method: 'DELETE',
    })
    feedback.type = 'success'
    feedback.message = `已删除任务：${task.title || task.id}`
    await fetchTasks()
  } catch (err) {
    feedback.type = 'error'
    feedback.message = err instanceof Error ? err.message : '删除任务失败'
  }
}

async function downloadTaskFile(task, kind) {
  downloadingTaskId.value = task.id
  feedback.type = ''
  feedback.message = ''
  try {
    const response = await fetch(buildTaskFileUrl(task.id, kind))
    if (!response.ok) {
      const text = await response.text()
      throw new Error(text || '下载任务文件失败')
    }
    const blob = await response.blob()
    const downloadUrl = window.URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = downloadUrl
    anchor.download = parseDownloadFilename(response.headers.get('Content-Disposition')) || `${task.id}.${kind}`
    document.body.appendChild(anchor)
    anchor.click()
    anchor.remove()
    window.URL.revokeObjectURL(downloadUrl)
    feedback.type = 'success'
    feedback.message = `已开始下载 ${task.title || task.id} 的 ${kind.toUpperCase()} 文件`
  } catch (err) {
    feedback.type = 'error'
    feedback.message = err instanceof Error ? err.message : '下载任务文件失败'
  } finally {
    downloadingTaskId.value = ''
  }
}

function goSettings() {
  router.push({ name: 'settings-netinsight' })
}

function statusLabel(status) {
  return {
    queued: '排队中',
    running: '执行中',
    completed: '已完成',
    failed: '失败',
    cancelled: '已取消',
  }[status] || status || '未知'
}

function statusClass(status) {
  return {
    queued: 'border border-slate-200 bg-slate-100 text-slate-700',
    running: 'border border-sky-200 bg-sky-50 text-sky-700',
    completed: 'border border-emerald-200 bg-emerald-50 text-emerald-700',
    failed: 'border border-rose-200 bg-rose-50 text-rose-700',
    cancelled: 'border border-amber-200 bg-amber-50 text-amber-700',
  }[status] || 'bg-slate-100 text-slate-700'
}

function statusDotClass(status) {
  return {
    queued: 'bg-slate-400',
    running: 'bg-sky-500',
    completed: 'bg-emerald-500',
    failed: 'bg-rose-500',
    cancelled: 'bg-amber-500',
  }[status] || 'bg-slate-400'
}

function progressFillClass(status) {
  return {
    queued: 'bg-slate-500',
    running: 'bg-gradient-to-r from-sky-500 to-cyan-400',
    completed: 'bg-gradient-to-r from-emerald-500 to-teal-400',
    failed: 'bg-gradient-to-r from-rose-500 to-orange-400',
    cancelled: 'bg-gradient-to-r from-amber-400 to-yellow-300',
  }[status] || 'bg-slate-500'
}

function parseKeywords(text) {
  return String(text || '')
    .split(/[\n,，;；、]+/)
    .map((item) => item.trim())
    .filter(Boolean)
}

function normalizePlatformsForSubmit(values) {
  const list = Array.isArray(values) ? values.map((item) => String(item).trim()).filter(Boolean) : []
  if (list.includes('全部')) return ['全部']
  return list
}

function taskHasFile(task, filename) {
  const files = Array.isArray(task?.output?.files) ? task.output.files : []
  if (!files.length) return Boolean(task?.output?.dir && task?.status === 'completed')
  return files.some((item) => String(item || '').endsWith(`/${filename}`) || String(item || '').endsWith(`\\${filename}`))
}

function buildTaskFileUrl(taskId, kind) {
  const base = String(backendBase.value || '').replace(/\/+$/, '')
  return `${base}/api/netinsight/tasks/${encodeURIComponent(taskId)}/files/${encodeURIComponent(kind)}`
}

function formatDateInput(value) {
  const year = value.getFullYear()
  const month = String(value.getMonth() + 1).padStart(2, '0')
  const day = String(value.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

function formatTimestamp(value) {
  if (!value) return '--'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')} ${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}`
}

function parseDownloadFilename(contentDisposition) {
  const match = String(contentDisposition || '').match(/filename\*?=(?:UTF-8''|")?([^\";]+)/i)
  if (!match?.[1]) return ''
  const raw = match[1].replace(/"/g, '').trim()
  try {
    return decodeURIComponent(raw)
  } catch {
    return raw
  }
}

function startRefreshLoop() {
  stopRefreshLoop()
  refreshTimer.value = window.setInterval(() => {
    if (!autoRefresh.value) return
    const hasActive = tasks.value.some((task) => ['queued', 'running'].includes(task.status))
    if (hasActive || !tasks.value.length) {
      fetchTasks()
    }
  }, 5000)
}

function stopRefreshLoop() {
  if (refreshTimer.value) {
    window.clearInterval(refreshTimer.value)
    refreshTimer.value = null
  }
}


onMounted(async () => {
  await Promise.all([fetchSettings(), fetchProjects(), fetchTasks(), fetchLoginState()])
  resetTaskForm()
  startRefreshLoop()
  if (loginState.value.status === 'logging_in') startLoginPoll()
})

onBeforeUnmount(() => {
  stopRefreshLoop()
  stopLoginPoll()
})
</script>
