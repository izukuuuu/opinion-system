<template>
  <div class="app-checkbox">
    <label :for="resolvedId" :class="['app-checkbox__label', labelClass]">
      <span class="app-checkbox__control">
        <input
          :id="resolvedId"
          :name="name"
          :checked="isChecked"
          :disabled="disabled"
          :required="required"
          :aria-label="ariaLabel"
          :class="['app-checkbox__input', inputClass]"
          type="checkbox"
          @change="handleChange"
        />
        <span class="app-checkbox__icon" aria-hidden="true">
          <svg viewBox="0 0 20 20" fill="currentColor" stroke="currentColor" stroke-width="1">
            <path
              fill-rule="evenodd"
              d="M16.707 5.293a1 1 0 0 1 0 1.414l-8 8a1 1 0 0 1-1.414 0l-4-4a1 1 0 1 1 1.414-1.414L8 12.586l7.293-7.293a1 1 0 0 1 1.414 0Z"
              clip-rule="evenodd"
            />
          </svg>
        </span>
      </span>
      <span v-if="$slots.default || label" :class="['app-checkbox__content', contentClass]">
        <slot>{{ label }}</slot>
      </span>
    </label>
  </div>
</template>

<script setup>
import { computed } from 'vue'

let checkboxId = 0

const props = defineProps({
  modelValue: {
    type: [Boolean, Array],
    default: false,
  },
  value: {
    type: [String, Number, Boolean],
    default: true,
  },
  id: {
    type: String,
    default: '',
  },
  name: {
    type: String,
    default: '',
  },
  label: {
    type: String,
    default: '',
  },
  ariaLabel: {
    type: String,
    default: '',
  },
  disabled: {
    type: Boolean,
    default: false,
  },
  required: {
    type: Boolean,
    default: false,
  },
  labelClass: {
    type: [String, Array, Object],
    default: '',
  },
  contentClass: {
    type: [String, Array, Object],
    default: '',
  },
  inputClass: {
    type: [String, Array, Object],
    default: '',
  },
})

const emit = defineEmits(['update:modelValue', 'change'])

const fallbackId = `app-checkbox-${++checkboxId}`

const resolvedId = computed(() => props.id || fallbackId)

const isChecked = computed(() => (
  Array.isArray(props.modelValue)
    ? props.modelValue.includes(props.value)
    : Boolean(props.modelValue)
))

function handleChange(event) {
  const checked = event.target.checked
  let nextValue

  if (Array.isArray(props.modelValue)) {
    const next = [...props.modelValue]
    const index = next.findIndex((item) => item === props.value)

    if (checked && index === -1) {
      next.push(props.value)
    } else if (!checked && index !== -1) {
      next.splice(index, 1)
    }

    nextValue = next
  } else {
    nextValue = checked
  }

  emit('update:modelValue', nextValue)
  emit('change', nextValue)
}
</script>

<style scoped>
.app-checkbox {
  display: inline-flex;
  max-width: 100%;
  vertical-align: middle;
}

.app-checkbox__label {
  display: inline-flex;
  align-items: center;
  gap: 0.625rem;
  max-width: 100%;
  cursor: pointer;
  position: relative;
  user-select: none;
}

.app-checkbox__control {
  position: relative;
  display: inline-flex;
  flex-shrink: 0;
}

.app-checkbox__input {
  width: 1.25rem;
  height: 1.25rem;
  appearance: none;
  border-radius: 0.375rem;
  border: 1px solid var(--color-border-soft);
  background-color: var(--color-surface);
  box-shadow:
    0 1px 2px rgb(15 23 42 / 0.06),
    inset 0 1px 0 rgb(255 255 255 / 0.55);
  transition:
    background-color 0.18s ease,
    border-color 0.18s ease,
    box-shadow 0.18s ease,
    transform 0.18s ease;
  cursor: pointer;
}

.app-checkbox__label:hover .app-checkbox__input:not(:disabled) {
  border-color: rgb(var(--color-brand-400) / 1);
  box-shadow:
    0 2px 6px rgb(var(--color-brand-900) / 0.08),
    inset 0 1px 0 rgb(255 255 255 / 0.7);
}

.app-checkbox__input:checked {
  border-color: rgb(var(--color-brand-700) / 1);
  background-color: rgb(var(--color-brand-700) / 1);
  box-shadow:
    0 1px 2px rgb(var(--color-brand-900) / 0.14),
    inset 0 1px 0 rgb(255 255 255 / 0.12);
}

.app-checkbox__label:hover .app-checkbox__input:checked:not(:disabled) {
  border-color: rgb(var(--color-brand-800) / 1);
  background-color: rgb(var(--color-brand-800) / 1);
  box-shadow:
    0 3px 8px rgb(var(--color-brand-900) / 0.16),
    inset 0 1px 0 rgb(255 255 255 / 0.16);
}

.app-checkbox__input:focus-visible {
  outline: 2px solid var(--color-focus-outline);
  outline-offset: 2px;
}

.app-checkbox__input:active:not(:disabled) {
  transform: scale(0.96);
}

.app-checkbox__input:disabled {
  cursor: not-allowed;
  opacity: 0.56;
  box-shadow: none;
}

.app-checkbox__icon {
  position: absolute;
  inset: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: var(--color-surface);
  opacity: 0;
  transform: scale(0.78);
  transition: opacity 0.16s ease, transform 0.16s ease;
  pointer-events: none;
}

.app-checkbox__input:checked + .app-checkbox__icon {
  opacity: 1;
  transform: scale(1);
}

.app-checkbox__icon svg {
  width: 0.875rem;
  height: 0.875rem;
}

.app-checkbox__content {
  min-width: 0;
}

.app-checkbox__label:has(.app-checkbox__input:disabled) {
  cursor: not-allowed;
}
</style>
