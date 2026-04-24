<template>
  <div class="file-explorer">
    <!-- 头部 -->
    <div class="explorer-header">
      <span class="explorer-title">资源管理器</span>
      <el-dropdown v-if="activeServerId" trigger="click" @command="handleCommand">
        <el-button text size="small" @click.stop>
          <el-icon><MoreFilled /></el-icon>
        </el-button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item command="refresh">
              <el-icon><Refresh /></el-icon> 刷新
            </el-dropdown-item>
            <el-dropdown-item command="mkdir">
              <el-icon><FolderAdd /></el-icon> 新建目录
            </el-dropdown-item>
            <el-dropdown-item command="upload">
              <el-icon><Upload /></el-icon> 上传文件
            </el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
    </div>

    <!-- 无服务器选中时提示 -->
    <div v-if="!activeServerId" class="explorer-empty">
      <el-icon size="24" color="#8b949e"><FolderOpened /></el-icon>
      <p>连接服务器后查看文件</p>
    </div>

    <!-- 面包屑路径 -->
    <div v-else class="explorer-breadcrumb">
      <el-icon size="12" class="breadcrumb-icon"><FolderOpened /></el-icon>
      <span class="breadcrumb-path" @click="currentPath = '/'">
        {{ currentPath || '/' }}
      </span>
    </div>

    <!-- 文件树 -->
    <div v-if="activeServerId" v-loading="loading" class="explorer-tree">
      <!-- 返回上一级 -->
      <div
        v-if="currentPath !== '/'"
        class="tree-item parent-dir"
        @click="navigateTo(parentPath)"
        @dblclick.stop
      >
        <el-icon size="14" color="#8b949e"><ArrowLeft /></el-icon>
        <span>..</span>
      </div>

      <!-- 目录排序在前 -->
      <div
        v-for="item in sortedItems"
        :key="item.path"
        class="tree-item"
        :class="{ 'is-dir': item.is_dir }"
        @click="item.is_dir && navigateTo(item.path)"
        @contextmenu.prevent="showItemMenu($event, item)"
        @dblclick="onItemDblClick(item)"
      >
        <el-icon size="14" :color="item.is_dir ? '#d29922' : '#58a6ff'">
          <Folder v-if="item.is_dir" />
          <Document v-else />
        </el-icon>
        <span class="tree-item-name" :title="item.name">{{ item.name }}</span>
        <span v-if="!item.is_dir" class="tree-item-size">{{ formatSize(item.size) }}</span>
      </div>

      <!-- 空目录 -->
      <div v-if="!loading && files.length === 0" class="tree-empty">
        空目录
      </div>
    </div>

    <!-- 右键菜单 -->
    <div
      v-if="menuVisible"
      class="ctx-menu"
      :style="{ top: menuPos.y + 'px', left: menuPos.x + 'px' }"
      v-click-outside="menuVisible = false"
    >
      <div v-if="!ctxItem?.is_dir" class="ctx-item" @click="downloadFile(); menuVisible = false">
        <el-icon><Download /></el-icon> 下载
      </div>
      <div v-if="!ctxItem?.is_dir" class="ctx-item" @click="editFile(); menuVisible = false">
        <el-icon><Edit /></el-icon> 编辑
      </div>
      <div class="ctx-item" @click="startRename(); menuVisible = false">
        <el-icon><EditPen /></el-icon> 重命名
      </div>
      <div class="ctx-item danger" @click="deleteFile(); menuVisible = false">
        <el-icon><Delete /></el-icon> 删除
      </div>
    </div>

    <!-- 新建目录 -->
    <el-dialog v-model="mkdirDialog" title="新建目录" width="320px" append-to-body>
      <el-input v-model="newDirName" placeholder="目录名称" size="small" @keyup.enter="mkdir" />
      <template #footer>
        <el-button size="small" @click="mkdirDialog = false">取消</el-button>
        <el-button size="small" type="primary" @click="mkdir" :disabled="!newDirName">创建</el-button>
      </template>
    </el-dialog>

    <!-- 重命名 -->
    <el-dialog v-model="renameDialog" title="重命名" width="320px" append-to-body>
      <el-input v-model="renameValue" size="small" @keyup.enter="doRename" />
      <template #footer>
        <el-button size="small" @click="renameDialog = false">取消</el-button>
        <el-button size="small" type="primary" @click="doRename" :disabled="!renameValue">确定</el-button>
      </template>
    </el-dialog>

    <!-- 文件编辑器 -->
    <el-dialog v-model="editorDialog" :title="'编辑 - ' + editingFile" width="700px" append-to-body>
      <el-input
        v-model="editorContent"
        type="textarea"
        :rows="20"
        style="font-family: monospace; font-size: 13px"
      />
      <template #footer>
        <el-button size="small" @click="editorDialog = false">取消</el-button>
        <el-button size="small" type="primary" :loading="savingFile" @click="saveFile">保存</el-button>
      </template>
    </el-dialog>

    <!-- 隐藏的上传 input -->
    <input
      ref="uploadInputRef"
      type="file"
      multiple
      style="display: none"
      @change="handleFileSelect"
    />
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  FolderOpened, MoreFilled, Refresh, FolderAdd, Upload, Folder, Document,
  Download, Edit, EditPen, Delete, ArrowLeft,
} from '@element-plus/icons-vue'
import api from '@/utils/api'

