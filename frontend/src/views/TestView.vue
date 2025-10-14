<template>
  <section class="test-view">
    <header class="test-view__header">
      <BeakerIcon class="test-view__icon" />
      <div>
        <h1>接口调试工作区</h1>
        <p>在此快速验证 API，方便排查管线、查询及分析任务。</p>
      </div>
    </header>
    <nav class="test-view__tabs" role="tablist">
      <button
        v-for="tab in tabs"
        :key="tab.id"
        class="test-view__tab"
        :class="{ 'is-active': tab.id === activeTab }"
        type="button"
        role="tab"
        :aria-selected="tab.id === activeTab"
        @click="activate(tab.id)"
      >
        {{ tab.label }}
      </button>
    </nav>
    <component :is="activeComponent" />
  </section>
</template>

<script setup>
import { computed, ref } from 'vue'
import { BeakerIcon } from '@heroicons/vue/24/outline'
import ApiWorkbench from '../components/ApiWorkbench.vue'
import AnalyzeWorkbench from '../components/AnalyzeWorkbench.vue'

const tabs = [
  { id: 'api', label: '接口调试', component: ApiWorkbench },
  { id: 'analyze', label: 'Analyze 分析', component: AnalyzeWorkbench }
]

const activeTab = ref('api')

const activate = (id) => {
  activeTab.value = id
}

const activeComponent = computed(() => {
  const current = tabs.find((tab) => tab.id === activeTab.value)
  return current ? current.component : ApiWorkbench
})
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
  width: 100%;
  box-sizing: border-box;
}

.test-view__tabs {
  display: inline-flex;
  gap: 0.5rem;
  background: rgba(248, 250, 252, 0.75);
  padding: 0.4rem;
  border-radius: 999px;
  border: 1px solid rgba(148, 163, 184, 0.2);
  width: fit-content;
}

.test-view__tab {
  border: none;
  background: transparent;
  color: #475569;
  font-weight: 600;
  padding: 0.45rem 1.1rem;
  border-radius: 999px;
  cursor: pointer;
  transition: background 0.2s ease, color 0.2s ease, transform 0.2s ease;
}

.test-view__tab.is-active {
  background: linear-gradient(135deg, #2563eb 0%, #7c3aed 100%);
  color: #fff;
  box-shadow: 0 12px 24px rgba(37, 99, 235, 0.25);
}

.test-view__tab:not(.is-active):hover {
  transform: translateY(-1px);
  color: #1d4ed8;
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

  .test-view__tabs {
    width: 100%;
    justify-content: space-between;
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
