<template>
  <section class="card-surface space-y-6 p-6">
    <header class="flex flex-wrap items-center justify-between gap-4">
      <div>
        <p class="text-xs font-semibold uppercase tracking-[0.35em] text-muted">颜色</p>
        <h1 class="text-xl font-semibold text-primary">主题颜色管理</h1>
        <p class="mt-2 max-w-3xl text-sm leading-6 text-secondary">
          调整系统主题色板以适配不同品牌形象。变更会立即应用到当前会话并保存在浏览器本地，可随时导入或导出 JSON 配置。
        </p>
      </div>
      <button
        type="button"
        class="inline-flex items-center gap-2 rounded-full border border-slate-200 px-4 py-2 text-sm font-semibold text-slate-600 transition hover:border-rose-200 hover:bg-rose-50 hover:text-rose-600"
        @click="confirmReset = true"
      >
        重设颜色
      </button>
    </header>

    <ThemeColorEditor ref="editorRef" />

    <AppModal
      v-model="confirmReset"
      title="确认重置"
      description="确定要将主题色恢复到默认配置吗？此操作会清除所有已保存的自定义颜色。"
      cancel-text="取消"
      confirm-text="重置"
      confirm-tone="danger"
      @confirm="handleReset"
      @cancel="handleCancelReset"
    />
  </section>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import AppModal from '../../components/AppModal.vue'
import ThemeColorEditor from './components/ThemeColorEditor.vue'

const confirmReset = ref(false)
const editorRef = ref(null)

onMounted(() => {
  editorRef.value?.refresh()
})

const handleReset = () => {
  confirmReset.value = false
  editorRef.value?.resetAll()
}

const handleCancelReset = () => {
  confirmReset.value = false
}
</script>
