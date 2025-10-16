<template>
  <section class="hello">
    <h2>{{ msg }}</h2>
    <p>
      你可以在 <code>frontend</code> 目录中开发 Vue 3 前端，并通过环境变量或接口地址与后端交互。
      当前版本提供了项目面板与项目数据归档两大模块。
    </p>
    <ul>
      <li>运行 <code>npm install</code> 安装依赖（已包含 @heroicons/vue）</li>
      <li>执行 <code>npm run dev</code> 启动开发服务器</li>
      <li>前往“项目数据”上传 Excel/CSV/JSONL，即可生成对应的 JSONL 与 PKL 归档</li>
    </ul>
  </section>
</template>

<script setup>
defineProps({
  msg: {
    type: String,
    required: true
  }
})
</script>

<style scoped>
.hello {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

h2 {
  font-size: 1.5rem;
  margin: 0;
}

code {
  background-color: rgba(79, 70, 229, 0.08);
  padding: 0.1rem 0.4rem;
  border-radius: 0.25rem;
}
</style>
