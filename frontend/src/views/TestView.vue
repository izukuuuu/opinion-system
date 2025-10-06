<template>
  <section class="test-view">
    <header class="test-view__header">
      <BeakerIcon class="test-view__icon" />
      <div>
        <h1>测试与验证空间</h1>
        <p>用于快速验证交互、组件以及与后端接口的对接情况，保持开发过程中的敏捷性。</p>
      </div>
    </header>
    <div class="test-view__content">
      <HelloWorld msg="欢迎访问测试界面" />
      <section class="test-view__tips">
        <h2>可用测试操作</h2>
        <ul>
          <li>在 <strong>项目数据</strong> 页面上传 Excel 或 CSV，观察生成的 PKL/JSON</li>
          <li>使用浏览器控制台查看 API 请求与响应</li>
          <li>根据需要在此处嵌入新的调试组件</li>
        </ul>
      </section>
    </div>
  </section>
</template>

<script setup>
import { BeakerIcon } from '@heroicons/vue/24/outline'
import HelloWorld from '../components/HelloWorld.vue'
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

.test-view__content {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 2rem;
}

.test-view__tips {
  background: rgba(248, 250, 252, 0.9);
  border-radius: 20px;
  padding: 1.5rem;
  border: 1px solid rgba(148, 163, 184, 0.14);
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.test-view__tips h2 {
  margin: 0;
  font-size: 1.25rem;
}

.test-view__tips ul {
  margin: 0;
  padding-left: 1.25rem;
  color: #475569;
  display: flex;
  flex-direction: column;
  gap: 0.6rem;
}

.test-view__tips strong {
  color: #1d4ed8;
}

@media (max-width: 640px) {
  .test-view {
    padding: 1.75rem;
    border-radius: 22px;
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
