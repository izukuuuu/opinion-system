<template>
  <section class="test-view">
    <h1>测试界面</h1>
    <HelloWorld msg="欢迎访问测试界面" />
  </section>
</template>

<script setup>
import HelloWorld from '../components/HelloWorld.vue'
</script>

<style scoped>
.test-view {
  max-width: 720px;
  margin: 3rem auto;
  padding: 2rem;
  background: rgba(248, 250, 252, 0.9);
  border-radius: 16px;
  box-shadow: 0 12px 32px rgba(15, 23, 42, 0.08);
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
}

h1 {
  margin: 0;
  font-size: 2rem;
  color: #1f2933;
}
</style>
