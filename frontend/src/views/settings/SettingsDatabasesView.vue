<template>
  <section class="card-surface space-y-6 p-6">
    <header class="flex flex-wrap items-center justify-between gap-4">
      <div>
        <p
          class="text-xs font-semibold uppercase tracking-[0.4em] text-slate-400"
        >
          数据库
        </p>
        <h2 class="text-xl font-semibold text-slate-900">数据库连接管理</h2>
        <p class="text-sm text-slate-500">
          维护项目可用的数据库连接，并指定默认连接。
        </p>
      </div>
      <button
        type="button"
        class="inline-flex items-center gap-2 rounded-full border border-soft px-4 py-2 text-sm font-semibold text-slate-600 transition hover:border-indigo-200 hover:text-indigo-600"
        @click="openCreateDatabaseModal"
      >
        新增连接
      </button>
    </header>

    <p
      v-if="databaseState.error"
      class="rounded-2xl bg-rose-100 px-4 py-3 text-sm text-rose-600"
    >
      {{ databaseState.error }}
    </p>
    <p
      v-if="databaseState.message"
      class="rounded-2xl bg-emerald-100 px-4 py-3 text-sm text-emerald-600"
    >
      {{ databaseState.message }}
    </p>

    <ul v-if="databaseState.connections.length" class="space-y-4">
      <li
        v-for="connection in databaseState.connections"
        :key="connection.id"
        class="rounded-3xl border border-soft bg-white p-5 action-card"
      >
        <div class="flex flex-col gap-2">
          <div class="flex flex-wrap items-center gap-2">
            <h3 class="text-base font-semibold text-slate-900">
              {{ connection.name }}
            </h3>
            <span
              v-if="databaseState.active === connection.id"
              class="badge-soft bg-indigo-100 text-indigo-600"
              >默认</span
            >
          </div>
          <p class="text-sm text-slate-500">
            {{ connection.engine }} · {{ connection.url }}
          </p>
          <p class="text-sm text-slate-500">
            {{ connection.description || "暂无描述" }}
          </p>
        </div>
        <div class="mt-4 flex flex-wrap gap-2">
          <button
            v-if="databaseState.active !== connection.id"
            type="button"
            class="rounded-full border border-soft px-4 py-1.5 text-sm font-medium text-slate-600 transition hover:border-indigo-200 hover:text-indigo-600"
            @click="activateConnection(connection.id)"
          >
            设为默认
          </button>
          <button
            type="button"
            class="rounded-full border border-soft px-4 py-1.5 text-sm font-medium text-slate-600 transition hover:border-indigo-200 hover:text-indigo-600"
            @click="editDatabaseConnection(connection)"
          >
            编辑
          </button>
          <button
            type="button"
            class="rounded-full border border-rose-200 px-4 py-1.5 text-sm font-medium text-rose-600 transition hover:bg-rose-50 disabled:cursor-not-allowed disabled:opacity-60"
            :disabled="databaseState.active === connection.id"
            @click="deleteDatabaseConnection(connection.id)"
          >
            删除
          </button>
        </div>
      </li>
    </ul>
    <p
      v-else-if="!databaseState.loading"
      class="rounded-2xl bg-slate-100 px-4 py-3 text-sm text-slate-500"
    >
      尚未添加数据库连接。
    </p>
    <p
      v-if="databaseState.loading"
      class="rounded-2xl bg-slate-100 px-4 py-3 text-sm text-slate-500"
    >
      加载中…
    </p>

    <AppModal
      v-model="databaseModalVisible"
      eyebrow="数据库管理"
      :title="
        databaseModalMode === 'create' ? '新增数据库连接' : '编辑数据库连接'
      "
      :description="
        databaseModalMode === 'create'
          ? '为项目添加新的数据库连接，并可选择设为默认。'
          : '更新数据库连接信息，保存后即时生效。'
      "
      cancel-text="取消"
      :confirm-text="databaseModalMode === 'create' ? '新增连接' : '保存修改'"
      confirm-loading-text="保存中…"
      :confirm-loading="databaseFormState.saving"
      :confirm-disabled="databaseModalConfirmDisabled"
      :close-on-backdrop="!databaseFormState.saving"
      :show-close="!databaseFormState.saving"
      width="max-w-2xl"
      @cancel="handleDatabaseModalCancel"
      @confirm="handleDatabaseModalConfirm"
    >
      <p
        v-if="databaseFormState.error"
        class="rounded-2xl bg-rose-100 px-4 py-3 text-sm text-rose-600"
      >
        {{ databaseFormState.error }}
      </p>
      <form class="space-y-4" @submit.prevent>
        <div class="grid gap-4 md:grid-cols-2">
          <label class="flex flex-col gap-2 text-sm font-medium text-slate-600">
            <span>连接标识</span>
            <input
              v-model.trim="databaseForm.id"
              type="text"
              :disabled="databaseModalMode === 'edit'"
              placeholder="如：primary"
              class="rounded-2xl border border-slate-300 bg-white px-3 py-2 text-sm transition focus:border-indigo-300 focus:outline-none focus:ring-2 focus:ring-indigo-100 disabled:bg-slate-100 disabled:text-slate-400"
            />
          </label>
          <label class="flex flex-col gap-2 text-sm font-medium text-slate-600">
            <span>显示名称</span>
            <input
              v-model.trim="databaseForm.name"
              type="text"
              placeholder="如：主库"
              class="rounded-2xl border border-slate-300 bg-white px-3 py-2 text-sm transition focus:border-indigo-300 focus:outline-none focus:ring-2 focus:ring-indigo-100"
            />
          </label>
          <label class="flex flex-col gap-2 text-sm font-medium text-slate-600">
            <span>数据库类型</span>
            <input
              v-model.trim="databaseForm.engine"
              type="text"
              placeholder="如：mysql"
              class="rounded-2xl border border-slate-300 bg-white px-3 py-2 text-sm transition focus:border-indigo-300 focus:outline-none focus:ring-2 focus:ring-indigo-100"
            />
          </label>
          <label class="flex flex-col gap-2 text-sm font-medium text-slate-600">
            <span>连接 URL</span>
            <input
              v-model.trim="databaseForm.url"
              type="text"
              placeholder="如：mysql+pymysql://user:password@host:3306/db"
              class="rounded-2xl border border-slate-300 bg-white px-3 py-2 text-sm transition focus:border-indigo-300 focus:outline-none focus:ring-2 focus:ring-indigo-100"
            />
          </label>
          <label
            class="md:col-span-2 flex flex-col gap-2 text-sm font-medium text-slate-600"
          >
            <span>描述</span>
            <textarea
              v-model.trim="databaseForm.description"
              rows="3"
              placeholder="用途说明（可选）"
              class="rounded-2xl border border-slate-300 bg-white px-3 py-2 text-sm transition focus:border-indigo-300 focus:outline-none focus:ring-2 focus:ring-indigo-100"
            ></textarea>
          </label>
          <label
            class="flex items-center gap-2 text-sm font-medium text-slate-600 md:col-span-2"
          >
            <input
              v-model="databaseForm.set_active"
              type="checkbox"
              class="h-4 w-4 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
            />
            <span>保存后设为默认连接</span>
          </label>
        </div>
        <button type="submit" class="hidden" aria-hidden="true">
          隐藏提交按钮
        </button>
      </form>
    </AppModal>
  </section>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from "vue";
