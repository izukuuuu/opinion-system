<!--
  可折叠侧边栏组件 (CollapsibleSidebar)
  
  这是一个页面内部的可复用侧边栏结构组件，支持展开和收起两种状态。
  
  功能特性：
  - 支持展开/收起切换，展开时显示完整内容（包括描述文字），收起时仅显示图标和标题
  - 支持路由导航（RouterLink）和按钮两种模式
  - 支持自定义激活状态判断
  - 支持受控和非受控两种模式（通过 collapsed prop）
  
  可传入参数：
  - items: 侧边栏项数组，必填
    * 每个 item 可包含以下属性：
      - key: 唯一标识符（用于激活状态判断）
      - label: 显示标题（必填）
      - description: 描述文字（可选，仅在展开时显示）
      - icon: Vue 组件（图标组件，必填）
      - iconBg: 图标背景色类名（可选，默认 'bg-white/70'）
      - iconColor: 图标颜色类名（可选，默认 'text-brand-600'）
      - to: 路由对象或路径（可选，如果提供则渲染为 RouterLink，否则渲染为 button）
      - id: HTML id 属性（可选）
      - ariaControls: aria-controls 属性（可选）
  
  - activeKey: 当前激活项的 key 值（String | Number | null，可选）
  
  - collapsed: 是否收起状态（Boolean | null，可选）
    * null: 非受控模式，组件内部管理状态
    * boolean: 受控模式，由父组件控制状态
  
  - isActiveFn: 自定义激活状态判断函数（Function，可选）
    * 函数签名: (item) => boolean
    * 如果提供，将使用此函数判断激活状态，忽略 activeKey
  
  事件：
  - select: 当点击侧边栏项时触发，参数为被点击的 item 对象
  - update:collapsed: 当收起状态改变时触发（用于 v-model:collapsed 双向绑定）
-->
<template>
  <!-- 移动端：底部导航栏 -->
  <nav class="fixed inset-x-0 bottom-4 z-10 flex justify-center px-4 lg:hidden">
    <div class="mobile-pill-nav w-full max-w-xl">
      <div class="mobile-pill-nav__container">
      <component
        v-for="(item, index) in items"
        :key="itemKey(item, index)"
        :is="item.to ? RouterLink : 'button'"
        v-bind="itemProps(item)"
        class="group mobile-pill-nav__item focus-ring-accent"
        :class="mobileItemClasses(item)"
        role="tab"
        :aria-current="item.to ? (isItemActive(item) ? 'page' : undefined) : undefined"
        :aria-selected="!item.to ? isItemActive(item) : undefined"
        @click="handleSelect(item)"
      >
        <component :is="item.icon" class="mobile-pill-nav__icon" />
        <span>{{ item.label }}</span>
      </component>
      </div>
    </div>
  </nav>

  <!-- 桌面端：侧边栏 -->
  <aside
    class="hidden w-full shrink-0 flex-col gap-3 lg:flex lg:sticky lg:top-16"
    :class="isCollapsed ? 'lg:w-24' : 'lg:w-64'"
  >
    <div class="flex flex-col gap-3">
      <component
        v-for="(item, index) in items"
        :key="itemKey(item, index)"
        :is="item.to ? RouterLink : 'button'"
        v-bind="itemProps(item)"
        class="group rounded-2xl border transition focus-ring-accent"
        :class="itemClasses(item)"
        role="tab"
        :aria-current="item.to ? (isItemActive(item) ? 'page' : undefined) : undefined"
        :aria-selected="!item.to ? isItemActive(item) : undefined"
        @click="handleSelect(item)"
      >
        <div
          class="flex flex-1"
          :class="isCollapsed ? 'flex-col items-center gap-1 text-center' : 'items-center gap-3'"
        >
          <div
            class="rounded-xl p-2 shadow-sm"
            :class="[
              isCollapsed ? 'p-1.5' : '',
              item.iconBg || 'bg-white/70',
              item.iconColor || 'text-brand-600'
            ]"
          >
            <component :is="item.icon" class="h-5 w-5" />
          </div>
          <span
            class="flex flex-col text-muted transition-colors"
            :class="[
              isCollapsed
                ? 'items-center text-[11px] font-medium leading-tight text-secondary'
                : 'items-start gap-1 text-left'
            ]"
          >
            <span :class="isCollapsed ? 'text-[11px] font-semibold text-secondary' : 'font-semibold text-left'">
              {{ item.label }}
            </span>
            <span v-if="item.description && !isCollapsed" class="text-xs text-muted">
              {{ item.description }}
            </span>
          </span>
        </div>
        <ChevronRightIcon
          v-if="!isCollapsed"
          class="h-4 w-4 text-muted transition group-hover:text-brand-500"
        />
      </component>
    </div>
    <button
      type="button"
      class="mx-auto inline-flex h-8 w-8 items-center justify-center rounded-full border border-soft text-secondary/70 transition hover:text-secondary focus-ring-accent"
      @click="toggleCollapse"
      :aria-pressed="isCollapsed"
    >
      <ChevronLeftIcon class="h-4 w-4 transition-transform" :class="isCollapsed ? 'rotate-180' : ''" />
      <span class="sr-only">{{ isCollapsed ? '展开侧栏' : '收起侧栏' }}</span>
    </button>
  </aside>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import { ChevronLeftIcon, ChevronRightIcon } from '@heroicons/vue/24/outline'

