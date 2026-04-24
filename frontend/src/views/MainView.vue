<template>
  <div class="main-layout">
    <!-- 左侧：活动栏 + 侧边栏 -->
    <aside class="sidebar-container" :class="{ collapsed: !sidebarVisible }">
      <!-- 活动栏（收起时仍显示） -->
      <div class="activity-bar">
        <div class="activity-top">
          <div
            class="activity-item"
            :class="{ active: sidebarTab === 'servers' && sidebarVisible }"
            title="服务器列表"
            @click="toggleSidebar('servers')"
          >
            <el-icon size="20"><Monitor /></el-icon>
          </div>
          <div
            class="activity-item"
            :class="{ active: sidebarTab === 'files' && sidebarVisible }"
            title="资源管理器"
            @click="toggleSidebar('files')"
          >
            <el-icon size="20"><FolderOpened /></el-icon>
          </div>
          <div
            class="activity-item"
            :class="{ active: sidebarTab === 'snippets' && sidebarVisible }"
            title="快捷命令"
            @click="toggleSidebar('snippets')"
          >
            <el-icon size="20"><Collection /></el-icon>
          </div>
          <div
            class="activity-item"
            :class="{ active: sidebarTab === 'batch' && sidebarVisible }"
            title="批量命令"
            @click="toggleSidebar('batch')"
          >
            <el-icon size="20"><Promotion /></el-icon>
          </div>
        </div>
        <div class="activity-bottom">
          <div class="activity-item" title="设置" @click="$router.push('/settings')">
            <el-icon size="18"><Setting /></el-icon>
          </div>
          <div class="activity-item" title="日志" @click="$router.push('/logs')">
            <el-icon size="18"><Document /></el-icon>
          </div>
          <div class="activity-item" title="退出登录" @click="authStore.logout(); $router.push('/login')">
            <el-icon size="18"><SwitchButton /></el-icon>
          </div>
        </div>
      </div>

      <!-- 侧边栏内容 -->
      <div class="sidebar-panel" :style="{ width: sidebarVisible ? '260px' : '0px' }">
        <!-- 服务器列表 -->
        <div v-show="sidebarVisible && sidebarTab === 'servers'" class="sidebar-content">
          <div class="sidebar-header">
            <span class="sidebar-title">服务器</span>
            <el-button text size="small" @click="showAddServer = true">
              <el-icon><Plus /></el-icon>
            </el-button>
          </div>

          <div class="sidebar-search">
            <el-input
              v-model="searchQuery"
              placeholder="搜索服务器..."
              size="small"
              clearable
              :prefix-icon="Search"
              @input="serverStore.fetchServers(searchQuery)"
            />
          </div>

          <!-- 分组选择 -->
          <div class="group-tabs">
            <el-scrollbar>
              <div class="group-list">
                <div
                  class="group-chip"
                  :class="{ active: selectedGroupId === null }"
                  @click="selectGroup(null)"
                >全部</div>
                <div
                  v-for="g in serverStore.groups"
                  :key="g.id"
                  class="group-chip"
                  :class="{ active: selectedGroupId === g.id }"
                  :style="{ borderColor: selectedGroupId === g.id ? g.color : 'transparent' }"
                  @click="selectGroup(g.id)"
                >
                  <span class="group-dot" :style="{ background: g.color }" />
                  {{ g.name }}
                </div>
                <el-button text size="small" @click="showAddGroup = true">
                  <el-icon><Plus /></el-icon>
                </el-button>
              </div>
            </el-scrollbar>
          </div>

          <el-scrollbar class="server-list-scroll">
            <div class="server-list">
              <div
                v-for="server in serverStore.servers"
                :key="server.id"
                class="server-item"
                :class="{ connected: isConnected(server.id) }"
                @contextmenu.prevent="showServerMenu($event, server)"
              >
                <div class="server-dot" :style="{ background: getServerColor(server) }" />
                <div class="server-info">
                  <div class="server-name">
                    <el-icon v-if="server.is_favorite" color="#d29922" size="12"><StarFilled /></el-icon>
                    {{ server.name }}
                  </div>
                  <div class="server-host">{{ server.username }}@{{ server.host }}:{{ server.port }}</div>
                </div>
                <div class="server-actions">
                  <el-button
                    type="primary"
                    size="small"
                    circle
                    @click.stop="connectServer(server)"
                    :loading="connectingId === server.id"
                  >
                    <el-icon><Link /></el-icon>
                  </el-button>
                </div>
              </div>

              <div v-if="!serverStore.servers.length && !serverStore.loading" class="empty-tip">
                <el-icon size="32" color="#8b949e"><Cpu /></el-icon>
                <p>暂无服务器</p>
                <el-button size="small" type="primary" @click="showAddServer = true">添加服务器</el-button>
              </div>
            </div>
          </el-scrollbar>


        </div>

        <!-- 文件资源管理器 -->
        <div v-show="sidebarVisible && sidebarTab === 'files'" class="sidebar-content">
          <FileExplorer
            :server-id="activeTabServerId"
            ref="fileExplorerRef"
          />
        </div>

        <!-- 快捷命令（内嵌） -->
        <div v-show="sidebarVisible && sidebarTab === 'snippets'" class="sidebar-content">
          <div class="sidebar-header">
            <span class="sidebar-title">快捷命令</span>
            <el-button text size="small" @click="showAddSnippet = true">
              <el-icon><Plus /></el-icon>
            </el-button>
          </div>
          <div class="sidebar-search">
            <el-input
              v-model="snippetSearch"
              placeholder="搜索命令..."
              size="small"
              clearable
              :prefix-icon="Search"
            />
          </div>
          <el-scrollbar class="snippet-scroll">
            <div class="snippet-list-inline">
              <div
                v-for="s in filteredSnippets"
                :key="s.id"
                class="snippet-item-inline"
                @click="sendSnippetCmd(s)"
              >
                <div class="snippet-name-inline">{{ s.name }}</div>
                <div class="snippet-cmd-inline">{{ s.command }}</div>
              </div>
              <div v-if="!filteredSnippets.length" class="empty-tip-small">
                暂无命令
              </div>
            </div>
          </el-scrollbar>
        </div>

        <!-- 批量命令（内嵌） -->
        <div v-show="sidebarVisible && sidebarTab === 'batch'" class="sidebar-content">
          <div class="sidebar-header">
            <span class="sidebar-title">批量命令</span>
          </div>
          <div class="batch-panel">
            <div class="batch-targets">
              <div class="batch-label">目标终端</div>
              <el-checkbox-group v-model="batchForm.selectedIds" size="small">
                <div v-for="tab in terminalStore.tabs" :key="tab.id" class="batch-tab-item">
                  <el-checkbox :label="tab.id" size="small">
                    <span class="batch-tab-name">
                      <span class="tab-dot" :style="{ background: tab.color }" />
                      {{ tab.name }}
                    </span>
                  </el-checkbox>
                </div>
              </el-checkbox-group>
              <div v-if="!terminalStore.tabs.length" class="empty-tip-small">
                请先连接终端
              </div>
            </div>
            <div class="batch-input-area">
              <el-input
                v-model="batchForm.command"
                type="textarea"
                :rows="3"
                placeholder="输入要批量执行的命令"
                size="small"
                style="font-family: monospace; font-size: 12px"
              />
              <el-button
                type="warning"
                size="small"
                :loading="batchSending"
                :disabled="!batchForm.selectedIds.length || !batchForm.command"
                @click="sendBatchCmd"
                style="width: 100%; margin-top: 8px"
              >
                发送到 {{ batchForm.selectedIds.length }} 个终端
              </el-button>
            </div>
          </div>
        </div>
      </div>
    </aside>

    <!-- 主区域：终端 -->
    <main class="main-content">
      <!-- 无会话时的欢迎页 -->
      <div v-if="terminalStore.tabs.length === 0" class="welcome-screen">
        <el-icon size="64" color="#58a6ff"><Monitor /></el-icon>
        <h2>WebSSH Manager</h2>
        <p>从左侧选择服务器，点击连接按钮开始会话</p>
        <div class="welcome-features">
          <div class="feature-item">
            <el-icon color="#3fb950"><CircleCheck /></el-icon>
            <span>多标签同时连接不同服务器</span>
          </div>
          <div class="feature-item">
            <el-icon color="#3fb950"><CircleCheck /></el-icon>
            <span>关闭网页 SSH 连接不中断</span>
          </div>
          <div class="feature-item">
            <el-icon color="#3fb950"><CircleCheck /></el-icon>
            <span>重新打开自动恢复所有终端</span>
          </div>
          <div class="feature-item">
            <el-icon color="#3fb950"><CircleCheck /></el-icon>
            <span>左侧资源管理器 + 终端并排</span>
          </div>
        </div>
      </div>

      <!-- 有会话时的终端区域 -->
      <template v-else>
        <!-- 标签栏 -->
        <div class="terminal-tabs">
          <div
            v-for="tab in terminalStore.tabs"
            :key="tab.id"
            class="terminal-tab"
            :class="{ active: tab.id === terminalStore.activeTabId }"
            @click="terminalStore.setActive(tab.id)"
            @contextmenu.prevent="showTabMenu($event, tab)"
          >
            <span class="tab-dot" :style="{ background: tab.color || '#409EFF' }" />
            <div class="tab-status-dot" :class="tab.status" />
            <span class="tab-name">{{ tab.name }}</span>
            <el-icon class="tab-close" @click.stop="closeTab(tab.id)"><Close /></el-icon>
          </div>
          <div class="add-tab-btn" @click="showAddServer = true">
            <el-icon><Plus /></el-icon>
          </div>
        </div>

        <!-- 终端容器 -->
        <div class="terminals-wrapper">
          <TerminalPane
            v-for="tab in terminalStore.tabs"
            :key="tab.id"
            :session-id="tab.id"
            :visible="tab.id === terminalStore.activeTabId"
            :server-id="tab.serverId"
            :tab-name="tab.name"
            @status-change="(s) => terminalStore.updateTabStatus(tab.id, s)"
            @open-sftp="toggleSidebar('files')"
          />
        </div>
      </template>
    </main>

    <!-- 右键菜单：服务器 -->
    <div
      v-if="serverMenuVisible"
      class="ctx-menu"
      :style="{ top: serverMenuPos.y + 'px', left: serverMenuPos.x + 'px' }"
      v-click-outside="() => (serverMenuVisible = false)"
    >
      <div class="ctx-item" @click="connectServer(ctxServer); serverMenuVisible = false">
        <el-icon><Link /></el-icon> 连接
      </div>
      <div class="ctx-item" @click="toggleSidebar('files'); serverMenuVisible = false">
        <el-icon><FolderOpened /></el-icon> 资源管理器
      </div>
      <div class="ctx-item" @click="openSFTP(ctxServer.id); serverMenuVisible = false">
        <el-icon><Monitor /></el-icon> 全屏文件管理
      </div>
      <div class="ctx-item" @click="editServer(ctxServer); serverMenuVisible = false">
        <el-icon><Edit /></el-icon> 编辑
      </div>
      <div class="ctx-item" @click="serverStore.toggleFavorite(ctxServer.id); serverMenuVisible = false">
        <el-icon><Star /></el-icon> {{ ctxServer?.is_favorite ? '取消收藏' : '收藏' }}
      </div>
      <el-divider style="margin: 4px 0" />
      <div class="ctx-item danger" @click="deleteServer(ctxServer); serverMenuVisible = false">
        <el-icon><Delete /></el-icon> 删除
      </div>
    </div>

    <!-- 弹窗：添加/编辑服务器 -->
    <ServerDialog
      v-model="showAddServer"
      :edit-server="editingServer"
      :groups="serverStore.groups"
      @saved="onServerSaved"
    />

    <!-- 弹窗：添加分组 -->
    <el-dialog v-model="showAddGroup" title="新建分组" width="360px" align-center>
      <el-form :model="groupForm" label-width="60px">
        <el-form-item label="名称">
          <el-input v-model="groupForm.name" placeholder="例如：生产环境" />
        </el-form-item>
        <el-form-item label="颜色">
          <el-color-picker v-model="groupForm.color" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showAddGroup = false">取消</el-button>
        <el-button type="primary" @click="createGroup">确定</el-button>
      </template>
    </el-dialog>

    <!-- 弹窗：添加快捷命令 -->
    <el-dialog v-model="showAddSnippet" title="添加命令" width="440px" align-center>
      <el-form :model="snippetForm" label-width="70px">
        <el-form-item label="名称">
          <el-input v-model="snippetForm.name" placeholder="命令名称" />
        </el-form-item>
        <el-form-item label="命令">
          <el-input v-model="snippetForm.command" type="textarea" :rows="3" placeholder="例如：docker ps -a" style="font-family: monospace" />
        </el-form-item>
        <el-form-item label="分类">
          <el-input v-model="snippetForm.category" placeholder="默认：通用" />
        </el-form-item>
        <el-form-item label="说明">
          <el-input v-model="snippetForm.description" placeholder="可选" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showAddSnippet = false">取消</el-button>
        <el-button type="primary" @click="addSnippet">添加</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Monitor, SwitchButton, Search, Plus, Setting, Document, Collection,
  Promotion, CircleCheck, Close, Link, FolderOpened, Edit, Star, StarFilled,
  Delete, Cpu,
} from '@element-plus/icons-vue'

