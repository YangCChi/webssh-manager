<template>
  <div class="sftp-view">
    <div class="sftp-header">
      <el-button @click="$router.back()">
        <el-icon><ArrowLeft /></el-icon> 返回终端
      </el-button>
      <h2>
        <el-icon><FolderOpened /></el-icon>
        SFTP 文件管理 - {{ serverName }}
      </h2>
      <el-button type="primary" @click="uploadDialog = true">
        <el-icon><Upload /></el-icon> 上传文件
      </el-button>
    </div>

    <div class="sftp-toolbar">
      <!-- 路径面包屑 -->
      <el-breadcrumb separator="/">
        <el-breadcrumb-item
          v-for="(part, idx) in pathParts"
          :key="idx"
          @click="navigateTo(getPathAt(idx))"
          style="cursor: pointer"
        >{{ part || '/' }}</el-breadcrumb-item>
      </el-breadcrumb>
      <div style="flex: 1" />
      <el-input v-model="currentPath" @change="loadDir" size="small" style="width: 200px" />
      <el-button size="small" @click="loadDir" :loading="loading">
        <el-icon><Refresh /></el-icon>
      </el-button>
      <el-button size="small" @click="mkdirDialog = true">
        <el-icon><FolderAdd /></el-icon> 新建目录
      </el-button>
    </div>

    <!-- 文件列表 -->
    <el-table
      v-loading="loading"
      :data="files"
      class="sftp-table"
      @row-dblclick="onRowDblClick"
      row-key="name"
      :row-class-name="rowClass"
    >
      <el-table-column width="40">
        <template #default="{ row }">
          <el-icon :color="row.is_dir ? '#d29922' : '#58a6ff'">
            <Folder v-if="row.is_dir" />
            <Document v-else />
          </el-icon>
        </template>
      </el-table-column>
      <el-table-column label="文件名" prop="name" sortable min-width="200">
        <template #default="{ row }">
          <span :class="{ 'dir-name': row.is_dir }">{{ row.name }}</span>
        </template>
      </el-table-column>
      <el-table-column label="大小" width="100" sortable>
        <template #default="{ row }">
          {{ row.is_dir ? '-' : formatSize(row.size) }}
        </template>
      </el-table-column>
      <el-table-column label="修改时间" width="160" sortable>
        <template #default="{ row }">
          {{ row.mtime ? new Date(row.mtime * 1000).toLocaleString() : '-' }}
        </template>
      </el-table-column>
      <el-table-column label="权限" width="80" prop="permissions" />
      <el-table-column label="操作" width="160">
        <template #default="{ row }">
          <el-button text size="small" @click="downloadFile(row)" :disabled="row.is_dir">
            <el-icon><Download /></el-icon>
          </el-button>
          <el-button text size="small" @click="editFile(row)" :disabled="row.is_dir">
            <el-icon><Edit /></el-icon>
          </el-button>
          <el-button text size="small" @click="startRename(row)">
            <el-icon><EditPen /></el-icon>
          </el-button>
          <el-button text size="small" @click="deleteFile(row)">
            <el-icon color="#f85149"><Delete /></el-icon>
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 上传文件 -->
    <el-dialog v-model="uploadDialog" title="上传文件" width="440px" align-center>
      <el-upload
        drag
        multiple
        :before-upload="doUpload"
        :show-file-list="true"
        :auto-upload="false"
        ref="uploadRef"
        :limit="10"
      >
        <el-icon size="40"><Upload /></el-icon>
        <div>拖拽文件到此处，或<em>点击选择文件</em></div>
        <template #tip>
          <div style="font-size: 12px; color: var(--text-secondary)">
            上传目标：{{ currentPath }}，单文件最大 {{ maxSize }}MB
          </div>
        </template>
      </el-upload>
      <template #footer>
        <el-button @click="uploadDialog = false">取消</el-button>
        <el-button type="primary" @click="submitUpload" :loading="uploading">开始上传</el-button>
      </template>
    </el-dialog>

    <!-- 新建目录 -->
    <el-dialog v-model="mkdirDialog" title="新建目录" width="360px" align-center>
      <el-input v-model="newDirName" placeholder="目录名称" />
      <template #footer>
        <el-button @click="mkdirDialog = false">取消</el-button>
        <el-button type="primary" @click="mkdir">创建</el-button>
      </template>
    </el-dialog>

    <!-- 重命名 -->
    <el-dialog v-model="renameDialog" title="重命名" width="360px" align-center>
      <el-input v-model="renameValue" />
      <template #footer>
        <el-button @click="renameDialog = false">取消</el-button>
        <el-button type="primary" @click="doRename">确定</el-button>
      </template>
    </el-dialog>

    <!-- 文件编辑器 -->
    <el-dialog v-model="editorDialog" :title="'编辑 - ' + editingFile" width="800px" align-center>
      <el-input
        v-model="editorContent"
        type="textarea"
        :rows="25"
        style="font-family: monospace; font-size: 12px"
      />
      <template #footer>
        <el-button @click="editorDialog = false">取消</el-button>
        <el-button type="primary" :loading="savingFile" @click="saveFile">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  ArrowLeft, FolderOpened, Upload, Refresh, FolderAdd, Folder, Document,
  Download, Edit, EditPen, Delete,
} from '@element-plus/icons-vue'
import api from '@/utils/api'
import { useServerStore } from '@/stores/servers'

