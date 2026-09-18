<template>
  <div class="devices-page">
    <el-card>
      <template #header>
        <div class="card-header">
          <span class="card-title">
            <el-icon><Monitor /></el-icon>
            设备管理
          </span>
          <el-button type="primary" @click="openAdd">
            <el-icon><Plus /></el-icon>
            添加设备
          </el-button>
        </div>
      </template>

      <el-skeleton v-if="loading" :rows="6" animated style="padding: 8px 24px" />
      <el-table v-else :data="devices" stripe>
        <el-table-column prop="device_code" label="设备编号" width="110" />
        <el-table-column prop="name" label="设备名称" width="140" />
        <el-table-column prop="device_type" label="类型" width="90" />
        <el-table-column prop="location" label="位置" width="120">
          <template #default="{ row }">{{ row.location || '-' }}</template>
        </el-table-column>
        <el-table-column label="状态" width="96">
          <template #default="{ row }">
            <span class="status-dot" :class="deviceStatus(row.status).cls"></span>
            <span :style="{ color: deviceStatus(row.status).color }">{{ deviceStatus(row.status).text }}</span>
          </template>
        </el-table-column>
        <el-table-column label="CPU" width="90">
          <template #default="{ row }">{{ row.latest_cpu?.toFixed(1) ?? '-' }}%</template>
        </el-table-column>
        <el-table-column label="内存" width="90">
          <template #default="{ row }">{{ row.latest_memory?.toFixed(1) ?? '-' }}%</template>
        </el-table-column>
        <el-table-column label="延迟" width="90">
          <template #default="{ row }">{{ row.latest_latency?.toFixed(1) ?? '-' }}ms</template>
        </el-table-column>
        <el-table-column label="最近上报" width="170">
          <template #default="{ row }">
            {{ row.last_seen_at ? new Date(row.last_seen_at).toLocaleString('zh-CN') : '-' }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="240" fixed="right">
          <template #default="{ row }">
            <el-button size="small" type="primary" plain @click="goDetail(row)">详情</el-button>
            <el-button size="small" @click="openEdit(row)">编辑</el-button>
            <el-button size="small" type="danger" plain @click="handleDelete(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 添加/编辑对话框 -->
    <el-dialog
      v-model="dialogVisible"
      :title="isEdit ? '编辑设备' : '添加设备'"
      width="500px"
    >
      <el-form ref="formRef" :model="form" :rules="rules" label-width="100px">
        <el-form-item label="设备编号" prop="device_code">
          <el-input v-model="form.device_code" :disabled="isEdit" placeholder="如 DEV-001" />
        </el-form-item>
        <el-form-item label="设备名称" prop="name">
          <el-input v-model="form.name" placeholder="设备名称" />
        </el-form-item>
        <el-form-item label="设备类型" prop="device_type">
          <el-select v-model="form.device_type" style="width:100%">
            <el-option value="路由器" />
            <el-option value="交换机" />
            <el-option value="网关" />
            <el-option value="传感器" />
            <el-option value="未知" />
          </el-select>
        </el-form-item>
        <el-form-item label="部署位置">
          <el-input v-model="form.location" placeholder="如 机房A-3号柜" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleSave">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import request from '../api/request'
import { deviceStatus } from '../utils/status'

const router = useRouter()
const devices = ref([])
const loading = ref(false)
const dialogVisible = ref(false)
const isEdit = ref(false)
const editId = ref(null)

const formRef = ref(null)
const form = reactive({
  device_code: '',
  name: '',
  device_type: '未知',
  location: '',
})

const rules = {
  device_code: [{ required: true, message: '设备编号不能为空' }],
  name: [{ required: true, message: '设备名称不能为空' }],
  device_type: [{ required: true, message: '请选择设备类型' }],
}

async function loadDevices() {
  loading.value = true
  try {
    const res = await request.get('/devices')
    devices.value = res.data
  } catch (e) {
    ElMessage.error('加载设备列表失败')
  } finally {
    loading.value = false
  }
}

function goDetail(row) {
  router.push(`/devices/${row.id}`)
}

function openAdd() {
  isEdit.value = false
  editId.value = null
  form.device_code = ''
  form.name = ''
  form.device_type = '未知'
  form.location = ''
  dialogVisible.value = true
}

function openEdit(row) {
  isEdit.value = true
  editId.value = row.id
  form.device_code = row.device_code
  form.name = row.name
  form.device_type = row.device_type
  form.location = row.location || ''
  dialogVisible.value = true
}

async function handleSave() {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return

  try {
    if (isEdit.value) {
      await request.put(`/devices/${editId.value}`, {
        name: form.name,
        device_type: form.device_type,
        location: form.location,
      })
      ElMessage.success('设备已更新')
    } else {
      await request.post('/devices', { ...form })
      ElMessage.success('设备已添加')
    }
    dialogVisible.value = false
    loadDevices()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '操作失败')
  }
}

async function handleDelete(row) {
  try {
    await ElMessageBox.confirm(`确认删除设备 ${row.name}？将同时删除其所有数据和告警记录。`, '警告', {
      type: 'warning',
      confirmButtonText: '确认删除',
      cancelButtonText: '取消',
    })
    await request.delete(`/devices/${row.id}`)
    ElMessage.success('已删除')
    loadDevices()
  } catch {
    // cancelled
  }
}

onMounted(loadDevices)
</script>
