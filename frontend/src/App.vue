<template>
  <div class="app-shell" :class="{ 'app-shell--collapsed': sidebarCollapsed }">
    <aside
      class="app-shell__sidebar"
      :class="sidebarCollapsed ? 'app-shell__sidebar--collapsed' : 'app-shell__sidebar--expanded'"
    >
      <button
        type="button"
        class="app-shell__collapse-toggle"
        :aria-expanded="!sidebarCollapsed"
        :aria-label="sidebarToggleLabel"
        @click="toggleSidebar"
      >
        <component
          :is="sidebarCollapsed ? ChevronDoubleRightIcon : ChevronDoubleLeftIcon"
          class="app-shell__collapse-icon"
        />
      </button>
      <RouterLink
        v-if="!sidebarCollapsed"
        to="/"
        class="app-shell__brand app-shell__brand--expanded"
      >
        <span class="app-shell__logo">Opinion System</span>
        <span class="app-shell__tagline">舆情监测系统</span>
      </RouterLink>
      <RouterLink
        v-else
        to="/"
        class="app-shell__brand app-shell__brand--compact"
        aria-label="Opinion System"
        title="Opinion System"
      >
        <span class="app-shell__brand-mark" aria-hidden="true">OS</span>
        <span class="sr-only">Opinion System 舆情监测系统</span>
      </RouterLink>
      <div
        class="app-shell__nav-wrapper"
        :class="sidebarCollapsed ? 'app-shell__nav-wrapper--collapsed' : 'app-shell__nav-wrapper--expanded'"
      >
        <nav v-if="!sidebarCollapsed" class="app-shell__nav app-shell__nav--expanded">
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
        <nav v-else class="app-shell__nav app-shell__nav--compact">
          <RouterLink
            v-for="link in navigationLinks"
            :key="link.label"
            :to="link.to"
            class="app-shell__link app-shell__link--compact"
            :title="link.label"
            :aria-label="link.label"
          >
            <component :is="link.icon" class="app-shell__icon app-shell__icon--compact" />
            <span class="sr-only">{{ link.label }}</span>
          </RouterLink>
        </nav>
      </div>
    </aside>
    <div class="app-shell__main">
      <header class="app-shell__header">
        <div class="app-shell__header-bar">
          <p class="app-shell__breadcrumbs">项目制控制台</p>
          <div class="app-shell__active-project" role="status" aria-live="polite">
            <BriefcaseIcon class="app-shell__active-project-icon" aria-hidden="true" />
            <span class="app-shell__active-project-label">当前项目</span>
            <span class="app-shell__active-project-name">
              {{ activeProjectName || '未选择项目' }}
            </span>
          </div>
        </div>
        <h1 class="app-shell__title">{{ pageTitle || '欢迎使用 Opinion System' }}</h1>
      </header>
      <main class="app-shell__content">
        <RouterView />
      </main>
    </div>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { RouterLink, RouterView, useRoute } from 'vue-router'
import {
  BeakerIcon,
  BriefcaseIcon,
  ChevronDoubleLeftIcon,
  ChevronDoubleRightIcon,
  Cog6ToothIcon,
  DocumentArrowUpIcon,
  Squares2X2Icon
} from '@heroicons/vue/24/outline'
import { useActiveProject } from './composables/useActiveProject'

const navigationLinks = [
  {
    label: '项目面板',
    description: '查看项目记录',
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
    description: 'API调用测试',
    to: { name: 'test' },
    icon: BeakerIcon
  },
  {
    label: '系统设置',
    description: '配置数据库与模型参数',
    to: { name: 'settings' },
    icon: Cog6ToothIcon
  }
]

const route = useRoute()

const pageTitle = computed(() => route.meta?.title ?? '')

const { activeProjectName } = useActiveProject()

const sidebarCollapsed = ref(false)

const toggleSidebar = () => {
  sidebarCollapsed.value = !sidebarCollapsed.value
}

const sidebarToggleLabel = computed(() =>
  sidebarCollapsed.value ? '展开侧边栏' : '收起侧边栏'
)
</script>

