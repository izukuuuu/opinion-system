<template>
  <section class="card-surface space-y-6 p-6">
    <header class="settings-toolbar">
      <div class="settings-page-header">
        <p class="settings-page-eyebrow">
          数据库
        </p>
        <h2 class="settings-page-title">数据库连接管理</h2>
        <p class="settings-page-desc">
          维护项目可用的数据库连接，并指定默认连接。
        </p>
      </div>
      <button type="button"
        class="btn-secondary px-4 py-2 text-sm"
        @click="openCreateDatabaseModal">
        新增连接
      </button>
    </header>

    <p v-if="databaseState.error" class="settings-message-error">
      {{ databaseState.error }}
    </p>
    <p v-if="databaseState.message" class="settings-message-success">
      {{ databaseState.message }}
    </p>

    <ul v-if="databaseState.connections.length" class="space-y-4">
      <li v-for="connection in databaseState.connections" :key="connection.id"
        class="rounded-3xl border border-soft bg-surface p-5 action-card">
        <div class="flex flex-col gap-2">
          <div class="flex flex-wrap items-center gap-2">
            <h3 class="text-base font-semibold text-primary">
              {{ connection.name }}
            </h3>
            <span v-if="databaseState.active === connection.id"
              class="badge-brand">默认</span>
          </div>
          <p class="text-sm text-secondary">
            {{ connection.engine }} · {{ connection.url }}
          </p>
          <p class="text-sm text-secondary">
            主键：<code class="text-xs bg-surface-muted px-1 rounded">{{ connection.primary_key || 'id' }}</code>
          </p>
          <p class="text-sm text-secondary">
            {{ connection.description || "暂无描述" }}
          </p>
        </div>
        <div class="mt-4 flex flex-wrap gap-2">
          <button v-if="databaseState.active !== connection.id" type="button"
            class="btn-secondary px-4 py-1.5 text-sm font-medium"
            @click="activateConnection(connection.id)">
            设为默认
          </button>
          <button type="button"
            class="btn-secondary px-4 py-1.5 text-sm font-medium"
            @click="editDatabaseConnection(connection)">
            编辑
          </button>
          <button type="button"
            class="btn-secondary px-4 py-1.5 text-sm font-medium text-danger"
            :disabled="databaseState.active === connection.id" @click="deleteDatabaseConnection(connection.id)">
            删除
          </button>
        </div>
      </li>
    </ul>
    <p v-else-if="!databaseState.loading" class="settings-empty-state">
      尚未添加数据库连接。
    </p>
    <p v-if="databaseState.loading" class="settings-empty-state">
      加载中…
    </p>

    <AppModal v-model="databaseModalVisible" eyebrow="数据库管理" :title="databaseModalMode === 'create' ? '新增数据库连接' : '编辑数据库连接'
      " :description="databaseModalMode === 'create'
        ? '为项目添加新的数据库连接，并可选择设为默认。'
        : '更新数据库连接信息，保存后即时生效。'
        " cancel-text="取消" :confirm-text="databaseModalMode === 'create' ? '新增连接' : '保存修改'" confirm-loading-text="保存中…"
      :confirm-loading="databaseFormState.saving" :confirm-disabled="databaseModalConfirmDisabled"
      :close-on-backdrop="!databaseFormState.saving" :show-close="!databaseFormState.saving" width="max-w-2xl"
      @cancel="handleDatabaseModalCancel" @confirm="handleDatabaseModalConfirm">
      <p v-if="databaseFormState.error" class="settings-message-error">
        {{ databaseFormState.error }}
      </p>
      <form class="space-y-4" @submit.prevent>
        <!-- Mode Toggle -->
        <div class="flex justify-center pb-2">
          <TabSwitch
            :tabs="[{ value: 'structured', label: '配置模式' }, { value: 'url', label: 'URL 模式' }]"
            :active="databaseInputMode"
            @change="databaseInputMode = $event"
          />
        </div>

        <div class="max-h-[60vh] overflow-y-auto px-1 py-1">
          <div class="grid gap-4 md:grid-cols-2">
            <label class="flex flex-col gap-2 text-sm font-medium text-secondary">
              <span>连接标识</span>
              <input v-model.trim="databaseForm.id" type="text" :disabled="databaseModalMode === 'edit'"
                placeholder="如：primary"
                class="input disabled:bg-surface-muted disabled:text-muted" />
            </label>
            <label class="flex flex-col gap-2 text-sm font-medium text-secondary">
              <span>显示名称</span>
              <input v-model.trim="databaseForm.name" type="text" placeholder="如：主库"
                class="input" />
            </label>

            <label class="flex flex-col gap-2 text-sm font-medium text-secondary md:col-span-2">
              <span>数据库类型</span>
              <AppSelect
                :options="databaseEngineOptions"
                :value="databaseForm.engine"
                @change="handleEngineChange"
              />
            </label>

            <!-- Structured Mode Inputs -->
            <template v-if="databaseInputMode === 'structured'">
              <label class="flex flex-col gap-2 text-sm font-medium text-secondary">
                <span>服务器地址 (Host)</span>
                <input v-model.trim="databaseStructured.host" type="text" placeholder="localhost"
                  class="input" />
              </label>
              <label class="flex flex-col gap-2 text-sm font-medium text-secondary">
                <span>端口 (Port)</span>
                <input v-model.trim="databaseStructured.port" type="text" :placeholder="defaultPort"
                  class="input" />
              </label>
              <label class="flex flex-col gap-2 text-sm font-medium text-secondary">
                <span>用户名 (Username)</span>
                <input v-model.trim="databaseStructured.username" type="text" placeholder="root"
                  class="input" />
              </label>
              <label class="flex flex-col gap-2 text-sm font-medium text-secondary">
                <span>密码 (Password)</span>
                <input v-model.trim="databaseStructured.password" type="password" placeholder="password"
                  class="input" />
              </label>
              <label class="md:col-span-2 flex flex-col gap-2 text-sm font-medium text-secondary">
                <span>数据库名 (Database)</span>
                <input v-model.trim="databaseStructured.database" type="text" placeholder="db_name"
                  class="input" />
              </label>
            </template>

            <label v-if="databaseInputMode === 'url'"
              class="md:col-span-2 flex flex-col gap-2 text-sm font-medium text-secondary">
              <span>连接 URL</span>
              <input v-model.trim="databaseForm.url" type="text"
                placeholder="如：mysql+pymysql://user:password@host:3306/db"
                class="input" />
            </label>

            <!-- Readonly URL preview in structured mode -->
            <div v-else
              class="settings-help-block md:col-span-2 break-all text-xs">
              <span class="font-bold text-muted mr-2">PREVIEW</span>
              {{ databaseForm.url || '等待输入...' }}
            </div>

            <label class="flex flex-col gap-2 text-sm font-medium text-secondary">
              <span>主键字段</span>
              <input v-model.trim="databaseForm.primary_key" type="text" placeholder="id"
                class="input" />
              <span class="text-xs text-muted">数据表建表时使用的主键列名，默认为 <code>id</code></span>
            </label>

            <label class="md:col-span-2 flex flex-col gap-2 text-sm font-medium text-secondary">
              <span>描述</span>
              <textarea v-model.trim="databaseForm.description" rows="3" placeholder="用途说明（可选）"
                class="input"></textarea>
            </label>
            <AppCheckbox
              v-model="databaseForm.set_active"
              class="md:col-span-2"
              label-class="text-sm font-medium text-secondary"
            >
              保存后设为默认连接
            </AppCheckbox>
          </div>
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
import AppCheckbox from "../../components/AppCheckbox.vue";
import AppModal from "../../components/AppModal.vue";
import AppSelect from "../../components/AppSelect.vue";
import TabSwitch from "../../components/TabSwitch.vue";
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
// 'url' | 'structured'
const databaseInputMode = ref("structured");

