import { defineStore } from 'pinia'
import { ref } from 'vue'
import api from '@/utils/api'
import { ElMessage } from 'element-plus'

export const useTerminalStore = defineStore('terminal', () => {
  // 所有标签页
  const tabs = ref([])
  // 当前活跃标签页 ID
  const activeTabId = ref(null)

  // 从后端恢复会话列表
  async function restoreSessions() {
    try {
      const res = await api.get('/api/sessions')
      const sessions = res.data
      if (sessions.length > 0) {
        tabs.value = sessions.map(s => ({
          id: s.id,
          tabId: s.tab_id,
          name: s.tab_name,
          color: s.tab_color,
          serverId: s.server_id,
          status: s.status,
          cols: s.terminal_cols,
          rows: s.terminal_rows,
        }))
        activeTabId.value = tabs.value[0].id
        return true
      }
    } catch (e) {
      console.warn('恢复会话失败', e)
    }
    return false
  }

  // 连接新服务器
  async function connect(serverId, options = {}) {
    const res = await api.post('/api/sessions/connect', null, {
      params: {
        server_id: serverId,
        tab_name: options.tabName || '',
        tab_color: options.tabColor || '#409EFF',
        keepalive_hours: options.keepaliveHours || 24,
        cols: options.cols || 80,
        rows: options.rows || 24,
      },
    })
    const session = res.data
    const tab = {
      id: session.session_id,
      tabId: session.tab_id,
      name: session.tab_name,
      color: session.tab_color,
      serverId: session.server_id,
      serverName: session.server_name,
      serverHost: session.server_host,
      status: 'connecting',
    }
    tabs.value.push(tab)
    activeTabId.value = tab.id
    return tab
  }

  // 关闭标签页
  async function closeTab(sessionId) {
    try {
      await api.delete(`/api/sessions/${sessionId}`)
    } catch (e) {
      console.error('关闭会话失败', e)
      ElMessage.error('关闭会话失败，请重试')
      return  // 删除失败时不移除前端标签，避免状态不一致
    }
    const idx = tabs.value.findIndex(t => t.id === sessionId)
    tabs.value.splice(idx, 1)
    
    if (activeTabId.value === sessionId) {
      activeTabId.value = tabs.value.length > 0
        ? tabs.value[Math.max(0, idx - 1)].id
        : null
    }
  }

  function setActive(sessionId) {
    activeTabId.value = sessionId
  }

  function updateTabStatus(sessionId, status) {
    const tab = tabs.value.find(t => t.id === sessionId)
    if (tab) tab.status = status
  }

  return {
    tabs, activeTabId,
    restoreSessions, connect, closeTab, setActive, updateTabStatus,
  }
})
