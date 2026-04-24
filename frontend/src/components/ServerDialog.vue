<template>
  <el-dialog
    :model-value="modelValue"
    @update:model-value="$emit('update:modelValue', $event)"
    :title="editServer ? '编辑服务器' : '添加服务器'"
    width="560px"
    align-center
    @open="onOpen"
  >
    <el-form :model="form" :rules="rules" ref="formRef" label-width="90px" @submit.prevent>
      <!-- 基础信息 -->
      <el-form-item label="服务器别名" prop="name">
        <el-input v-model="form.name" placeholder="例如：生产服务器01" />
      </el-form-item>

      <el-row :gutter="12">
        <el-col :span="16">
          <el-form-item label="主机地址" prop="host">
            <el-input v-model="form.host" placeholder="IP 或域名" />
          </el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item label="端口" prop="port">
            <el-input v-model.number="form.port" placeholder="22" style="width: 100%" />
          </el-form-item>
        </el-col>
      </el-row>

      <el-form-item label="用户名" prop="username">
        <el-input v-model="form.username" placeholder="例如：root" />
      </el-form-item>

      <!-- 认证方式 -->
      <el-form-item label="认证方式">
        <el-radio-group v-model="form.auth_type">
          <el-radio-button label="password">密码</el-radio-button>
          <el-radio-button label="key">私钥</el-radio-button>
        </el-radio-group>
      </el-form-item>

      <el-form-item v-if="form.auth_type === 'password'" label="密码" prop="password">
        <el-input
          v-model="form.password"
          type="password"
          show-password
          :placeholder="editServer ? '留空则不修改' : '请输入SSH密码'"
        />
      </el-form-item>

      <template v-if="form.auth_type === 'key'">
        <el-form-item label="私钥内容" prop="private_key">
          <el-input
            v-model="form.private_key"
            type="textarea"
            :rows="4"
            :placeholder="editServer ? '留空则不修改\n' : '粘贴私钥内容，例如 -----BEGIN OPENSSH PRIVATE KEY-----...'"
            style="font-family: monospace; font-size: 12px"
          />
        </el-form-item>
        <el-form-item label="私钥密码">
          <el-input v-model="form.private_key_passphrase" type="password" show-password placeholder="如无密码则留空" />
        </el-form-item>
      </template>

      <!-- 分组 -->
      <el-form-item label="分组">
        <el-select v-model="form.group_id" placeholder="无分组" clearable style="width: 100%">
          <el-option v-for="g in groups" :key="g.id" :label="g.name" :value="g.id" />
        </el-select>
      </el-form-item>

      <!-- 标签 -->
      <el-form-item label="标签">
        <el-input v-model="form.tags" placeholder="多个标签用逗号分隔，例如：生产,数据库" />
      </el-form-item>

      <!-- 跳板机 -->
      <el-form-item label="跳板机">
        <el-switch v-model="form.proxy_enabled" />
        <span style="margin-left: 10px; font-size: 12px; color: var(--text-secondary)">
          通过跳板机访问内网服务器
        </span>
      </el-form-item>

      <template v-if="form.proxy_enabled">
        <el-row :gutter="12">
          <el-col :span="16">
            <el-form-item label="跳板机IP">
              <el-input v-model="form.proxy_host" placeholder="跳板机 IP" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="端口">
              <el-input v-model.number="form.proxy_port" placeholder="22" style="width: 100%" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="用户名">
              <el-input v-model="form.proxy_username" placeholder="跳板机用户名" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="密码">
              <el-input v-model="form.proxy_password" type="password" show-password placeholder="跳板机密码" />
            </el-form-item>
          </el-col>
        </el-row>
      </template>

      <!-- 备注 -->
      <el-form-item label="备注">
        <el-input v-model="form.notes" type="textarea" :rows="2" placeholder="可选备注信息" />
      </el-form-item>
    </el-form>

    <template #footer>
      <el-button @click="$emit('update:modelValue', false)">取消</el-button>
      <el-button type="primary" :loading="saving" @click="save">
        {{ editServer ? '保存修改' : '添加服务器' }}
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { ElMessage } from 'element-plus'
import { useServerStore } from '@/stores/servers'

const props = defineProps({
  modelValue: Boolean,
  editServer: { type: Object, default: null },
  groups: { type: Array, default: () => [] },
})

const emit = defineEmits(['update:modelValue', 'saved'])
const serverStore = useServerStore()
const formRef = ref()
const saving = ref(false)

const defaultForm = {
  name: '', host: '', port: 22, username: 'root',
  auth_type: 'password', password: '', private_key: '', private_key_passphrase: '',
  group_id: null, tags: '', notes: '',
  proxy_enabled: false, proxy_host: '', proxy_port: 22, proxy_username: '', proxy_password: '',
}

const form = reactive({ ...defaultForm })

const rules = {
  name: [{ required: true, message: '请输入服务器别名', trigger: 'blur' }],
  host: [{ required: true, message: '请输入主机地址', trigger: 'blur' }],
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
}

function onOpen() {
  if (props.editServer) {
    Object.assign(form, {
      ...defaultForm,
      ...props.editServer,
      password: '',
      private_key: '',
    })
  } else {
    Object.assign(form, { ...defaultForm })
  }
}

async function save() {
  await formRef.value?.validate()
  saving.value = true
  try {
    if (props.editServer) {
      await serverStore.updateServer(props.editServer.id, { ...form })
      ElMessage.success('保存成功')
    } else {
      await serverStore.createServer({ ...form })
      ElMessage.success('服务器添加成功')
    }
    emit('saved')
  } finally {
    saving.value = false
  }
}
</script>
