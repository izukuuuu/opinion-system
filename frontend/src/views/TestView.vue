<template>
  <section class="test-view">
    <header class="test-view__header">
      <BeakerIcon class="test-view__icon" />
      <div>
        <h1>接口调试工作区</h1>
        <p>在此快速验证 API，方便排查管线、查询及分析任务。</p>
      </div>
    </header>
    <ApiWorkbench />
  </section>
</template>

<script setup>
import { BeakerIcon } from '@heroicons/vue/24/outline'
import ApiWorkbench from '../components/ApiWorkbench.vue'
</script>

<style scoped>
.test-view {
  display: flex;
  flex-direction: column;
  gap: 2rem;
  padding: 2.5rem;
  background: rgba(255, 255, 255, 0.92);
  border-radius: 28px;
  border: 1px solid rgba(148, 163, 184, 0.16);
  box-shadow: 0 25px 60px -30px rgba(15, 23, 42, 0.35);
}

.test-view__header {
  display: flex;
  gap: 1.5rem;
  align-items: center;
}

.test-view__icon {
  width: 3rem;
  height: 3rem;
  color: #2563eb;
}

.test-view__header h1 {
  margin: 0;
  font-size: 2rem;
  font-weight: 700;
}

.test-view__header p {
  margin: 0.35rem 0 0;
  color: #475569;
  max-width: 640px;
}

@media (max-width: 640px) {
  .test-view {
    padding: 1.75rem;
    border-radius: 22px;
  }

  .test-view__header {
    flex-direction: column;
    align-items: flex-start;
  }

  .test-view__icon {
    width: 2.5rem;
    height: 2.5rem;
  }
}
</style>
