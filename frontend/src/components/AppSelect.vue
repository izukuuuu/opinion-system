<script setup>
/**
 * AppSelect - 统一的自定义下拉选择组件
 *
 * 使用方式:
 * <AppSelect
 *   :options="[{ value: 'a', label: '选项A' }, ...]"
 *   :value="selectedValue"
 *   @change="selectedValue = $event"
 *   placeholder="请选择"
 * />
 *
 * 支持:
 * - searchable: 是否可搜索
 * - disabled: 是否禁用
 * - clearable: 是否可清空
 */
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ChevronDownIcon, XMarkIcon } from '@heroicons/vue/24/outline'

const props = defineProps({
  options: {
    type: Array,
    required: true
    // [{ value: string, label: string, disabled?: boolean }]
  },
  value: {
    type: String,
    default: ''
  },
  placeholder: {
    type: String,
    default: '请选择'
  },
  searchable: {
    type: Boolean,
    default: false
  },
  disabled: {
    type: Boolean,
    default: false
  },
  clearable: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['change'])

const isOpen = ref(false)
const searchQuery = ref('')
const selectedIndex = ref(-1)
const isSearchFocused = ref(false)
const triggerRef = ref(null)
const dropdownRef = ref(null)
const dropdownStyle = ref({})

const DROPDOWN_OFFSET = 6
const DROPDOWN_VIEWPORT_MARGIN = 12
const DEFAULT_DROPDOWN_MAX_HEIGHT = 280
const MIN_OPTIONS_HEIGHT = 120
const SEARCH_BAR_HEIGHT = 56

const selectedOption = computed(() =>
  props.options.find(opt => opt.value === props.value)
)

const displayLabel = computed(() =>
  selectedOption.value?.label || props.placeholder
)

const filteredOptions = computed(() => {
  if (!props.searchable || !searchQuery.value) return props.options
  const query = searchQuery.value.toLowerCase()
  return props.options.filter(opt =>
    opt.label.toLowerCase().includes(query)
  )
})

const isSearchActive = computed(() =>
  props.searchable && (isSearchFocused.value || searchQuery.value.trim().length > 0)
)

function toggleDropdown() {
  if (props.disabled) return
  isOpen.value = !isOpen.value
  if (isOpen.value && props.searchable) {
    searchQuery.value = ''
    selectedIndex.value = -1
  }
}

function closeDropdown() {
  isOpen.value = false
  searchQuery.value = ''
  selectedIndex.value = -1
  isSearchFocused.value = false
  dropdownStyle.value = {}
}

function selectOption(option) {
  if (option.disabled) return
  emit('change', option.value)
  closeDropdown()
}

function clearSelection() {
  emit('change', '')
}

function handleKeydown(e) {
  if (!isOpen.value) {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault()
      toggleDropdown()
    }
    return
  }

  const opts = filteredOptions.value

  switch (e.key) {
    case 'ArrowDown':
      e.preventDefault()
      selectedIndex.value = Math.min(selectedIndex.value + 1, opts.length - 1)
      break
    case 'ArrowUp':
      e.preventDefault()
      selectedIndex.value = Math.max(selectedIndex.value - 1, 0)
      break
    case 'Enter':
      e.preventDefault()
      if (selectedIndex.value >= 0 && opts[selectedIndex.value]) {
        selectOption(opts[selectedIndex.value])
      }
      break
    case 'Escape':
      e.preventDefault()
      closeDropdown()
      break
    case 'Tab':
      closeDropdown()
      break
  }
}

function handleClickOutside(e) {
  if (
    triggerRef.value &&
    dropdownRef.value &&
    !triggerRef.value.contains(e.target) &&
    !dropdownRef.value.contains(e.target)
  ) {
    closeDropdown()
  }
}

