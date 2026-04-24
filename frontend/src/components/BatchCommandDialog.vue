<template>
  <el-dialog
    :model-value="modelValue"
    @update:model-value="$emit('update:modelValue', $event)"
    title="批量发送命令"
    width="520px"
    align-center
  >
    <div class="batch-info">
      <el-icon color="#d29922"><Warning /></el-icon>
      <span>批量命令会同时发送到选中的所有终端，请谨慎操作</span>
    </div>

    <el-form :model="form" label-width="80px" style="margin-top: 16px">
      <el-form-item label="目标终端">
        <el-checkbox-group v-model="form.selectedIds">
          <div v-for="tab in tabs" :key="tab.id" style="margin-bottom: 6px">
            <el-checkbox :label="tab.id">
              <span class="tab-check-label">
                <span class="tab-dot" :style="{ background: tab.color }" />
                {{ tab.name }}
                <span class="tab-host" v-if="tab.serverHost">（{{ tab.serverHost }}）</span>
              </span>
            </el-checkbox>
          </div>
        </el-checkbox-group>
      </el-form-item>

      <el-form-item label="命令">
        <el-input
          v-model="form.command"
          type="textarea"
          :rows="3"
          placeholder="输入要批量执行的命令"
          style="font-family: monospace; font-size: 13px"
        />
      </el-form-item>

      <el-form-item label="发送间隔">
        <el-input-number
          v-model="form.interval"
          :min="0"
          :max="5000"
          :step="100"
          style="width: 160px"
        />
        <span style="margin-left: 8px; font-size: 12px; color: var(--text-secondary)">毫秒</span>
      </el-form-item>
    </el-form>

    <template #footer>
      <el-button @click="$emit('update:modelValue', false)">取消</el-button>
      <el-button
        type="warning"
        :loading="sending"
        :disabled="!form.selectedIds.length || !form.command"
        @click="sendBatch"
      >
        发送到 {{ form.selectedIds.length }} 个终端
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { Warning } from '@element-plus/icons-vue'
import api from '@/utils/api'

const props = defineProps({
  modelValue: Boolean,
  tabs: { type: Array, default: () => [] },
})
const emit = defineEmits(['update:modelValue'])

const sending = ref(false)
const form = reactive({ selectedIds: [], command: '', interval: 100 })

// 默认全选
watch(() => props.tabs, (tabs) => {
  form.selectedIds = tabs.map(t => t.id)
}, { immediate: true })

async function sendBatch() {
  if (!form.command.trim()) return
  sending.value = true
  try {
    const res = await api.post('/api/batch-command', {
      session_ids: form.selectedIds,
      command: form.command,
      interval_ms: form.interval,
    })
    ElMessage.success(`已发送到 ${res.data.sent.length} 个终端`)
    if (res.data.failed.length) {
      ElMessage.warning(`${res.data.failed.length} 个终端发送失败`)
    }
    emit('update:modelValue', false)
  } finally {
    sending.value = false
  }
}
</script>

<style scoped>
.batch-info {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  background: rgba(210, 153, 34, 0.1);
  border-radius: 8px;
  font-size: 13px;
  color: var(--text-primary);
  border: 1px solid rgba(210, 153, 34, 0.3);
}

.tab-check-label {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
}

.tab-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.tab-host {
  color: var(--text-secondary);
  font-size: 12px;
}
</style>
