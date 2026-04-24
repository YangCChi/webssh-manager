<template>
  <div class="page-view">
    <div class="page-header">
      <el-button @click="$router.push('/')"><el-icon><ArrowLeft /></el-icon> 返回</el-button>
      <h2>操作审计日志</h2>
      <el-select v-model="actionFilter" clearable placeholder="操作类型" size="small" style="width: 140px">
        <el-option v-for="a in actionTypes" :key="a.value" :label="a.label" :value="a.value" />
      </el-select>
    </div>

    <el-table :data="logs" v-loading="loading" class="log-table">
      <el-table-column label="时间" width="170">
        <template #default="{ row }">
          {{ new Date(row.created_at * 1000).toLocaleString() }}
        </template>
      </el-table-column>
      <el-table-column label="操作" width="120">
        <template #default="{ row }">
          <el-tag :type="actionTagType(row.action)" size="small">{{ actionLabel(row.action) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="服务器" width="160" prop="server_name" />
      <el-table-column label="主机" width="160" prop="server_host" />
      <el-table-column label="详情" prop="detail" />
      <el-table-column label="IP" width="130" prop="ip_address" />
    </el-table>

    <el-pagination
      v-model:current-page="page"
      :total="total"
      :page-size="50"
      layout="total, prev, pager, next"
      style="padding: 16px; text-align: right"
      @current-change="loadLogs"
    />
  </div>
</template>

<script setup>
import { ref, watch, onMounted } from 'vue'
import { ArrowLeft } from '@element-plus/icons-vue'
import api from '@/utils/api'

const logs = ref([])
const loading = ref(false)
const page = ref(1)
const total = ref(0)
const actionFilter = ref('')

const actionTypes = [
  { value: 'connect', label: '连接' },
  { value: 'disconnect', label: '断开' },
  { value: 'batch_command', label: '批量命令' },
  { value: 'login', label: '登录' },
  { value: 'login_failed', label: '登录失败' },
]

function actionLabel(action) {
  return actionTypes.find(a => a.value === action)?.label || action
}

function actionTagType(action) {
  const map = {
    connect: 'success', disconnect: 'info',
    batch_command: 'warning', login: '', login_failed: 'danger',
  }
  return map[action] || 'info'
}

async function loadLogs() {
  loading.value = true
  try {
    const res = await api.get('/api/audit-logs', {
      params: { page: page.value, page_size: 50, action: actionFilter.value || undefined },
    })
    logs.value = res.data.logs
    total.value = res.data.total
  } finally {
    loading.value = false
  }
}

watch(actionFilter, () => { page.value = 1; loadLogs() })
onMounted(loadLogs)
</script>

<style scoped>
.page-view {
  display: flex;
  flex-direction: column;
  height: 100vh;
  background: var(--bg-primary);
}

.page-header {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 12px 20px;
  background: var(--bg-secondary);
  border-bottom: 1px solid var(--border-color);
  flex-shrink: 0;
}

.page-header h2 { flex: 1; font-size: 16px; }
.log-table { flex: 1; }
</style>