import { useAuthStore } from '@/stores/auth'
import { useServerStore } from '@/stores/servers'
import { useTerminalStore } from '@/stores/terminal'

import TerminalPane from '@/components/TerminalPane.vue'
import FileExplorer from '@/components/FileExplorer.vue'
import ServerDialog from '@/components/ServerDialog.vue'
import api from '@/utils/api'

const router = useRouter()
const authStore = useAuthStore()
const serverStore = useServerStore()
const terminalStore = useTerminalStore()

// 搜索 & 分组
const searchQuery = ref('')
const selectedGroupId = ref(null)

// 弹窗控制
const showAddServer = ref(false)
const showAddGroup = ref(false)
const showAddSnippet = ref(false)

// 快捷命令（内嵌面板）
const snippets = ref([])
const snippetSearch = ref('')
const snippetForm = reactive({ name: '', command: '', category: '通用', description: '' })

const filteredSnippets = computed(() => {
  return snippets.value.filter(s => {
    return !snippetSearch.value || s.name.includes(snippetSearch.value) || s.command.includes(snippetSearch.value)
  })
})

// 批量命令（内嵌面板）
const batchSending = ref(false)
const batchForm = reactive({ selectedIds: [], command: '' })

// 编辑服务器
const editingServer = ref(null)

// 分组表单
const groupForm = reactive({ name: '', color: '#409EFF' })

