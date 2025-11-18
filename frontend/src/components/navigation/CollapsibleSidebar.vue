<template>
  <aside
    class="flex w-full shrink-0 flex-col gap-3 lg:sticky lg:top-16"
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
          <div class="rounded-xl bg-white/70 p-2 text-brand-600 shadow-sm" :class="isCollapsed ? 'p-1.5' : ''">
            <component :is="item.icon" class="h-4 w-4" />
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

const props = defineProps({
  items: {
    type: Array,
    required: true
  },
  activeKey: {
    type: [String, Number, null],
    default: null
  },
  collapsed: {
    type: Boolean,
    default: null
  },
  isActiveFn: {
    type: Function,
    default: null
  }
})

const emit = defineEmits(['select', 'update:collapsed'])

const internalCollapsed = ref(
  typeof props.collapsed === 'boolean' ? props.collapsed : false
)

watch(
  () => props.collapsed,
  (next) => {
    if (typeof next === 'boolean') {
      internalCollapsed.value = next
    }
  }
)

const isCollapsed = computed({
  get: () => (typeof props.collapsed === 'boolean' ? props.collapsed : internalCollapsed.value),
  set: (val) => {
    internalCollapsed.value = val
    emit('update:collapsed', val)
  }
})

const toggleCollapse = () => {
  isCollapsed.value = !isCollapsed.value
}

const itemKey = (item, index) => item.key ?? item.label ?? item.to?.name ?? item.to ?? index

const isItemActive = (item) => {
  if (props.isActiveFn) {
    return props.isActiveFn(item)
  }
  const key = item.key ?? item.label
  return key !== undefined && key === props.activeKey
}

const handleSelect = (item) => {
  emit('select', item)
}

const itemProps = (item) => {
  const base = {}
  if (item.id) base.id = item.id
  if (item.ariaControls) base['aria-controls'] = item.ariaControls
  if (item.to) {
    return { ...base, to: item.to }
  }
  return { ...base, type: 'button' }
}

const itemClasses = (item) => {
  const activeClass = isItemActive(item)
    ? 'border-brand-soft bg-brand-soft text-brand-600 shadow-sm'
    : 'border-transparent bg-surface text-secondary hover:border-brand-soft hover:bg-accent-faint hover:text-brand-600'

  const sizeClass = isCollapsed.value
    ? 'flex flex-col items-center justify-center gap-1 px-1 py-4 text-xs'
    : 'inline-flex items-center justify-between gap-3 px-4 py-3 text-left text-sm'

  return [activeClass, sizeClass]
}
</script>
