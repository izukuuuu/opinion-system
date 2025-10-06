<template>
  <div class="app-shell">
    <header class="app-shell__header">
      <div class="app-shell__top">
        <RouterLink to="/" class="app-shell__brand">Opinion System</RouterLink>
        <nav class="app-shell__nav">
          <RouterLink
            v-for="link in navigationLinks"
            :key="link.label"
            :to="link.to"
            class="app-shell__link"
          >
            {{ link.label }}
          </RouterLink>
        </nav>
      </div>
      <p v-if="pageTitle" class="app-shell__subtitle">当前页面：{{ pageTitle }}</p>
    </header>
    <main class="app-shell__content">
      <RouterView />
    </main>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { RouterLink, RouterView, useRoute } from 'vue-router'

const navigationLinks = [
  { label: '项目面板', to: { name: 'projects' } },
  { label: '测试界面', to: { name: 'test' } }
]

const route = useRoute()

const pageTitle = computed(() => route.meta?.title ?? '')
</script>

<style scoped>
.app-shell {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  background: #f8fafc;
  color: #1f2933;
  font-family: 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif;
}

.app-shell__header {
  padding: 1.5rem 2rem 1rem;
  border-bottom: 1px solid rgba(15, 23, 42, 0.08);
  background: rgba(255, 255, 255, 0.85);
  backdrop-filter: blur(10px);
  position: sticky;
  top: 0;
  z-index: 10;
}

.app-shell__top {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 1.5rem;
  flex-wrap: wrap;
}

.app-shell__brand {
  font-size: 1.5rem;
  font-weight: 700;
  color: #1f2937;
  text-decoration: none;
}

.app-shell__nav {
  display: flex;
  gap: 1rem;
}

.app-shell__link {
  color: #475569;
  text-decoration: none;
  font-weight: 500;
  padding: 0.35rem 0.75rem;
  border-radius: 999px;
  transition: background 0.2s ease, color 0.2s ease;
}

.app-shell__link:hover {
  background: rgba(59, 130, 246, 0.12);
  color: #2563eb;
}

.app-shell__link.router-link-active,
.app-shell__link.router-link-exact-active {
  background: linear-gradient(135deg, rgba(59, 130, 246, 0.18), rgba(124, 58, 237, 0.18));
  color: #1f2937;
  font-weight: 600;
}

.app-shell__subtitle {
  margin: 1rem 0 0;
  color: #64748b;
  font-size: 0.95rem;
}

.app-shell__content {
  flex: 1;
  display: flex;
  flex-direction: column;
}

@media (max-width: 640px) {
  .app-shell__header {
    padding: 1.25rem 1.5rem 0.75rem;
  }

  .app-shell__nav {
    width: 100%;
    justify-content: flex-start;
    flex-wrap: wrap;
  }
}
</style>