// 连接中状态
const connectingId = ref(null)

// 右键菜单
const serverMenuVisible = ref(false)
const serverMenuPos = reactive({ x: 0, y: 0 })
const ctxServer = ref(null)

// 检查服务器是否已有活跃会话
function isConnected(serverId) {
  return terminalStore.tabs.some(t => t.serverId === serverId && t.status === 'active')
}

// 获取服务器状态颜色
function getServerColor(server) {
  if (isConnected(server.id)) return '#3fb950'
  return server.is_favorite ? '#d29922' : '#58a6ff'
}

async function selectGroup(groupId) {
  selectedGroupId.value = groupId
  await serverStore.fetchServers(searchQuery.value, groupId)
}

async function connectServer(server) {
  connectingId.value = server.id
  try {
    await terminalStore.connect(server.id, { tabName: server.name })
  } catch (e) {
    ElMessage.error(`连接失败: ${e.response?.data?.detail || e.message}`)
  } finally {
    connectingId.value = null
  }
}

async function closeTab(sessionId) {
  try {
    await ElMessageBox.confirm('确定关闭此终端会话？', '关闭会话', {
      confirmButtonText: '关闭',
      cancelButtonText: '取消',
      type: 'warning',
    })
    await terminalStore.closeTab(sessionId)
  } catch (e) {
    // 取消
  }
}

