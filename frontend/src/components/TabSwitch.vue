<script setup>
/**
 * TabSwitch - 统一的标签页切换组件
 *
 * 使用方式:
 * <TabSwitch :tabs="tabs" :active="activeTab" @change="activeTab = $event" />
 *
 * tabs 格式:
 * - 基础: [{ value: 'tab1', label: '标签1' }, ...]
 * - 带徽章: [{ value: 'tab1', label: '标签1', badge: '12' }, ...]
 * - 带图标: [{ value: 'tab1', label: '标签1', icon: Component }, ...]
 *
 * 支持 size: 'sm' | 'md' | 'lg'
 */
import { computed } from 'vue'

const props = defineProps({
  tabs: {
    type: Array,
    required: true
    // [{ value: string, label: string, badge?: string | number, icon?: Component }]
  },
  active: {
    type: String,
    required: true
  },
  size: {
    type: String,
    default: 'md',
    validator: (v) => ['sm', 'md', 'lg'].includes(v)
  }
})

const emit = defineEmits(['change'])

function selectTab(value) {
  if (value !== props.active) {
    emit('change', value)
  }
}

const sizeClass = computed(() => `tab-switch--${props.size}`)
</script>

<template>
  <div class="tab-switch" :class="sizeClass">
    <button
      v-for="tab in tabs"
      :key="tab.value"
      type="button"
      class="tab-switch-btn"
      :class="{ 'tab-switch-btn--active': active === tab.value }"
      @click="selectTab(tab.value)"
    >
      <component :is="tab.icon" v-if="tab.icon" class="h-4 w-4" />
      <span>{{ tab.label }}</span>
      <span
        v-if="tab.badge !== undefined"
        class="tab-switch-badge"
        :class="{ 'tab-switch-badge--active': active === tab.value }"
      >
        {{ tab.badge }}
      </span>
    </button>
  </div>
</template>