/**
 * Props 定义
 */
const props = defineProps({
  /**
   * 侧边栏项数组，必填
   * 每个 item 对象可包含：key, label, description, icon, iconBg, iconColor, to, id, ariaControls
   */
  items: {
    type: Array,
    required: true
  },
  /**
   * 当前激活项的 key 值
   * 用于判断哪个侧边栏项处于激活状态
   */
  activeKey: {
    type: [String, Number, null],
    default: null
  },
  /**
   * 是否收起状态
   * null: 非受控模式，组件内部管理状态
   * boolean: 受控模式，由父组件控制状态（支持 v-model:collapsed）
   */
  collapsed: {
    type: Boolean,
    default: null
  },
  /**
   * 自定义激活状态判断函数
   * 如果提供，将使用此函数判断激活状态，忽略 activeKey
   * 函数签名: (item) => boolean
   */
  isActiveFn: {
    type: Function,
    default: null
  }
})

/**
 * 事件定义
 * @event select - 当点击侧边栏项时触发，参数为被点击的 item 对象
 * @event update:collapsed - 当收起状态改变时触发，用于 v-model:collapsed 双向绑定
 */
const emit = defineEmits(['select', 'update:collapsed'])

// 内部收起状态（用于非受控模式）
const internalCollapsed = ref(
  typeof props.collapsed === 'boolean' ? props.collapsed : false
)

// 监听外部 collapsed prop 的变化（受控模式）
watch(
  () => props.collapsed,
  (next) => {
    if (typeof next === 'boolean') {
      internalCollapsed.value = next
    }
  }
)

// 收起状态的 computed 属性，支持双向绑定
const isCollapsed = computed({
  get: () => (typeof props.collapsed === 'boolean' ? props.collapsed : internalCollapsed.value),
  set: (val) => {
    internalCollapsed.value = val
    emit('update:collapsed', val)
  }
})

/**
 * 切换收起/展开状态
 */
const toggleCollapse = () => {
  isCollapsed.value = !isCollapsed.value
}

/**
 * 获取侧边栏项的唯一 key
 * 优先级：item.key > item.label > item.to?.name > item.to > index
 */
const itemKey = (item, index) => item.key ?? item.label ?? item.to?.name ?? item.to ?? index

/**
 * 判断侧边栏项是否处于激活状态
 * 如果提供了 isActiveFn，则使用自定义函数判断
 * 否则使用 activeKey 与 item 的 key 或 label 进行比较
 */
const isItemActive = (item) => {
  if (props.isActiveFn) {
    return props.isActiveFn(item)
  }
  const key = item.key ?? item.label
  return key !== undefined && key === props.activeKey
}

/**
 * 处理侧边栏项点击事件
 */
const handleSelect = (item) => {
  emit('select', item)
}

/**
 * 获取侧边栏项的 props
 * 如果 item.to 存在，返回路由相关 props（用于 RouterLink）
 * 否则返回按钮相关 props
 */
const itemProps = (item) => {
  const base = {}
  if (item.id) base.id = item.id
  if (item.ariaControls) base['aria-controls'] = item.ariaControls
  if (item.to) {
    return { ...base, to: item.to }
  }
  return { ...base, type: 'button' }
}

/**
 * 获取侧边栏项的 CSS 类名
 * 根据激活状态和收起状态返回不同的样式类
 */
const itemClasses = (item) => {
  const activeClass = isItemActive(item)
    ? 'border-brand-soft bg-brand-soft text-brand-600 shadow-sm'
    : 'border-transparent bg-surface text-secondary hover:border-brand-soft hover:bg-accent-faint hover:text-brand-600'

  const sizeClass = isCollapsed.value
    ? 'flex flex-col items-center justify-center gap-1 px-1 py-4 text-xs'
    : 'inline-flex items-center justify-between gap-3 px-4 py-3 text-left text-sm'

  return [activeClass, sizeClass]
}

/**
 * 获取移动端底部导航栏项的 CSS 类名
 * 根据激活状态返回不同的样式类
 */
const mobileItemClasses = (item) => {
  return isItemActive(item) ? 'mobile-pill-nav__item--active' : ''
}
</script>

<style scoped>
.mobile-pill-nav__container {
  display: flex;
  align-items: center;
  gap: 0.35rem;
  padding: 0.45rem;
  border-radius: 1.5rem;
  border: 1px solid var(--color-border-soft);
  background-color: var(--color-bg-base-soft);
  box-shadow: 0 12px 36px rgb(12 18 28 / 0.12);
}

.mobile-pill-nav__item {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 0.2rem;
  padding: 0.35rem 0.4rem;
  border-radius: 1rem;
  font-size: 0.7rem;
  font-weight: 600;
  color: var(--color-text-muted);
  background-color: transparent;
  border: none;
  transition: background-color 0.25s ease, color 0.25s ease;
}

.mobile-pill-nav__item--active {
  background-color: rgb(var(--color-brand-100) / 1);
  color: var(--color-text-primary);
}

.mobile-pill-nav__icon {
  width: 1.5rem;
  height: 1.5rem;
  color: rgb(var(--color-brand-600) / 1);
}

.mobile-pill-nav__item--active .mobile-pill-nav__icon {
  color: rgb(var(--color-brand-700) / 1);
}
</style>