function showServerMenu(event, server) {
  ctxServer.value = server
  serverMenuPos.x = event.clientX
  serverMenuPos.y = event.clientY
  serverMenuVisible.value = true
}

function showTabMenu(event, tab) {
  // 可扩展标签右键菜单
}

function editServer(server) {
  editingServer.value = server
  showAddServer.value = true
}

async function deleteServer(server) {
  try {
    await ElMessageBox.confirm(`确定删除服务器 "${server.name}"？`, '删除服务器', {
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      type: 'warning',
    })
    await serverStore.deleteServer(server.id)
    ElMessage.success('删除成功')
  } catch (e) {
    // 取消
  }
}

function openSFTP(serverId) {
  router.push(`/sftp/${serverId}`)
}

// 当前活跃标签的服务器 ID（用于 FileExplorer）
const activeTabServerId = computed(() => {
  const tab = terminalStore.tabs.find(t => t.id === terminalStore.activeTabId)
  return tab?.serverId || null
})

// 侧边栏状态
const sidebarVisible = ref(true)
const sidebarTab = ref('servers')  // 'servers' | 'files'
const fileExplorerRef = ref(null)

function toggleSidebar(tab) {
  if (sidebarTab.value === tab && sidebarVisible.value) {
    // 再次点击同一个 tab → 收起
    sidebarVisible.value = false
  } else {
    sidebarTab.value = tab
    sidebarVisible.value = true
  }
}

