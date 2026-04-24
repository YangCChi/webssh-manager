<template>
  <el-drawer
    :model-value="modelValue"
    @update:model-value="$emit('update:modelValue', $event)"
    title="常用命令"
    size="400px"
    direction="rtl"
  >
    <template #header>
      <div style="display: flex; align-items: center; gap: 12px; flex: 1">
        <span style="font-size: 15px; font-weight: 600">常用命令</span>
        <el-button size="small" type="primary" @click="showAdd = true">
          <el-icon><Plus /></el-icon> 添加
        </el-button>
      </div>
    </template>

    <el-input
      v-model="search"
      placeholder="搜索命令..."
      :prefix-icon="Search"
      clearable
      style="margin-bottom: 12px"
    />

    <div class="snippet-categories">
      <el-check-tag
        v-for="cat in categories"
        :key="cat"
        :checked="selectedCat === cat"
        @change="selectedCat = selectedCat === cat ? '' : cat"
        style="margin-right: 6px; margin-bottom: 6px; font-size: 12px"
      >{{ cat }}</el-check-tag>
    </div>

    <div class="snippet-list">
      <div
        v-for="s in filteredSnippets"
        :key="s.id"
        class="snippet-item"
        @click="sendSnippet(s)"
      >
        <div class="snippet-name">{{ s.name }}</div>
        <div class="snippet-cmd">{{ s.command }}</div>
        <div v-if="s.description" class="snippet-desc">{{ s.description }}</div>
        <div class="snippet-actions">
          <el-tag size="small" type="info">{{ s.category }}</el-tag>
          <span style="flex: 1" />
          <el-button text size="small" @click.stop="deleteSnippet(s.id)">
            <el-icon color="#f85149"><Delete /></el-icon>
          </el-button>
        </div>
      </div>

      <el-empty v-if="!filteredSnippets.length" description="暂无命令" :image-size="60" />
    </div>

    <!-- 添加对话框 -->
    <el-dialog v-model="showAdd" title="添加命令" width="440px" append-to-body align-center>
      <el-form :model="addForm" label-width="70px">
        <el-form-item label="名称">
          <el-input v-model="addForm.name" placeholder="命令名称" />
        </el-form-item>
        <el-form-item label="命令">
          <el-input v-model="addForm.command" type="textarea" :rows="3" placeholder="例如：docker ps -a" style="font-family: monospace" />
        </el-form-item>
        <el-form-item label="分类">
          <el-input v-model="addForm.category" placeholder="默认：通用" />
        </el-form-item>
        <el-form-item label="说明">
          <el-input v-model="addForm.description" placeholder="可选" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showAdd = false">取消</el-button>
        <el-button type="primary" @click="addSnippet">添加</el-button>
      </template>
    </el-dialog>
  </el-drawer>
</template>

<script setup>
import { ref, computed, onMounted, reactive } from 'vue'
import { ElMessage } from 'element-plus'
import { Plus, Search, Delete } from '@element-plus/icons-vue'
import api from '@/utils/api'

const props = defineProps({ modelValue: Boolean })
const emit = defineEmits(['update:modelValue', 'send'])

const snippets = ref([])
const search = ref('')
const selectedCat = ref('')
const showAdd = ref(false)
const addForm = reactive({ name: '', command: '', category: '通用', description: '' })

const categories = computed(() => [...new Set(snippets.value.map(s => s.category))])

const filteredSnippets = computed(() => {
  return snippets.value.filter(s => {
    const matchSearch = !search.value || s.name.includes(search.value) || s.command.includes(search.value)
    const matchCat = !selectedCat.value || s.category === selectedCat.value
    return matchSearch && matchCat
  })
})

async function fetchSnippets() {
  const res = await api.get('/api/snippets')
  snippets.value = res.data
}

async function addSnippet() {
  if (!addForm.name || !addForm.command) return
  await api.post('/api/snippets', { ...addForm })
  ElMessage.success('添加成功')
  showAdd.value = false
  addForm.name = addForm.command = addForm.description = ''
  addForm.category = '通用'
  fetchSnippets()
}

async function deleteSnippet(id) {
  await api.delete(`/api/snippets/${id}`)
  snippets.value = snippets.value.filter(s => s.id !== id)
}

async function sendSnippet(s) {
  await api.post(`/api/snippets/${s.id}/use`)
  s.use_count = (s.use_count || 0) + 1
  emit('send', s.command)
}

onMounted(fetchSnippets)
</script>

<style scoped>
.snippet-categories { margin-bottom: 12px; }

.snippet-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.snippet-item {
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  padding: 10px 12px;
  cursor: pointer;
  transition: border-color 0.15s, background 0.15s;
}

.snippet-item:hover {
  border-color: var(--accent-blue);
  background: var(--bg-hover);
}

.snippet-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 4px;
}

.snippet-cmd {
  font-size: 12px;
  font-family: monospace;
  color: var(--accent-green);
  background: var(--bg-primary);
  padding: 3px 6px;
  border-radius: 4px;
  margin-bottom: 4px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.snippet-desc {
  font-size: 11px;
  color: var(--text-secondary);
  margin-bottom: 4px;
}

.snippet-actions {
  display: flex;
  align-items: center;
  gap: 6px;
}
</style>