const props = defineProps({
  serverId: { type: Number, default: null },
})

const activeServerId = computed(() => props.serverId)
const currentPath = ref('/')
const files = ref([])
const loading = ref(false)

// 菜单
const menuVisible = ref(false)
const menuPos = ref({ x: 0, y: 0 })
const ctxItem = ref(null)

// 弹窗
const mkdirDialog = ref(false)
const renameDialog = ref(false)
const editorDialog = ref(false)
const newDirName = ref('')
const renameValue = ref('')
const editingFile = ref('')
const editorContent = ref('')
const savingFile = ref(false)
const uploadInputRef = ref(null)

const parentPath = computed(() => {
  const p = currentPath.value.replace(/\/+$/, '')
  if (p === '' || p === '/') return '/'
  const idx = p.lastIndexOf('/')
  return idx <= 0 ? '/' : p.substring(0, idx)
})

const sortedItems = computed(() => {
  return [...files.value].sort((a, b) => {
    if (a.is_dir !== b.is_dir) return a.is_dir ? -1 : 1
    return a.name.localeCompare(b.name)
  })
})

// 监听 serverId 变化，自动加载根目录
watch(() => props.serverId, (newId) => {
  if (newId) {
    currentPath.value = '/'
    loadDir()
  } else {
    files.value = []
  }
}, { immediate: true })

async function loadDir() {
  if (!activeServerId.value) return
  loading.value = true
  try {
    const res = await api.get(`/api/sftp/${activeServerId.value}/list`, {
      params: { path: currentPath.value }
    })
    files.value = res.data.files || []
  } catch (e) {
    files.value = []
  } finally {
    loading.value = false
  }
}

function navigateTo(path) {
  currentPath.value = path
  loadDir()
}

function onItemDblClick(item) {
  if (item.is_dir) {
    navigateTo(item.path)
  }
}

function formatSize(bytes) {
  if (bytes < 1024) return bytes + 'B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(0) + 'K'
  return (bytes / 1024 / 1024).toFixed(1) + 'M'
}

function showItemMenu(event, item) {
  ctxItem.value = item
  menuPos.value = { x: event.clientX, y: event.clientY }
  menuVisible.value = true
}

function downloadFile() {
  if (!ctxItem.value || ctxItem.value.is_dir) return
  const url = `/api/sftp/${activeServerId.value}/download?path=${encodeURIComponent(ctxItem.value.path)}`
  const a = document.createElement('a')
  a.href = url
  a.download = ctxItem.value.name
  a.click()
}

async function editFile() {
  if (!ctxItem.value || ctxItem.value.is_dir) return
  try {
    const res = await api.get(`/api/sftp/${activeServerId.value}/read`, {
      params: { path: ctxItem.value.path }
    })
    editingFile.value = ctxItem.value.name
    editorContent.value = res.data.content
    editorDialog.value = true
  } catch (e) {
    ElMessage.error('读取文件失败')
  }
}

async function saveFile() {
  savingFile.value = true
  try {
    const path = currentPath.value.replace(/\/$/, '') + '/' + editingFile.value
    await api.post(`/api/sftp/${activeServerId.value}/write`, null, {
      params: { path, content: editorContent.value }
    })
    ElMessage.success('保存成功')
    editorDialog.value = false
  } catch (e) {
    ElMessage.error('保存失败')
  } finally {
    savingFile.value = false
  }
}

function startRename() {
  if (!ctxItem.value) return
  renameValue.value = ctxItem.value.name
  renameDialog.value = true
}