async function createGroup() {
  if (!groupForm.name) return
  await serverStore.createGroup({ name: groupForm.name, color: groupForm.color })
  groupForm.name = ''
  groupForm.color = '#409EFF'
  showAddGroup.value = false
}

async function onServerSaved() {
  showAddServer.value = false
  editingServer.value = null
  await serverStore.fetchServers()
}

// 快捷命令 API
async function fetchSnippets() {
  try {
    const res = await api.get('/api/snippets')
    snippets.value = res.data
  } catch (e) {
    console.warn('获取快捷命令失败', e)
  }
}

async function addSnippet() {
  if (!snippetForm.name || !snippetForm.command) return
  try {
    await api.post('/api/snippets', { ...snippetForm })
    ElMessage.success('添加成功')
    showAddSnippet.value = false
    snippetForm.name = snippetForm.command = snippetForm.description = ''
    snippetForm.category = '通用'
    fetchSnippets()
  } catch (e) {
    ElMessage.error('添加失败')
  }
}

async function sendSnippetCmd(s) {
  // 发送到当前活跃终端
  await api.post(`/api/snippets/${s.id}/use`)
  s.use_count = (s.use_count || 0) + 1
  // 通过 WebSocket 发送到活跃终端
  const activeTab = terminalStore.tabs.find(t => t.id === terminalStore.activeTabId)
  if (activeTab) {
    try {
      await api.post('/api/batch-command', {
        session_ids: [activeTab.id],
        command: s.command,
        interval_ms: 0,
      })
    } catch (e) {
      ElMessage.error('发送命令失败')
    }
  } else {
    ElMessage.warning('请先连接终端')
  }
}

// 批量命令 API
async function sendBatchCmd() {
  if (!batchForm.command.trim() || !batchForm.selectedIds.length) return
  batchSending.value = true
  try {
    const res = await api.post('/api/batch-command', {
      session_ids: batchForm.selectedIds,
      command: batchForm.command,
      interval_ms: 0,
    })
    ElMessage.success(`已发送到 ${res.data.sent.length} 个终端`)
    if (res.data.failed.length) {
      ElMessage.warning(`${res.data.failed.length} 个终端发送失败`)
    }
    batchForm.command = ''
  } catch (e) {
    ElMessage.error('批量发送失败')
  } finally {
    batchSending.value = false
  }
}

onMounted(async () => {
  await Promise.all([
    serverStore.fetchServers(),
    serverStore.fetchGroups(),
    terminalStore.restoreSessions(),
    fetchSnippets(),
  ])
})

