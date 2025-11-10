<template>
  <section class="card-surface space-y-6 p-6">
    <header class="space-y-2">
      <p class="text-xs font-semibold uppercase tracking-[0.4em] text-slate-400">后端服务</p>
      <h2 class="text-xl font-semibold text-slate-900">后端地址配置</h2>
      <p class="text-sm text-slate-500">
        前端请求的 API 地址只在这里配置。默认使用 <code>http://127.0.0.1:8000</code>，你可以在部署时改成公网地址。
      </p>
    </header>

    <form class="space-y-4" @submit.prevent="handleSave">
      <label class="flex flex-col gap-2 text-sm font-medium text-slate-600">
        <span>后端基础地址（不带 /api）</span>
        <input
          v-model.trim="form.base"
          type="text"
          placeholder="例如：https://api.example.com:8000"
          class="rounded-2xl border border-slate-300 bg-white px-3 py-2 text-sm transition focus:border-indigo-300 focus:outline-none focus:ring-2 focus:ring-indigo-100"
        />
      </label>
      <div class="flex flex-wrap gap-3">
        <button
          type="submit"
          class="rounded-full bg-indigo-600 px-5 py-2 text-sm font-semibold text-white shadow transition hover:bg-indigo-500 disabled:opacity-60"
          :disabled="saving"
        >
          {{ saving ? '保存中…' : '保存配置' }}
        </button>
        <button
          type="button"
          class="rounded-full border border-slate-200 px-5 py-2 text-sm font-semibold text-slate-600 transition hover:border-indigo-200 hover:text-indigo-600 disabled:opacity-60"
          :disabled="saving"
          @click="resetToDefault"
        >
          恢复默认地址
        </button>
      </div>
    </form>

    <p v-if="message.success" class="rounded-2xl bg-emerald-100 px-4 py-3 text-sm text-emerald-600">
      {{ message.success }}
    </p>
    <p v-if="message.error" class="rounded-2xl bg-rose-100 px-4 py-3 text-sm text-rose-600">
      {{ message.error }}
    </p>

    <dl class="grid gap-4 rounded-2xl border border-slate-200 bg-white p-4 text-sm text-slate-600 md:grid-cols-2">
      <div>
        <dt class="text-xs uppercase tracking-[0.4em] text-slate-400">当前基础地址</dt>
        <dd class="mt-2 font-semibold text-slate-900">{{ backendBase }}</dd>
      </div>
      <div>
        <dt class="text-xs uppercase tracking-[0.4em] text-slate-400">API 请求前缀</dt>
        <dd class="mt-2 font-semibold text-slate-900">{{ apiBase }}</dd>
      </div>
    </dl>
  </section>
</template>

<script setup>
import { reactive, ref, watch } from 'vue'
import { useApiBase } from '../../composables/useApiBase'

const { backendBase, apiBase, setBackendBase, resetBackendBase } = useApiBase()

const form = reactive({
  base: backendBase.value
})

const saving = ref(false)
const message = reactive({
  success: '',
  error: ''
})

watch(backendBase, (value) => {
  form.base = value
})

const validateInput = () => {
  const value = form.base?.trim()
  if (!value) {
    message.error = '后端地址不能为空'
    message.success = ''
    return null
  }
  return value
}

const handleSave = () => {
  const value = validateInput()
  if (!value) return
  saving.value = true
  try {
    setBackendBase(value)
    message.success = '后端地址已保存'
    message.error = ''
  } catch (error) {
    message.error = error instanceof Error ? error.message : '保存失败'
    message.success = ''
  } finally {
    saving.value = false
  }
}

const resetToDefault = () => {
  saving.value = true
  try {
    resetBackendBase()
    message.success = '已恢复默认地址 http://127.0.0.1:8000'
    message.error = ''
  } finally {
    saving.value = false
  }
}
</script>