const databaseForm = reactive({
  id: "",
  name: "",
  engine: "",
  url: "",
  primary_key: "",
  description: "",
  set_active: false,
});

const databaseStructured = reactive({
  host: "localhost",
  port: "",
  username: "",
  password: "",
  database: "",
});

const defaultPort = computed(() => {
  if (databaseForm.engine === "mysql") return "3306";
  if (databaseForm.engine === "postgresql") return "5432";
  return "";
});

// Auto-build URL when in structured mode
import { watch } from "vue";

const databaseEngineOptions = [
  { value: 'mysql', label: 'MySQL' },
  { value: 'postgresql', label: 'PostgreSQL' }
];

watch(
  [
    () => databaseInputMode.value,
    () => databaseForm.engine,
    databaseStructured,
  ],
  () => {
    if (databaseInputMode.value !== "structured") return;

    const { host, port, username, password, database } = databaseStructured;
    const engine = databaseForm.engine;

    // Only build if we have the basics
    if (!engine) return;

    let driver = "";
    if (engine === "mysql") driver = "mysql+pymysql";
    else if (engine === "postgresql") driver = "postgresql+psycopg2";
    else driver = engine; // fallback

    const p = port || defaultPort.value;
    const auth = username ? (password ? `${username}:${password}` : username) : "";
    const net = host ? (p ? `${host}:${p}` : host) : "";
    const db = database ? `/${database}` : "";

    if (auth && net) {
      databaseForm.url = `${driver}://${auth}@${net}${db}`;
    } else {
      // Partial or empty, maybe don't wipe it out immediately or set to prefix
      // databaseForm.url = `${driver}://...`; 
    }
  },
  { deep: true }
);

const handleEngineChange = (value) => {
  databaseForm.engine = value;
};

const databaseFormState = reactive({
  saving: false,
  error: "",
});

const resetDatabaseForm = () => {
  databaseForm.id = "";
  databaseForm.name = "";
  databaseForm.engine = "";
  databaseForm.url = "";
  databaseForm.primary_key = "";
  databaseForm.description = "";
  databaseForm.set_active = false;

  databaseInputMode.value = "structured";
  databaseStructured.host = "localhost";
  databaseStructured.port = "";
  databaseStructured.username = "";
  databaseStructured.password = "";
  databaseStructured.database = "";
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
  databaseInputMode.value = "url"; // Default to URL mode for editing to preserve exact string
  databaseFormState.error = "";
  databaseForm.id = connection.id || "";
  databaseForm.name = connection.name || "";
  databaseForm.engine = connection.engine || "";
  databaseForm.url = connection.url || "";
  databaseForm.primary_key = connection.primary_key || "";
  databaseForm.description = connection.description || "";
  databaseForm.set_active = databaseState.active === connection.id;

  // Optionally try to parse, but for now leave structured fields empty or default
  databaseStructured.host = "";
  databaseStructured.port = "";
  databaseStructured.username = "";
  databaseStructured.password = "";
  databaseStructured.database = "";

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
    primary_key: (databaseForm.primary_key || "").trim() || "id",
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