// 点击外部关闭菜单
const vClickOutside = {
  mounted(el, binding) {
    el._clickOutside = (e) => {
      if (!el.contains(e.target)) binding.value(e)
    }
    document.addEventListener('click', el._clickOutside)
  },
  unmounted(el) {
    document.removeEventListener('click', el._clickOutside)
  },
}
</script>

<style scoped>
.main-layout {
  display: flex;
  height: 100vh;
  width: 100vw;
  overflow: hidden;
  background: var(--bg-primary);
}

/* 侧边栏容器（活动栏 + 面板） */
.sidebar-container {
  display: flex;
  flex-shrink: 0;
  height: 100%;
  transition: all 0.2s ease;
}

.sidebar-container.collapsed {
  /* 收起时只留活动栏 */
}

/* 活动栏（最左侧窄条） */
.activity-bar {
  width: 48px;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  background: var(--bg-secondary);
  border-right: 1px solid var(--border-color);
  flex-shrink: 0;
  padding: 4px 0;
}

.activity-top, .activity-bottom {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
}

.activity-item {
  width: 40px;
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  color: var(--text-secondary);
  border-left: 2px solid transparent;
  transition: all 0.15s;
  border-radius: 4px;
  margin: 2px 4px;
}

.activity-item:hover {
  color: var(--text-primary);
  background: var(--bg-hover);
}

.activity-item.active {
  color: var(--text-primary);
  border-left-color: var(--accent-blue);
}

/* 侧边栏内容面板 */
.sidebar-panel {
  width: 260px;
  background: var(--bg-secondary);
  border-right: 1px solid var(--border-color);
  overflow: hidden;
  flex-shrink: 0;
  transition: width 0.2s ease;
}

.sidebar-container.collapsed .sidebar-panel {
  width: 0;
  border-right: none;
}

.sidebar-content {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
}

.sidebar-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 12px;
  border-bottom: 1px solid var(--border-color);
  height: 40px;
  flex-shrink: 0;
}

.sidebar-title {
  font-weight: 600;
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: var(--text-secondary);
}

.sidebar-search {
  padding: 8px 12px;
  flex-shrink: 0;
}

.group-tabs {
  padding: 0 8px;
  flex-shrink: 0;
  border-bottom: 1px solid var(--border-color);
  padding-bottom: 8px;
}

.group-list {
  display: flex;
  gap: 6px;
  padding: 6px 4px;
  flex-wrap: nowrap;
}

.group-chip {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 3px 10px;
  border-radius: 12px;
  font-size: 12px;
  cursor: pointer;
  white-space: nowrap;
  border: 1px solid transparent;
  color: var(--text-secondary);
  background: var(--bg-panel);
  transition: all 0.15s;
}

.group-chip:hover { color: var(--text-primary); }
.group-chip.active {
  background: var(--bg-hover);
  color: var(--accent-blue);
  border-color: var(--accent-blue);
}

.group-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
}

.server-list-scroll { flex: 1; min-height: 0; }

.server-list {
  padding: 8px;
}

.server-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 10px;
  border-radius: 8px;
  cursor: pointer;
  transition: background 0.15s;
  margin-bottom: 2px;
}

.server-item:hover { background: var(--bg-hover); }
.server-item.connected { background: rgba(63, 185, 80, 0.08); }

.server-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex-shrink: 0;
}

.server-info {
  flex: 1;
  min-width: 0;
}

.server-name {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  display: flex;
  align-items: center;
  gap: 4px;
}

