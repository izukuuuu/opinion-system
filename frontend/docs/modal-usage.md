# AppModal 使用说明

前端新增了一个可复用的模态框组件，便于在页面内展示确认与表单类弹窗。

## 组件位置
- 路径：`frontend/src/components/AppModal.vue`
- 默认导出：`AppModal`

## 快速上手
```vue
<script setup>
import { ref } from 'vue'
import AppModal from '@/components/AppModal.vue'

const showDemoModal = ref(false)

const handleConfirm = () => {
  // 执行确认逻辑
  showDemoModal.value = false
}
</script>

<template>
  <button @click="showDemoModal = true">打开模态框</button>

  <AppModal
    v-model="showDemoModal"
    title="操作提示"
    description="这里是对当前操作的说明文字。"
    cancel-text="取消"
    confirm-text="确认"
    @confirm="handleConfirm"
  >
    <!-- 可选：额外内容插槽 -->
    <p class="text-sm text-slate-500">
      需要展示的补充信息可以写在默认插槽中。
    </p>
  </AppModal>
</template>
```

## 样式与交互
- 模态框会在视口居中显示，背景带有轻微暗化与模糊效果。
- 右上角提供 `✕` 关闭按钮；当 `confirmLoading` 为 `true` 时，关闭按钮与取消按钮会自动禁用。
- Esc 键或点击遮罩（默认开启）也会触发取消行为。

## 关键 Props
- `model-value` / `v-model` (`Boolean`)：控制模态框显示。
- `title` (`String`)：主标题。
- `description` (`String`)：说明文字，可配合 `#description` 插槽自定义。
- `cancel-text` / `confirm-text` (`String`)：按钮文案。
- `confirm-tone` (`String`)：按钮配色，支持 `primary`（默认）、`danger`、`success`。
- `confirm-loading` (`Boolean`)：显示加载态，自动禁用按钮。
- `confirm-loading-text` (`String`)：加载状态时的文案。
- `close-on-backdrop` (`Boolean`)：是否允许点击遮罩关闭。
- 插槽：默认插槽（附加内容）；`#description`（自定义说明区域）。

## 项目删除弹窗
项目工作台页面（`ProjectBoardView.vue`）已接入该组件，实现了带危险状态的删除确认弹窗，相关逻辑可作为进一步扩展的参考。
