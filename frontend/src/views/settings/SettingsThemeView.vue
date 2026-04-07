<template>
  <section class="card-surface space-y-6 p-6">
    <header class="settings-toolbar">
      <div class="settings-page-header">
        <p class="settings-page-eyebrow">颜色</p>
        <h1 class="settings-page-title">主题颜色管理</h1>
        <p class="settings-page-desc max-w-3xl">
          切换后在当前会话中立即生效。
        </p>
      </div>
      <button
        type="button"
        class="btn-secondary px-4 py-2 text-sm text-danger"
        @click="confirmReset = true"
      >
        重设颜色
      </button>
    </header>

    <ThemeColorEditor ref="editorRef" />

    <AppModal
      v-model="confirmReset"
      title="确认重置"
      description="确定要恢复到 Baby Blue 默认主题吗？此操作会清除当前主题和所有手动微调。"
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
