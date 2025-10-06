<template>
  <main class="app">
    <header class="app__header">
      <h1>Opinion System 前端</h1>
      <p>这里预留了与后端联动的空间，后续可根据业务需要进行扩展。</p>
    </header>
    <section class="app__content">
      <HelloWorld msg="欢迎使用 Vue 3 + Vite 开发环境" />
    </section>
  </main>
</template>

<script setup>
import HelloWorld from './components/HelloWorld.vue'
</script>

<style scoped>
.app {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  gap: 2rem;
  padding: 2rem;
  background: linear-gradient(180deg, #f6f8fb 0%, #ffffff 100%);
  color: #1f2933;
  font-family: 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif;
}

.app__header h1 {
  margin: 0;
  font-size: 2.25rem;
}

.app__header p {
  margin: 0.5rem 0 0;
  color: #52606d;
}

.app__content {
  background-color: #ffffff;
  border-radius: 16px;
  box-shadow: 0 20px 45px rgba(15, 23, 42, 0.08);
  padding: 2rem;
}
</style>
