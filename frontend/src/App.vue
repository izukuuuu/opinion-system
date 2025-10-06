<template>
  <div class="app-shell">
    <aside class="app-shell__sidebar">
      <RouterLink to="/" class="app-shell__brand">
        <span class="app-shell__logo">Opinion System</span>
        <span class="app-shell__tagline">项目制舆情工作台</span>
      </RouterLink>
      <nav class="app-shell__nav">
        <RouterLink
          v-for="link in navigationLinks"
          :key="link.label"
          :to="link.to"
          class="app-shell__link"
        >
          <component :is="link.icon" class="app-shell__icon" />
          <div class="app-shell__link-text">
            <span class="app-shell__link-label">{{ link.label }}</span>
            <span class="app-shell__link-description">{{ link.description }}</span>
          </div>
        </RouterLink>
      </nav>
    </aside>
    <div class="app-shell__main">
      <header class="app-shell__header">
        <p class="app-shell__breadcrumbs">项目制控制台</p>
        <h1 class="app-shell__title">{{ pageTitle || '欢迎使用 Opinion System' }}</h1>
      </header>
      <main class="app-shell__content">
        <RouterView />
      </main>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { RouterLink, RouterView, useRoute } from 'vue-router'
import { BeakerIcon, DocumentArrowUpIcon, Squares2X2Icon } from '@heroicons/vue/24/outline'

const navigationLinks = [
  {
    label: '项目面板',
    description: '查看项目整体进度与执行记录',
    to: { name: 'projects' },
    icon: Squares2X2Icon
  },
  {
    label: '项目数据',
    description: '导入 Excel 并生成数据存档',
    to: { name: 'project-data' },
    icon: DocumentArrowUpIcon
  },
  {
    label: '测试页面',
    description: '用于验证交互与组件效果',
    to: { name: 'test' },
    icon: BeakerIcon
  }
]

const route = useRoute()

const pageTitle = computed(() => route.meta?.title ?? '')
</script>

<style scoped>
.app-shell {
  min-height: 100vh;
  display: grid;
  grid-template-columns: 280px 1fr;
  background: linear-gradient(120deg, #f8fafc 0%, #eef2ff 35%, #f8fafc 100%);
  color: #0f172a;
  font-family: 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif;
}

.app-shell__sidebar {
  position: sticky;
  top: 0;
  align-self: stretch;
  padding: 2.5rem 2rem;
  display: flex;
  flex-direction: column;
  gap: 2rem;
  background: rgba(15, 23, 42, 0.96);
  color: rgba(241, 245, 249, 0.95);
  box-shadow: inset -1px 0 0 rgba(148, 163, 184, 0.18);
}

.app-shell__brand {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  color: inherit;
}

.app-shell__logo {
  font-weight: 700;
  font-size: 1.4rem;
}

.app-shell__tagline {
  font-size: 0.85rem;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: rgba(226, 232, 240, 0.7);
}

.app-shell__nav {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.app-shell__link {
  display: flex;
  gap: 0.9rem;
  align-items: center;
  padding: 0.75rem 0.9rem;
  border-radius: 16px;
  color: inherit;
  background: transparent;
  transition: background 0.2s ease, transform 0.2s ease;
}

.app-shell__link:hover {
  background: rgba(148, 163, 184, 0.12);
  transform: translateX(4px);
}

.router-link-active.app-shell__link,
.router-link-exact-active.app-shell__link {
  background: linear-gradient(135deg, rgba(59, 130, 246, 0.35), rgba(129, 140, 248, 0.35));
  color: #f8fafc;
  box-shadow: 0 18px 45px rgba(15, 23, 42, 0.35);
}

.app-shell__icon {
  width: 1.5rem;
  height: 1.5rem;
}

.app-shell__link-text {
  display: flex;
  flex-direction: column;
  gap: 0.1rem;
}

.app-shell__link-label {
  font-weight: 600;
}

.app-shell__link-description {
  font-size: 0.75rem;
  color: rgba(226, 232, 240, 0.7);
}

.router-link-active .app-shell__link-description,
.router-link-exact-active .app-shell__link-description {
  color: rgba(248, 250, 252, 0.85);
}

.app-shell__main {
  display: flex;
  flex-direction: column;
  min-height: 100vh;
}

.app-shell__header {
  padding: 2.5rem 3rem 2rem;
  display: flex;
  flex-direction: column;
  gap: 0.6rem;
}

.app-shell__breadcrumbs {
  margin: 0;
  font-size: 0.85rem;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: #64748b;
}

.app-shell__title {
  margin: 0;
  font-size: 2rem;
  font-weight: 700;
  color: #1f2937;
}

.app-shell__content {
  flex: 1;
  padding: 0 3rem 3rem;
  display: flex;
  flex-direction: column;
}

@media (max-width: 960px) {
  .app-shell {
    grid-template-columns: 1fr;
  }

  .app-shell__sidebar {
    position: relative;
    flex-direction: row;
    align-items: center;
    justify-content: space-between;
    padding: 1.75rem 1.5rem;
    gap: 1.5rem;
  }

  .app-shell__nav {
    flex-direction: row;
    flex-wrap: wrap;
    gap: 0.5rem;
  }

  .app-shell__link {
    border-radius: 12px;
    padding: 0.6rem 0.75rem;
  }

  .app-shell__link-text {
    display: none;
  }

  .app-shell__main {
    min-height: auto;
  }

  .app-shell__header {
    padding: 2rem 1.75rem 1.5rem;
  }

  .app-shell__content {
    padding: 0 1.75rem 2rem;
  }
}

@media (max-width: 640px) {
  .app-shell__sidebar {
    padding: 1.5rem 1.25rem;
  }

  .app-shell__header {
    padding: 1.5rem 1.25rem 1.25rem;
  }

  .app-shell__content {
    padding: 0 1.25rem 1.75rem;
  }
}
</style>
