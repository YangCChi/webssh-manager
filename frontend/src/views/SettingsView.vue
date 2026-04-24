<template>
  <div class="page-view">
    <div class="page-header">
      <el-button @click="$router.push('/')"><el-icon><ArrowLeft /></el-icon> 返回</el-button>
      <h2>系统设置</h2>
    </div>

    <el-scrollbar style="flex: 1">
      <div class="settings-content">
        <!-- 修改密码 -->
        <el-card class="settings-card">
          <template #header><span>修改登录密码</span></template>
          <el-form :model="pwForm" :rules="pwRules" ref="pwFormRef" label-width="100px">
            <el-form-item label="当前密码" prop="old_password">
              <el-input v-model="pwForm.old_password" type="password" show-password style="width: 320px" />
            </el-form-item>
            <el-form-item label="新密码" prop="new_password">
              <el-input v-model="pwForm.new_password" type="password" show-password style="width: 320px" />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :loading="pwLoading" @click="changePwd">修改密码</el-button>
            </el-form-item>
          </el-form>
        </el-card>

        <!-- 会话管理 -->
        <el-card class="settings-card">
          <template #header>
            <div style="display: flex; justify-content: space-between; align-items: center">
              <span>活跃会话管理</span>
              <el-button size="small" @click="loadSessions">
                <el-icon><Refresh /></el-icon> 刷新
              </el-button>
            </div>
          </template>
          <el-table :data="sessions" size="small">
            <el-table-column label="会话ID" prop="id" width="200" />
            <el-table-column label="标签名" prop="tab_name" />
            <el-table-column label="状态" width="100">
              <template #default="{ row }">
                <el-tag :type="row.status === 'active' ? 'success' : 'warning'" size="small">
                  {{ row.status }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="最后活动" width="160">
              <template #default="{ row }">
                {{ new Date(row.last_activity * 1000).toLocaleString() }}
              </template>
            </el-table-column>
            <el-table-column label="操作" width="80">
              <template #default="{ row }">
                <el-button text size="small" @click="closeSession(row.id)">
                  <el-icon color="#f85149"><Close /></el-icon>
                </el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-card>

        <!-- 关于 -->
        <el-card class="settings-card">
          <template #header><span>关于</span></template>
          <div style="font-size: 13px; color: var(--text-secondary); line-height: 2">
            <div>WebSSH Manager v1.0.0</div>
            <div>基于 FastAPI + asyncssh + Vue3 + xterm.js 构建</div>
            <div>支持多终端并发 | SSH会话持久化 | SFTP文件管理 | 批量命令</div>
          </div>
        </el-card>
      </div>
    </el-scrollbar>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { ArrowLeft, Refresh, Close } from '@element-plus/icons-vue'
import api from '@/utils/api'

const pwFormRef = ref()
const pwLoading = ref(false)
const pwForm = reactive({ old_password: '', new_password: '' })
const pwRules = {
  old_password: [{ required: true, message: '请输入当前密码' }],
  new_password: [
    { required: true, message: '请输入新密码' },
    { min: 6, message: '密码至少6位' },
  ],
}

const sessions = ref([])

async function changePwd() {
  await pwFormRef.value?.validate()
  pwLoading.value = true
  try {
    await api.post('/api/auth/change-password', pwForm)
    ElMessage.success('密码修改成功')
    pwForm.old_password = ''
    pwForm.new_password = ''
  } finally {
    pwLoading.value = false
  }
}

async function loadSessions() {
  const res = await api.get('/api/sessions')
  sessions.value = res.data
}

async function closeSession(id) {
  await api.delete(`/api/sessions/${id}`)
  ElMessage.success('会话已关闭')
  loadSessions()
}

onMounted(loadSessions)
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

.page-header h2 { font-size: 16px; }

.settings-content {
  max-width: 720px;
  margin: 0 auto;
  padding: 24px 16px;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.settings-card {
  background: var(--bg-panel);
  border: 1px solid var(--border-color);
}

:deep(.el-card__header) {
  background: var(--bg-secondary);
  border-bottom: 1px solid var(--border-color);
  padding: 12px 20px;
  font-size: 14px;
  font-weight: 600;
}

:deep(.el-card__body) { padding: 20px; }
</style>