<style scoped>
.app-shell {
  --sidebar-width: 280px;
  --sidebar-collapsed-width: 92px;
  min-height: 100vh;
  display: flex;
  background: linear-gradient(120deg, #f8fafc 0%, #eef2ff 35%, #f8fafc 100%);
  color: #0f172a;
  font-family: 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif;
}

.app-shell--collapsed {
  --sidebar-width: var(--sidebar-collapsed-width);
}

.app-shell__sidebar {
  width: var(--sidebar-width);
  position: fixed;
  top: 0;
  left: 0;
  bottom: 0;
  height: 100vh;
  display: flex;
  flex-direction: column;
  background: rgba(15, 23, 42, 0.96);
  color: rgba(241, 245, 249, 0.95);
  box-shadow: inset -1px 0 0 rgba(148, 163, 184, 0.18);
  transition: padding 0.3s ease, gap 0.3s ease;
  box-sizing: border-box;
  align-items: center;
}

.app-shell__sidebar--expanded {
  padding: 3.5rem 2rem 2.5rem;
  gap: 2rem;
  overflow-y: auto;
  align-items: stretch;
}

.app-shell__sidebar--collapsed {
  padding: 3rem 1.25rem 2rem;
  gap: 2rem;
  align-items: center;
  overflow-y: hidden;
}

.app-shell__collapse-toggle {
  border: none;
  background: rgba(148, 163, 184, 0.16);
  color: rgba(241, 245, 249, 0.86);
  width: 2.25rem;
  height: 2.25rem;
  border-radius: 999px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: background 0.25s ease;
}

.app-shell__sidebar--collapsed .app-shell__collapse-toggle {
  align-self: center;
}

.app-shell__sidebar--expanded .app-shell__collapse-toggle {
  align-self: flex-end;
}

.app-shell__collapse-toggle:hover {
  background: rgba(148, 163, 184, 0.28);
}

.app-shell__collapse-icon {
  width: 1.25rem;
  height: 1.25rem;
}

.app-shell__brand {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  color: inherit;
  transition: opacity 0.25s ease;
  text-decoration: none;
}

.app-shell__brand--expanded {
  align-items: flex-start;
}

.app-shell__brand--compact {
  align-items: center;
  justify-content: center;
  width: 100%;
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
  transition: opacity 0.2s ease;
}

.app-shell__brand-mark {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 2.5rem;
  height: 2.5rem;
  border-radius: 0.85rem;
  background: linear-gradient(135deg, rgba(59, 130, 246, 0.65), rgba(129, 140, 248, 0.75));
  color: #f8fafc;
  font-weight: 700;
  letter-spacing: 0.2em;
  font-size: 0.95rem;
  text-transform: uppercase;
  box-shadow: 0 12px 30px rgba(15, 23, 42, 0.28);
}

.app-shell__nav {
  display: flex;
  flex-direction: column;
  width: 100%;
}

.app-shell__nav-wrapper {
  margin-top: auto;
  width: 100%;
  display: flex;
  justify-content: stretch;
}

.app-shell__nav-wrapper--collapsed {
  justify-content: center;
}

.app-shell__nav--expanded {
  gap: 0.75rem;
}

.app-shell__nav--compact {
  gap: 0.75rem;
  align-items: center;
}

.app-shell__link {
  display: flex;
  gap: 0.9rem;
  align-items: center;
  padding: 0.75rem 0.9rem;
  border-radius: 16px;
  color: inherit;
  background: transparent;
  transition: background 0.2s ease;
}


.app-shell__link--compact {
  justify-content: center;
  padding: 0.65rem 0;
  width: 100%;
}

.app-shell__link:hover {
  background: rgba(148, 163, 184, 0.12);
}

.router-link-active.app-shell__link,
.router-link-exact-active.app-shell__link {
  background: linear-gradient(135deg, rgba(59, 130, 246, 0.35), rgba(129, 140, 248, 0.35));
  color: #f8fafc;
  box-shadow: 0 18px 45px rgba(15, 23, 42, 0.35);
}

.app-shell__link--compact.router-link-active,
.app-shell__link--compact.router-link-exact-active {
  transform: none;
}

.app-shell__icon {
  width: 1.5rem;
  height: 1.5rem;
}

.app-shell__icon--compact {
  width: 1.75rem;
  height: 1.75rem;
}

.app-shell__link-text {
  display: flex;
  flex-direction: column;
  gap: 0.1rem;
  transition: opacity 0.2s ease;
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

.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}

.app-shell__main {
  margin-left: var(--sidebar-width);
  display: flex;
  flex-direction: column;
  min-height: 100vh;
  transition: margin-left 0.3s ease;
}

.app-shell__header {
  padding: 2.5rem 3rem 2rem;
  display: flex;
  flex-direction: column;
  gap: 0.9rem;
}

.app-shell__header-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  flex-wrap: wrap;
}

.app-shell__breadcrumbs {
  margin: 0;
  font-size: 0.85rem;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: #64748b;
}

.app-shell__active-project {
  display: inline-flex;
  align-items: center;
  gap: 0.45rem;
  padding: 0.35rem 0.75rem;
  border-radius: 999px;
  background: rgba(59, 130, 246, 0.08);
  color: #1d4ed8;
  font-size: 0.9rem;
}

.app-shell__active-project-icon {
  width: 1.1rem;
  height: 1.1rem;
}

.app-shell__active-project-label {
  font-weight: 600;
  letter-spacing: 0.05em;
}

.app-shell__active-project-name {
  font-weight: 600;
  color: #1e3a8a;
}

.app-shell__title {
  margin: 0;
  font-size: 2rem;
  font-weight: 700;
  color: #1f2937;
}

.app-shell__content {
  flex: 1;
  padding: 0 clamp(2rem, 5vw, 6rem) clamp(2.5rem, 6vw, 6rem);
  display: flex;
  flex-direction: column;
  align-items: center;
  width: 100%;
  box-sizing: border-box;
  gap: 2rem;
}

.app-shell__content > * {
  width: min(1400px, 100%);
}

@media (max-width: 960px) {
  .app-shell {
    flex-direction: column;
  }

  .app-shell__sidebar {
    position: relative;
    width: 100%;
    height: auto;
    padding: 1.75rem 1.5rem 1.25rem;
    flex-direction: column;
    align-items: flex-start;
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

  .app-shell__main {
    margin-left: 0;
    min-height: auto;
  }

  .app-shell__header {
    padding: 2rem 1.75rem 1.5rem;
  }

  .app-shell__content {
    padding: 0 1.75rem 2rem;
    align-items: stretch;
    gap: 1.5rem;
  }

  .app-shell__content > * {
    width: 100%;
  }

  .app-shell__collapse-toggle {
    display: none;
  }
}

@media (max-width: 640px) {
  .app-shell__sidebar {
    padding: 1.5rem 1.25rem;
  }

  .app-shell__header {
    padding: 1.5rem 1.25rem 1.25rem;
  }

  .app-shell__active-project {
    width: 100%;
    justify-content: center;
  }

  .app-shell__content {
    padding: 0 1.25rem 1.75rem;
    gap: 1.5rem;
  }
}
</style>