function updateDropdownPosition() {
  if (!triggerRef.value || !isOpen.value) return

  const rect = triggerRef.value.getBoundingClientRect()
  const viewportHeight = window.innerHeight
  const viewportWidth = window.innerWidth
  const horizontalMargin = DROPDOWN_VIEWPORT_MARGIN
  const verticalMargin = DROPDOWN_VIEWPORT_MARGIN

  const availableBelow = Math.max(
    viewportHeight - rect.bottom - DROPDOWN_OFFSET - verticalMargin,
    MIN_OPTIONS_HEIGHT
  )
  const availableAbove = Math.max(
    rect.top - DROPDOWN_OFFSET - verticalMargin,
    MIN_OPTIONS_HEIGHT
  )

  const shouldOpenAbove =
    availableBelow < DEFAULT_DROPDOWN_MAX_HEIGHT && availableAbove > availableBelow

  const dropdownMaxHeight = Math.min(
    DEFAULT_DROPDOWN_MAX_HEIGHT,
    shouldOpenAbove ? availableAbove : availableBelow
  )
  const optionsMaxHeight = Math.max(
    MIN_OPTIONS_HEIGHT,
    dropdownMaxHeight - (props.searchable ? SEARCH_BAR_HEIGHT : 0)
  )

  const width = Math.min(rect.width, viewportWidth - horizontalMargin * 2)
  const left = Math.min(
    Math.max(rect.left, horizontalMargin),
    viewportWidth - width - horizontalMargin
  )
  const top = shouldOpenAbove
    ? Math.max(verticalMargin, rect.top - dropdownMaxHeight - DROPDOWN_OFFSET)
    : Math.min(
        viewportHeight - dropdownMaxHeight - verticalMargin,
        rect.bottom + DROPDOWN_OFFSET
      )

  dropdownStyle.value = {
    top: `${top}px`,
    left: `${left}px`,
    width: `${width}px`,
    maxHeight: `${dropdownMaxHeight}px`,
    '--app-select-options-max-height': `${optionsMaxHeight}px`
  }
}

function handleViewportChange() {
  if (isOpen.value) {
    updateDropdownPosition()
  }
}

onMounted(() => {
  document.addEventListener('click', handleClickOutside)
  window.addEventListener('resize', handleViewportChange)
  window.addEventListener('scroll', handleViewportChange, true)
})

onBeforeUnmount(() => {
  document.removeEventListener('click', handleClickOutside)
  window.removeEventListener('resize', handleViewportChange)
  window.removeEventListener('scroll', handleViewportChange, true)
})

// Reset search when options change
watch(() => props.options, () => {
  if (isOpen.value) {
    searchQuery.value = ''
    selectedIndex.value = -1
    nextTick(updateDropdownPosition)
  }
})

watch(() => isOpen.value, async (open) => {
  if (!open) return
  await nextTick()
  updateDropdownPosition()
})
</script>

<template>
  <div class="app-select" :class="{ 'app-select--disabled': disabled }">
    <!-- Trigger -->
    <button
      ref="triggerRef"
      type="button"
      class="input app-select-trigger"
      :disabled="disabled"
      @click="toggleDropdown"
      @keydown="handleKeydown"
    >
      <span :class="{ 'app-select-placeholder': !selectedOption }">
        {{ displayLabel }}
      </span>
      <div class="app-select-icons">
        <XMarkIcon
          v-if="clearable && value && !disabled"
          class="app-select-clear"
          @click.stop="clearSelection"
        />
        <ChevronDownIcon
          class="app-select-arrow"
          :class="{ 'app-select-arrow--open': isOpen }"
        />
      </div>
    </button>

    <Teleport to="body">
      <Transition name="app-select-dropdown-transition">
        <!-- Dropdown -->
        <div
          v-if="isOpen"
          ref="dropdownRef"
          class="app-select-dropdown"
          :class="{ 'app-select-dropdown--search-active': isSearchActive }"
          :style="dropdownStyle"
        >
          <!-- Search -->
          <input
            v-if="searchable"
            v-model="searchQuery"
            type="text"
            class="app-select-search-input"
            placeholder="搜索..."
            @focus="isSearchFocused = true"
            @blur="isSearchFocused = false"
            @keydown="handleKeydown"
          />

          <!-- Options -->
          <div class="app-select-options">
            <button
              v-for="(option, idx) in filteredOptions"
              :key="option.value"
              type="button"
              class="app-select-option"
              :class="{
                'app-select-option--selected': value === option.value,
                'app-select-option--focused': selectedIndex === idx,
                'app-select-option--disabled': option.disabled
              }"
              :disabled="option.disabled"
              @click="selectOption(option)"
              @mouseenter="selectedIndex = idx"
            >
              {{ option.label }}
            </button>

            <div v-if="!filteredOptions.length" class="app-select-empty">
              {{ searchable ? '无匹配结果' : '暂无选项' }}
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>