async function doRename() {
  if (!ctxItem.value || !renameValue.value) return
  try {
    const oldPath = ctxItem.value.path
    const newPath = currentPath.value.replace(/\/$/, '') + '/' + renameValue.value
    await api.post(`/api/sftp/${activeServerId.value}/rename`, null, {
      params: { old_path: oldPath, new_path: newPath }
    })
    ElMessage.success('重命名成功')
    renameDialog.value = false
    loadDir()
  } catch (e) {
    ElMessage.error('重命名失败')
  }
}

async function deleteFile() {
  if (!ctxItem.value) return
  try {
    await ElMessageBox.confirm(`确定删除 "${ctxItem.value.name}"？`, '删除确认', { type: 'warning' })
    await api.delete(`/api/sftp/${activeServerId.value}/delete`, {
      params: { path: ctxItem.value.path, is_dir: ctxItem.value.is_dir }
    })
    ElMessage.success('删除成功')
    loadDir()
  } catch (e) {
    // 取消
  }
}

async function mkdir() {
  if (!newDirName.value || !activeServerId.value) return
  try {
    const path = currentPath.value.replace(/\/$/, '') + '/' + newDirName.value
    await api.post(`/api/sftp/${activeServerId.value}/mkdir`, null, { params: { path } })
    ElMessage.success('目录创建成功')
    mkdirDialog.value = false
    newDirName.value = ''
    loadDir()
  } catch (e) {
    ElMessage.error('创建失败')
  }
}

function handleCommand(cmd) {
  if (cmd === 'refresh') loadDir()
  else if (cmd === 'mkdir') { mkdirDialog.value = true }
  else if (cmd === 'upload') { uploadInputRef.value?.click() }
}

async function handleFileSelect(event) {
  const selectedFiles = event.target.files
  if (!selectedFiles?.length || !activeServerId.value) return
  for (const file of selectedFiles) {
    const form = new FormData()
    form.append('file', file)
    await api.post(`/api/sftp/${activeServerId.value}/upload`, form, {
      params: { remote_path: currentPath.value },
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  }
  ElMessage.success(`已上传 ${selectedFiles.length} 个文件`)
  event.target.value = ''
  loadDir()
}

// 暴露刷新方法
defineExpose({ loadDir })
</script>

<style scoped>
.file-explorer {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
}

.explorer-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  height: 36px;
  flex-shrink: 0;
  border-bottom: 1px solid var(--border-color);
}

.explorer-title {
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: var(--text-secondary);
}

.explorer-empty {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  color: var(--text-secondary);
  font-size: 12px;
  text-align: center;
  padding: 20px;
}

.explorer-breadcrumb {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  font-size: 12px;
  color: var(--text-secondary);
  border-bottom: 1px solid var(--border-color);
  flex-shrink: 0;
  overflow: hidden;
}

.breadcrumb-icon {
  flex-shrink: 0;
}

.breadcrumb-path {
  cursor: pointer;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.breadcrumb-path:hover {
  color: var(--text-primary);
}

.explorer-tree {
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
  padding: 4px 0;
}

.tree-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 3px 12px;
  font-size: 13px;
  cursor: pointer;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  user-select: none;
  transition: background 0.1s;
}

.tree-item:hover {
  background: var(--bg-hover);
}

.tree-item.is-dir {
  color: var(--text-primary);
}

.tree-item.parent-dir {
  color: var(--text-secondary);
}

.tree-item-name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  min-width: 0;
}

.tree-item-size {
  font-size: 11px;
  color: var(--text-secondary);
  flex-shrink: 0;
  margin-left: auto;
}

.tree-empty {
  padding: 20px 12px;
  text-align: center;
  font-size: 12px;
  color: var(--text-secondary);
}

/* 右键菜单 */
.ctx-menu {
  position: fixed;
  z-index: 9999;
  background: var(--bg-panel);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  padding: 4px;
  min-width: 140px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.4);
}

.ctx-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 12px;
  font-size: 12px;
  cursor: pointer;
  border-radius: 6px;
  color: var(--text-primary);
  transition: background 0.1s;
}

.ctx-item:hover { background: var(--bg-hover); }
.ctx-item.danger { color: #f85149; }
.ctx-item.danger:hover { background: rgba(248, 81, 73, 0.1); }

/* 滚动条美化 */
.explorer-tree::-webkit-scrollbar {
  width: 4px;
}
.explorer-tree::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.15);
  border-radius: 2px;
}
.explorer-tree::-webkit-scrollbar-track {
  background: transparent;
}
</style>
