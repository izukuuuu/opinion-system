<template>
  <section class="max-w-4xl space-y-6">
    <!-- Page header -->
    <header class="space-y-1">
      <h2 class="text-xl font-semibold text-primary">NetInsight 配置</h2>
      <p class="text-sm text-muted">
        在这里保存 NetInsight 登录信息和默认采集参数。保存后，新建任务会自动使用这些设置。
      </p>
    </header>

    <!-- Feedback banner -->
    <div
      v-if="feedback.message"
      class="rounded-2xl px-4 py-3 text-sm"
      :class="feedback.type === 'error' ? 'bg-danger-soft text-danger' : 'bg-success-soft text-success'"
    >
      {{ feedback.message }}
    </div>

    <!-- ─── Credentials ─────────────────────────────────────── -->
    <div class="card-surface p-6 space-y-5">
      <!-- Section header row: title + status badge -->
      <div class="flex items-center justify-between gap-4">
        <div class="flex items-center gap-3">
          <div class="flex h-8 w-8 items-center justify-center rounded-xl bg-brand-soft">
            <KeyIcon class="h-4 w-4 text-brand" />
          </div>
          <div>
            <h3 class="text-sm font-semibold text-primary">凭据</h3>
            <p class="text-xs text-muted">配置账号和密码，后台任务将自动登录并开始采集</p>
          </div>
        </div>
        <!-- Inline status badge -->
        <span
          class="shrink-0 rounded-full px-3 py-1 text-xs font-medium"
          :class="credentialsSummary.configured
            ? 'bg-success-soft text-success'
            : 'bg-surface-muted text-muted'"
        >
          {{ credentialsSummary.configured ? '✓ 已配置' : '未配置' }}
        </span>
      </div>

      <!-- Account + password inputs -->
      <div class="grid gap-4 sm:grid-cols-2">
        <label class="space-y-1.5 text-sm">
          <span class="font-medium text-secondary">账号</span>
          <input
            v-model.trim="form.user"
            type="text"
            autocomplete="username"
            placeholder="请输入账号"
            class="input"
          />
          <span v-if="credentialsSummary.masked_user" class="text-xs text-muted">
            当前：{{ credentialsSummary.masked_user }}
          </span>
        </label>
        <label class="space-y-1.5 text-sm">
          <span class="font-medium text-secondary">密码</span>
          <input
            v-model.trim="form.password"
            type="password"
            autocomplete="new-password"
            placeholder="留空则保持现有密码"
            class="input"
          />
          <span class="text-xs text-muted">
            {{ credentialsSummary.password_configured ? '已保存密码，留空不变' : '尚未保存密码' }}
          </span>
        </label>
      </div>

      <!-- Clear password toggle -->
      <label class="inline-flex items-center gap-2 cursor-pointer text-sm text-secondary select-none">
        <input
          v-model="form.clearPassword"
          type="checkbox"
          class="rounded border-soft accent-brand-600"
        />
        清空已保存的密码
      </label>
    </div>

    <!-- ─── Runtime parameters ──────────────────────────────── -->
    <div class="card-surface p-6 space-y-5">
      <div class="flex items-center gap-3">
        <div class="flex h-8 w-8 items-center justify-center rounded-xl bg-brand-soft">
          <CogIcon class="h-4 w-4 text-brand" />
        </div>
        <div>
          <h3 class="text-sm font-semibold text-primary">运行参数</h3>
          <p class="text-xs text-muted">控制浏览器采集行为的底层参数</p>
        </div>
      </div>

      <div class="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        <label class="space-y-1.5 text-sm">
          <span class="font-medium text-secondary">登录超时（毫秒）</span>
          <input
            v-model.number="form.loginTimeoutMs"
            type="number"
            min="10000"
            class="input"
          />
        </label>
        <label class="space-y-1.5 text-sm">
          <span class="font-medium text-secondary">后台空闲等待（秒）</span>
          <input
            v-model.number="form.workerIdleSeconds"
            type="number"
            min="15"
            class="input"
          />
        </label>
        <label class="space-y-1.5 text-sm">
          <span class="font-medium text-secondary">默认分页大小</span>
          <input
            v-model.number="form.pageSize"
            type="number"
            min="10"
            class="input"
          />
        </label>
        <label class="space-y-1.5 text-sm">
          <span class="font-medium text-secondary">默认排序</span>
          <select v-model="form.sort" class="input">
            <option value="comments_desc">按评论热度</option>
            <option value="relevance">按相关度</option>
            <option value="hot">按热度</option>
          </select>
        </label>
        <label class="space-y-1.5 text-sm">
          <span class="font-medium text-secondary">默认内容类型</span>
          <select v-model="form.infoType" class="input">
            <option value="2">内容</option>
            <option value="1">全部</option>
            <option value="3">评论</option>
          </select>
        </label>
        <label class="space-y-1.5 text-sm">
          <span class="font-medium text-secondary">浏览器通道</span>
          <input
            v-model.trim="form.browserChannel"
            type="text"
            placeholder="留空使用默认浏览器"
            class="input"
          />
        </label>
      </div>

      <!-- Toggle options -->
      <div class="grid gap-3 sm:grid-cols-2">
        <label class="flex items-center gap-3 rounded-2xl border border-soft bg-base-soft px-4 py-3 text-sm text-secondary cursor-pointer select-none">
          <input v-model="form.headless" type="checkbox" class="rounded border-soft accent-brand-600" />
          <div>
            <span class="font-medium text-primary">隐藏浏览器窗口</span>
            <p class="text-xs text-muted mt-0.5">关闭后会显示浏览器窗口，便于观察登录过程</p>
          </div>
        </label>
        <label class="flex items-center gap-3 rounded-2xl border border-soft bg-base-soft px-4 py-3 text-sm text-secondary cursor-pointer select-none">
          <input v-model="form.noProxy" type="checkbox" class="rounded border-soft accent-brand-600" />
          <div>
            <span class="font-medium text-primary">登录阶段禁用系统代理</span>
            <p class="text-xs text-muted mt-0.5">仅登录步骤绕过代理设置</p>
          </div>
        </label>
      </div>
    </div>

    <!-- ─── Planner defaults ────────────────────────────────── -->
    <div class="card-surface p-6 space-y-5">
      <div class="flex items-center gap-3">
        <div class="flex h-8 w-8 items-center justify-center rounded-xl bg-brand-soft">
          <CalendarDaysIcon class="h-4 w-4 text-brand" />
        </div>
        <div>
          <h3 class="text-sm font-semibold text-primary">规划默认值</h3>
          <p class="text-xs text-muted">新建采集任务时自动填充的预设参数</p>
        </div>
      </div>

      <div class="grid gap-4 sm:grid-cols-3">
        <label class="space-y-1.5 text-sm">
          <span class="font-medium text-secondary">默认回溯天数</span>
          <input
            v-model.number="form.defaultDays"
            type="number"
            min="1"
            class="input"
          />
        </label>
        <label class="space-y-1.5 text-sm">
          <span class="font-medium text-secondary">默认总抓取上限</span>
          <input
            v-model.number="form.defaultTotalLimit"
            type="number"
            min="1"
            class="input"
          />
        </label>
        <label class="space-y-1.5 text-sm">
          <span class="font-medium text-secondary">默认平台</span>
          <input
            v-model.trim="form.defaultPlatformsText"
            type="text"
            placeholder="例如：微博,新闻网站"
            class="input"
          />
        </label>
      </div>
    </div>

    <!-- ─── Save action bar ────────────────────────────────── -->
    <div class="card-surface flex items-center justify-between gap-4 px-5 py-4">
      <p class="text-xs text-muted">
        保存后，所有新建任务将自动继承以上设置
      </p>
      <button
        type="button"
        class="btn-primary shrink-0 px-6 py-2.5 text-sm"
        :disabled="loading"
        @click="submit"
      >
        {{ loading ? '保存中…' : '保存设置' }}
      </button>
    </div>
  </section>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { KeyIcon, Cog6ToothIcon as CogIcon, CalendarDaysIcon } from '@heroicons/vue/24/outline'

