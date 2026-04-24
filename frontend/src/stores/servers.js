import { defineStore } from 'pinia'
import { ref } from 'vue'
import api from '@/utils/api'

export const useServerStore = defineStore('servers', () => {
  const servers = ref([])
  const groups = ref([])
  const loading = ref(false)

  async function fetchServers(search = '', groupId = null) {
    loading.value = true
    try {
      const params = {}
      if (search) params.search = search
      if (groupId !== null) params.group_id = groupId
      const res = await api.get('/api/servers', { params })
      servers.value = res.data
    } finally {
      loading.value = false
    }
  }

  async function fetchGroups() {
    const res = await api.get('/api/servers/groups')
    groups.value = res.data
  }

  async function createServer(data) {
    const res = await api.post('/api/servers', data)
    await fetchServers()
    return res.data
  }

  async function updateServer(id, data) {
    const res = await api.put(`/api/servers/${id}`, data)
    await fetchServers()
    return res.data
  }

  async function deleteServer(id) {
    await api.delete(`/api/servers/${id}`)
    await fetchServers()
  }

  async function toggleFavorite(id) {
    const res = await api.post(`/api/servers/${id}/favorite`)
    const server = servers.value.find(s => s.id === id)
    if (server) server.is_favorite = res.data.is_favorite
  }

  async function createGroup(data) {
    const res = await api.post('/api/servers/groups', data)
    await fetchGroups()
    return res.data
  }

  return {
    servers, groups, loading,
    fetchServers, fetchGroups, createServer, updateServer, deleteServer,
    toggleFavorite, createGroup,
  }
})