import AppModal from "../../components/AppModal.vue";
import { useApiBase } from "../../composables/useApiBase";

const { ensureApiBase } = useApiBase();
const buildApiUrl = async (path) => {
  const baseUrl = await ensureApiBase();
  return `${baseUrl}${path}`;
};

const databaseState = reactive({
  connections: [],
  loading: false,
  error: "",
  message: "",
  active: "",
});

const databaseModalVisible = ref(false);
const databaseModalMode = ref("create");
const databaseForm = reactive({
  id: "",
  name: "",
  engine: "",
  url: "",
  description: "",
  set_active: false,
});

const databaseFormState = reactive({
  saving: false,
  error: "",
});

const resetDatabaseForm = () => {
  databaseForm.id = "";
  databaseForm.name = "";
  databaseForm.engine = "";
  databaseForm.url = "";
  databaseForm.description = "";
  databaseForm.set_active = false;
};

const databaseModalConfirmDisabled = computed(() => {
  return (
    databaseFormState.saving ||
    !databaseForm.id ||
    !databaseForm.name ||
    !databaseForm.engine ||
    !databaseForm.url
  );
});

const fetchDatabaseConnections = async () => {
  databaseState.loading = true;
  databaseState.error = "";
  try {
    const endpoint = await buildApiUrl("/settings/databases");
    const response = await fetch(endpoint);
    if (!response.ok) {
      throw new Error("获取数据库连接失败");
    }
    const payload = await response.json();
    const result =
      payload && typeof payload === "object" ? payload.data ?? {} : {};
    const connections = Array.isArray(result.connections)
      ? result.connections
      : [];
    databaseState.connections = connections;
    databaseState.active =
      typeof result.active === "string" ? result.active : "";
  } catch (err) {
    databaseState.error =
      err instanceof Error ? err.message : "获取数据库连接失败";
  } finally {
    databaseState.loading = false;
  }
};