import { useApiBase } from '../../composables/useApiBase'

const { callApi } = useApiBase()

const loading = ref(false)
const credentialsSummary = reactive({
  configured: false,
  user: '',
  masked_user: '',
  password_configured: false,
})

const feedback = reactive({
  type: '',
  message: '',
})

const form = reactive({
  user: '',
  password: '',
  clearPassword: false,
  headless: false,
  noProxy: false,
  loginTimeoutMs: 120000,
  workerIdleSeconds: 90,
  pageSize: 50,
  sort: 'comments_desc',
  infoType: '2',
  browserChannel: '',
  defaultDays: 30,
  defaultTotalLimit: 500,
  defaultPlatformsText: '微博',
})

const defaultPlatforms = computed(() =>
  String(form.defaultPlatformsText || '')
    .split(/[\n,，;；、]+/)
    .map((item) => item.trim())
    .filter(Boolean)
)

async function fetchSettings() {
  try {
    const response = await callApi('/api/settings/netinsight', { method: 'GET' })
    const payload = response?.data || {}
    Object.assign(credentialsSummary, payload.credentials || {})
    const runtime = payload.runtime || {}
    const planner = payload.planner || {}

    form.user = String(payload.credentials?.user || '')
    form.password = ''
    form.clearPassword = false
    form.headless = Boolean(runtime.headless)
    form.noProxy = Boolean(runtime.no_proxy)
    form.loginTimeoutMs = Number(runtime.login_timeout_ms || 120000)
    form.workerIdleSeconds = Number(runtime.worker_idle_seconds || 90)
    form.pageSize = Number(runtime.page_size || 50)
    form.sort = String(runtime.sort || 'comments_desc')
    form.infoType = String(runtime.info_type || '2')
    form.browserChannel = String(runtime.browser_channel || '')
    form.defaultDays = Number(planner.default_days || 30)
    form.defaultTotalLimit = Number(planner.default_total_limit || 500)
    form.defaultPlatformsText = Array.isArray(planner.default_platforms)
      ? planner.default_platforms.join(', ')
      : '微博'
  } catch (err) {
    feedback.type = 'error'
    feedback.message = err instanceof Error ? err.message : '读取 NetInsight 配置失败'
  }
}

async function submit() {
  loading.value = true
  feedback.type = ''
  feedback.message = ''
  try {
    const response = await callApi('/api/settings/netinsight', {
      method: 'PUT',
      body: JSON.stringify({
        user: form.user,
        password: form.password,
        clear_password: form.clearPassword,
        headless: form.headless,
        no_proxy: form.noProxy,
        login_timeout_ms: Number(form.loginTimeoutMs || 120000),
        worker_idle_seconds: Number(form.workerIdleSeconds || 90),
        page_size: Number(form.pageSize || 50),
        sort: form.sort,
        info_type: form.infoType,
        browser_channel: form.browserChannel,
        default_days: Number(form.defaultDays || 30),
        default_total_limit: Number(form.defaultTotalLimit || 500),
        default_platforms: defaultPlatforms.value,
      }),
    })
    Object.assign(credentialsSummary, response?.data?.credentials || {})
    feedback.type = 'success'
    feedback.message = 'NetInsight 配置已保存'
    form.password = ''
    form.clearPassword = false
  } catch (err) {
    feedback.type = 'error'
    feedback.message = err instanceof Error ? err.message : '保存 NetInsight 配置失败'
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  fetchSettings()
})
</script>
