<template>
  <div v-if="state.visible" class="rag-cache-toast">
    <div class="rag-cache-toast__header">
      <span class="rag-cache-toast__title">正在准备检索资料</span>
      <span v-if="state.topic" class="rag-cache-toast__topic">{{ state.topic }}</span>
    </div>
    <p class="rag-cache-toast__message">
      {{ state.message || '正在整理内容，请稍候…' }}
    </p>
    <div class="rag-cache-toast__bar">
      <div class="rag-cache-toast__bar-fill" :style="{ width: `${progress}%` }"></div>
    </div>
    <div class="rag-cache-toast__percent">{{ progress }}%</div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  state: {
    type: Object,
    required: true
  }
})

const progress = computed(() => {
  const value = Number(props.state?.percent || 0)
  return Math.max(0, Math.min(100, Math.round(value)))
})
</script>

<style scoped>
.rag-cache-toast {
  position: fixed;
  right: 24px;
  bottom: 24px;
  width: 280px;
  border-radius: 16px;
  background: #0f172a;
  color: #f8fafc;
  padding: 14px 16px 12px;
  box-shadow: 0 12px 30px rgba(15, 23, 42, 0.3);
  z-index: 9999;
}

.rag-cache-toast__header {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 6px;
}

.rag-cache-toast__title {
  font-size: 13px;
  font-weight: 600;
}

.rag-cache-toast__topic {
  font-size: 11px;
  color: #cbd5f5;
}

.rag-cache-toast__message {
  font-size: 12px;
  color: #e2e8f0;
  line-height: 1.4;
  margin: 0 0 10px;
}

.rag-cache-toast__bar {
  width: 100%;
  height: 6px;
  border-radius: 999px;
  background: rgba(148, 163, 184, 0.3);
  overflow: hidden;
}

.rag-cache-toast__bar-fill {
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(90deg, #38bdf8, #6366f1);
  transition: width 0.4s ease;
}

.rag-cache-toast__percent {
  margin-top: 6px;
  text-align: right;
  font-size: 11px;
  color: #cbd5f5;
}
</style>