const openCreateDatabaseModal = () => {
  resetDatabaseForm();
  databaseModalMode.value = "create";
  databaseFormState.error = "";
  databaseModalVisible.value = true;
};

const editDatabaseConnection = (connection) => {
  if (!connection) return;
  databaseModalMode.value = "edit";
  databaseFormState.error = "";
  databaseForm.id = connection.id || "";
  databaseForm.name = connection.name || "";
  databaseForm.engine = connection.engine || "";
  databaseForm.url = connection.url || "";
  databaseForm.description = connection.description || "";
  databaseForm.set_active = databaseState.active === connection.id;
  databaseModalVisible.value = true;
};

const closeDatabaseModal = () => {
  databaseModalVisible.value = false;
  databaseModalMode.value = "create";
  databaseFormState.error = "";
  resetDatabaseForm();
};

const handleDatabaseModalCancel = () => {
  if (databaseFormState.saving) return;
  closeDatabaseModal();
};

const handleDatabaseModalConfirm = async () => {
  if (databaseFormState.saving) return;
  databaseFormState.error = "";

  const trimmed = {
    id: (databaseForm.id || "").trim(),
    name: (databaseForm.name || "").trim(),
    engine: (databaseForm.engine || "").trim(),
    url: (databaseForm.url || "").trim(),
    description: (databaseForm.description || "").trim(),
    set_active: databaseForm.set_active,
  };

  if (!trimmed.id) {
    databaseFormState.error = "标识不能为空";
    return;
  }
  if (!trimmed.name) {
    databaseFormState.error = "名称不能为空";
    return;
  }
  if (!trimmed.engine) {
    databaseFormState.error = "数据库类型不能为空";
    return;
  }
  if (!trimmed.url) {
    databaseFormState.error = "连接 URL 不能为空";
    return;
  }

  databaseFormState.saving = true;
  databaseState.message = "";

  try {
    const endpoint =
      databaseModalMode.value === "create"
        ? await buildApiUrl("/settings/databases")
        : await buildApiUrl(
            `/settings/databases/${encodeURIComponent(trimmed.id)}`
          );
    const method = databaseModalMode.value === "create" ? "POST" : "PUT";
    const response = await fetch(endpoint, {
      method,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(trimmed),
    });
    const result = await response.json().catch(() => ({}));
    if (!response.ok || result.status === "error") {
      const message =
        result && typeof result === "object" ? result.message : "";
      throw new Error(message || "保存数据库连接失败");
    }
    databaseState.message =
      databaseModalMode.value === "create" ? "新增连接成功" : "连接信息已更新";
    await fetchDatabaseConnections();
    closeDatabaseModal();
  } catch (err) {
    databaseFormState.error =
      err instanceof Error ? err.message : "保存数据库连接失败";
  }
  databaseFormState.saving = false;
};

const activateConnection = async (connectionId) => {
  databaseState.error = "";
  try {
    const endpoint = await buildApiUrl(
      `/settings/databases/${encodeURIComponent(connectionId)}/activate`
    );
    const response = await fetch(endpoint, {
      method: "POST",
    });
    if (!response.ok) {
      throw new Error("设置默认连接失败");
    }
    databaseState.message = "已设为默认连接";
    databaseState.active = connectionId;
  } catch (err) {
    databaseState.error =
      err instanceof Error ? err.message : "设置默认连接失败";
  }
};

const deleteDatabaseConnection = async (connectionId) => {
  if (!window.confirm("确定要删除该连接吗？")) return;
  databaseState.error = "";
  try {
    const endpoint = await buildApiUrl(
      `/settings/databases/${encodeURIComponent(connectionId)}`
    );
    const response = await fetch(endpoint, {
      method: "DELETE",
    });
    if (!response.ok) {
      throw new Error("删除数据库连接失败");
    }
    databaseState.message = "删除成功";
    await fetchDatabaseConnections();
  } catch (err) {
    databaseState.error =
      err instanceof Error ? err.message : "删除数据库连接失败";
  }
};

onMounted(() => {
  fetchDatabaseConnections();
});
</script>

<style scoped>
.action-card {
  border-radius: 14px !important;
}
</style>