.server-host {
  font-size: 11px;
  color: var(--text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.server-actions { opacity: 0; }
.server-item:hover .server-actions { opacity: 1; }

.empty-tip {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 40px 20px;
  color: var(--text-secondary);
  font-size: 13px;
  text-align: center;
}

.sidebar-footer {
  padding: 6px 10px;
  border-top: 1px solid var(--border-color);
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

/* 主内容 */
.main-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: var(--bg-primary);
}

.terminals-wrapper {
  flex: 1;
  position: relative;
  overflow: hidden;
}

/* 欢迎页 */
.welcome-screen {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 16px;
  color: var(--text-secondary);
}

.welcome-screen h2 {
  font-size: 24px;
  font-weight: 600;
  color: var(--text-primary);
}

.welcome-screen p {
  font-size: 14px;
  color: var(--text-secondary);
}

.welcome-features {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-top: 8px;
}

.feature-item {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  color: var(--text-primary);
}

/* 标签栏 */
.terminal-tabs {
  display: flex;
  align-items: center;
  background: var(--bg-secondary);
  border-bottom: 1px solid var(--border-color);
  height: 40px;
  overflow-x: auto;
  overflow-y: hidden;
  flex-shrink: 0;
}

.terminal-tab {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 0 10px;
  height: 40px;
  min-width: 120px;
  max-width: 180px;
  cursor: pointer;
  border-right: 1px solid var(--border-color);
  color: var(--text-secondary);
  font-size: 12px;
  white-space: nowrap;
  overflow: hidden;
  user-select: none;
  transition: background 0.15s, color 0.15s;
  position: relative;
}

.terminal-tab:hover { background: var(--bg-hover); color: var(--text-primary); }
.terminal-tab.active {
  background: var(--bg-primary);
  color: var(--text-primary);
  border-bottom: 2px solid #1f6feb;
}

.tab-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.tab-status-dot {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  flex-shrink: 0;
}

.tab-status-dot.active { background: #3fb950; }
.tab-status-dot.connecting { background: #d29922; }
.tab-status-dot.disconnected { background: #f85149; }

.tab-name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
}

.tab-close {
  opacity: 0;
  padding: 2px;
  border-radius: 3px;
  flex-shrink: 0;
}

.terminal-tab:hover .tab-close { opacity: 1; }
.tab-close:hover { background: var(--bg-panel); color: #f85149; }

.add-tab-btn {
  padding: 0 12px;
  height: 40px;
  display: flex;
  align-items: center;
  cursor: pointer;
  color: var(--text-secondary);
  flex-shrink: 0;
}

.add-tab-btn:hover { color: #58a6ff; background: var(--bg-hover); }

/* 右键菜单 */
.ctx-menu {
  position: fixed;
  z-index: 9999;
  background: var(--bg-panel);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  padding: 4px;
  min-width: 160px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.4);
}

.ctx-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  font-size: 13px;
  cursor: pointer;
  border-radius: 6px;
  color: var(--text-primary);
  transition: background 0.1s;
}

.ctx-item:hover { background: var(--bg-hover); }
.ctx-item.danger { color: #f85149; }
.ctx-item.danger:hover { background: rgba(248, 81, 73, 0.1); }

/* 快捷命令内嵌面板 */
.snippet-scroll { flex: 1; min-height: 0; }

.snippet-list-inline {
  padding: 8px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.snippet-item-inline {
  background: var(--bg-panel);
  border: 1px solid var(--border-color);
  border-radius: 6px;
  padding: 8px 10px;
  cursor: pointer;
  transition: border-color 0.15s, background 0.15s;
}

.snippet-item-inline:hover {
  border-color: var(--accent-blue);
  background: var(--bg-hover);
}

.snippet-name-inline {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 3px;
}

.snippet-cmd-inline {
  font-size: 11px;
  font-family: monospace;
  color: var(--accent-green);
  background: var(--bg-primary);
  padding: 2px 5px;
  border-radius: 3px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.empty-tip-small {
  text-align: center;
  color: var(--text-secondary);
  font-size: 12px;
  padding: 20px 0;
}

/* 批量命令内嵌面板 */
.batch-panel {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 10px;
  flex: 1;
  overflow: hidden;
}

.batch-label {
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: var(--text-secondary);
  margin-bottom: 6px;
}

.batch-targets {
  flex: 1;
  overflow-y: auto;
}

.batch-tab-item {
  margin-bottom: 4px;
}

.batch-tab-name {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
}

.batch-input-area {
  flex-shrink: 0;
}
</style>