const route = useRoute()
const serverStore = useServerStore()
const serverId = computed(() => parseInt(route.params.serverId))
const serverName = computed(() => serverStore.servers.find(s => s.id === serverId.value)?.name || `服务器 ${serverId.value}`)
const maxSize = 100

const currentPath = ref('/')
const files = ref([])
const loading = ref(false)

const uploadDialog = ref(false)
const mkdirDialog = ref(false)
const renameDialog = ref(false)
const editorDialog = ref(false)
const newDirName = ref('')
const renameValue = ref('')
const renamingFile = ref(null)
const editingFile = ref('')
const editorContent = ref('')
const savingFile = ref(false)
const uploading = ref(false)
const uploadRef = ref()

const pathParts = computed(() => {
  const p = currentPath.value.replace(/\/+$/, '') || '/'
  return p === '/' ? ['/'] : p.split('/').filter(Boolean)
})

function getPathAt(idx) {
  if (idx === 0) return '/'
  return '/' + pathParts.value.slice(0, idx + 1).join('/')
}

async function loadDir() {
  loading.value = true
  try {
    const res = await api.get(`/api/sftp/${serverId.value}/list`, { params: { path: currentPath.value } })
    files.value = res.data.files
  } catch (e) {
    ElMessage.error('加载目录失败')
  } finally {
    loading.value = false
  }
}

function navigateTo(path) {
  currentPath.value = path
  loadDir()
}

function onRowDblClick(row) {
  if (row.is_dir) {
    navigateTo(row.path)
  }
}

function rowClass({ row }) {
  return row.is_dir ? 'dir-row' : ''
}

function formatSize(bytes) {
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  if (bytes < 1024 ** 3) return (bytes / 1024 / 1024).toFixed(1) + ' MB'
  return (bytes / 1024 ** 3).toFixed(1) + ' GB'
}

function downloadFile(row) {
  const url = `/api/sftp/${serverId.value}/download?path=${encodeURIComponent(row.path)}`
  const a = document.createElement('a')
  a.href = url
  a.download = row.name
  a.click()
}

async function deleteFile(row) {
  await ElMessageBox.confirm(`确定删除 "${row.name}"？`, '删除确认', { type: 'warning' })
  await api.delete(`/api/sftp/${serverId.value}/delete`, { params: { path: row.path, is_dir: row.is_dir } })
  ElMessage.success('删除成功')
  loadDir()
}

function startRename(row) {
  renamingFile.value = row
  renameValue.value = row.name
  renameDialog.value = true
}

async function doRename() {
  const oldPath = renamingFile.value.path
  const newPath = currentPath.value.replace(/\/$/, '') + '/' + renameValue.value
  await api.post(`/api/sftp/${serverId.value}/rename`, null, { params: { old_path: oldPath, new_path: newPath } })
  ElMessage.success('重命名成功')
  renameDialog.value = false
  loadDir()
}

async function mkdir() {
  const path = currentPath.value.replace(/\/$/, '') + '/' + newDirName.value
  await api.post(`/api/sftp/${serverId.value}/mkdir`, null, { params: { path } })
  ElMessage.success('目录创建成功')
  mkdirDialog.value = false
  newDirName.value = ''
  loadDir()
}

async function editFile(row) {
  const res = await api.get(`/api/sftp/${serverId.value}/read`, { params: { path: row.path } })
  editingFile.value = row.name
  editorContent.value = res.data.content
  editorDialog.value = true
}

async function saveFile() {
  savingFile.value = true
  try {
    const path = currentPath.value.replace(/\/$/, '') + '/' + editingFile.value
    await api.post(`/api/sftp/${serverId.value}/write`, null, { params: { path, content: editorContent.value } })
    ElMessage.success('保存成功')
    editorDialog.value = false
  } finally {
    savingFile.value = false
  }
}

async function submitUpload() {
  const files = uploadRef.value?.uploadFiles
  if (!files?.length) return
  uploading.value = true
  for (const file of files) {
    const form = new FormData()
    form.append('file', file.raw)
    await api.post(`/api/sftp/${serverId.value}/upload`, form, {
      params: { remote_path: currentPath.value },
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  }
  ElMessage.success(`已上传 ${files.length} 个文件`)
  uploading.value = false
  uploadDialog.value = false
  loadDir()
}

onMounted(() => {
  loadDir()
})
</script>

<style scoped>
.sftp-view {
  display: flex;
  flex-direction: column;
  height: 100vh;
  background: var(--bg-primary);
  color: var(--text-primary);
}

.sftp-header {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 12px 20px;
  background: var(--bg-secondary);
  border-bottom: 1px solid var(--border-color);
  flex-shrink: 0;
}

.sftp-header h2 {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 16px;
  flex: 1;
}

.sftp-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 20px;
  background: var(--bg-panel);
  border-bottom: 1px solid var(--border-color);
  flex-shrink: 0;
}

.sftp-table {
  flex: 1;
  overflow: auto;
}

.dir-name { color: #d29922; font-weight: 500; }

:deep(.dir-row) { cursor: pointer; }
:deep(.dir-row:hover td) { background: var(--bg-hover) !important; }
</style>
