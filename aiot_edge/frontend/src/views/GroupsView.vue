<template>
  <div class="groups-page">
    <!-- 汇总卡片 -->
    <el-row :gutter="16" class="stats-row">
      <el-col :xs="24" :sm="8">
        <StatCard label="分组总数" :value="groups.length" icon="Collection" color="var(--primary)" />
      </el-col>
      <el-col :xs="24" :sm="8">
        <StatCard label="已分组设备" :value="groupedCount" icon="Connection" color="var(--success)" />
      </el-col>
      <el-col :xs="24" :sm="8">
        <StatCard label="未分组设备" :value="ungroupedCount" icon="FolderOpened" color="var(--text-2)" />
      </el-col>
    </el-row>

    <!-- 分组列表 -->
    <el-card>
      <template #header>
        <div class="card-header">
          <span class="card-title"><el-icon><Collection /></el-icon>协同分组管理</span>
          <el-button type="primary" @click="openCreate">
            <el-icon><Plus /></el-icon>
            新建分组
          </el-button>
        </div>
      </template>

      <el-skeleton v-if="loading" :rows="4" animated style="padding: 8px 24px" />
      <el-empty v-else-if="!groups.length" description="暂无分组，点击右上角「新建分组」开始协同管理" />

      <el-row v-else :gutter="16">
        <el-col :span="8" v-for="g in groups" :key="g.id">
          <div class="group-card">
            <div class="group-head">
              <el-icon class="group-icon"><FolderOpened /></el-icon>
              <span class="group-name">{{ g.name }}</span>
            </div>
            <div class="group-desc">{{ g.description || '暂无描述' }}</div>
            <div class="group-meta">
              <span>设备 <b style="color:var(--text-1)">{{ g.device_count ?? 0 }}</b></span>
              <span>在线 <b style="color:var(--success)">{{ g.online_count ?? 0 }}</b></span>
            </div>
            <div class="group-actions">
              <el-button size="small" type="primary" plain @click="openDetail(g)">查看</el-button>
              <el-button size="small" @click="openEdit(g)">编辑</el-button>
              <el-button size="small" type="danger" plain @click="handleDelete(g)">删除</el-button>
            </div>
          </div>
        </el-col>
      </el-row>
    </el-card>

    <!-- 新建/编辑分组对话框 -->
    <el-dialog v-model="dialogVisible" :title="isEdit ? '编辑分组' : '新建分组'" width="440px">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="80px">
        <el-form-item label="分组名称" prop="name">
          <el-input v-model="form.name" placeholder="如 核心网络区" />
        </el-form-item>
        <el-form-item label="分组描述">
          <el-input v-model="form.description" type="textarea" :rows="2" placeholder="描述该分组的作用或协同场景" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleSave">保存</el-button>
      </template>
    </el-dialog>

    <!-- 分组详情抽屉 -->
    <el-drawer v-model="drawerVisible" :title="selectedGroup.name" size="640px">
      <div class="drawer-body">
        <div class="drawer-desc">{{ selectedGroup.description || '暂无描述' }}</div>
        <div class="drawer-toolbar">
          <span class="cell-sub">组内设备 {{ selectedGroup.devices?.length ?? 0 }} 台</span>
          <el-button size="small" type="primary" plain @click="openAssign">
            <el-icon><Plus /></el-icon>
            添加设备
          </el-button>
        </div>

        <el-table :data="selectedGroup.devices || []" stripe>
          <el-table-column prop="device_code" label="设备编号" width="110" />
          <el-table-column prop="name" label="设备名称" width="140" />
          <el-table-column prop="device_type" label="类型" width="90" />
          <el-table-column label="状态" width="96">
            <template #default="{ row }">
              <span class="status-dot" :class="deviceStatus(row.status).cls"></span>
              <span :style="{ color: deviceStatus(row.status).color }">{{ deviceStatus(row.status).text }}</span>
            </template>
          </el-table-column>
          <el-table-column label="CPU" width="90">
            <template #default="{ row }">{{ formatPercent(row.latest_cpu) }}</template>
          </el-table-column>
          <el-table-column label="操作" width="100">
            <template #default="{ row }">
              <el-button size="small" type="danger" plain @click="handleRemoveDevice(row)">移出</el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </el-drawer>

    <!-- 添加设备对话框 -->
    <el-dialog v-model="assignVisible" title="添加设备到分组" width="480px">
      <el-select v-model="assignDeviceIds" multiple filterable placeholder="选择要加入分组的设备" style="width:100%">
        <el-option
          v-for="d in candidateDevices"
          :key="d.id"
          :label="`${d.device_code} · ${d.name}`"
          :value="d.id"
        />
      </el-select>
      <template #footer>
        <el-button @click="assignVisible = false">取消</el-button>
        <el-button type="primary" :disabled="!assignDeviceIds.length" @click="handleAssign">确认添加</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import request from '../api/request'
import { deviceStatus } from '../utils/status'
import StatCard from '../components/StatCard.vue'

const groups = ref([])
const ungroupedCount = ref(0)
const loading = ref(false)
const allDevices = ref([])

const groupedCount = computed(() => groups.value.reduce((s, g) => s + (g.device_count || 0), 0))

// 新建/编辑
const dialogVisible = ref(false)
const isEdit = ref(false)
const editId = ref(null)
const formRef = ref(null)
const form = reactive({ name: '', description: '' })
const rules = { name: [{ required: true, message: '分组名称不能为空', trigger: 'blur' }] }

// 详情抽屉
const drawerVisible = ref(false)
const selectedGroup = ref({})

// 添加设备
const assignVisible = ref(false)
const assignDeviceIds = ref([])

const candidateDevices = computed(() => {
  const groupIds = new Set((selectedGroup.value.devices || []).map((d) => d.id))
  return allDevices.value.filter((d) => !groupIds.has(d.id))
})

async function loadGroups() {
  loading.value = true
  try {
    const res = await request.get('/groups')
    groups.value = res.data.items
    ungroupedCount.value = res.data.ungrouped_count
  } catch (e) {
    ElMessage.error('加载分组失败')
  } finally {
    loading.value = false
  }
}

function openCreate() {
  isEdit.value = false
  editId.value = null
  form.name = ''
  form.description = ''
  dialogVisible.value = true
}

function openEdit(g) {
  isEdit.value = true
  editId.value = g.id
  form.name = g.name
  form.description = g.description || ''
  dialogVisible.value = true
}

async function handleSave() {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return
  try {
    if (isEdit.value) {
      await request.put(`/groups/${editId.value}`, { name: form.name, description: form.description })
      ElMessage.success('分组已更新')
    } else {
      await request.post('/groups', { name: form.name, description: form.description })
      ElMessage.success('分组已创建')
    }
    dialogVisible.value = false
    loadGroups()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '操作失败')
  }
}

async function handleDelete(g) {
  try {
    await ElMessageBox.confirm(`确认删除分组「${g.name}」？组内设备将变为未分组。`, '警告', {
      type: 'warning',
      confirmButtonText: '确认删除',
      cancelButtonText: '取消',
    })
    await request.delete(`/groups/${g.id}`)
    ElMessage.success('已删除')
    loadGroups()
  } catch (e) {
    if (e !== 'cancel' && e !== 'close') {
      ElMessage.error(e.response?.data?.detail || '删除分组失败')
    }
  }
}

async function openDetail(g) {
  try {
    const res = await request.get(`/groups/${g.id}`)
    selectedGroup.value = res.data
    drawerVisible.value = true
  } catch (e) {
    ElMessage.error('加载分组详情失败')
  }
}

async function loadAllDevices() {
  try {
    const res = await request.get('/devices')
    allDevices.value = res.data
  } catch (e) {
    allDevices.value = []
    ElMessage.error('加载设备列表失败')
  }
}

async function openAssign() {
  assignDeviceIds.value = []
  await loadAllDevices()
  assignVisible.value = true
}

function formatPercent(value) {
  const n = Number(value)
  return Number.isFinite(n) ? `${n.toFixed(1)}%` : '-'
}

async function handleAssign() {
  try {
    await request.post(`/groups/${selectedGroup.value.id}/devices`, {
      device_ids: assignDeviceIds.value,
    })
    ElMessage.success('设备已加入分组')
    assignVisible.value = false
    openDetail({ id: selectedGroup.value.id })
    loadGroups()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '操作失败')
  }
}

async function handleRemoveDevice(device) {
  try {
    await request.delete(`/groups/${selectedGroup.value.id}/devices/${device.id}`)
    ElMessage.success('设备已移出分组')
    openDetail({ id: selectedGroup.value.id })
    loadGroups()
  } catch (e) {
    ElMessage.error('操作失败')
  }
}

onMounted(loadGroups)
</script>

<style scoped>
.groups-page {
  display: flex;
  flex-direction: column;
  gap: var(--sp-24);
}

.stats-row {
  margin: 0;
}

.group-card {
  border: 1px solid var(--border);
  border-radius: var(--radius-card);
  background: var(--bg-surface);
  padding: var(--sp-24);
  margin-bottom: var(--sp-16);
  transition: var(--transition);
}

.group-card:hover {
  transform: translateY(-3px);
  box-shadow: var(--shadow-hover);
}

.group-head {
  display: flex;
  align-items: center;
  gap: var(--sp-8);
}

.group-icon {
  color: var(--primary);
  font-size: 18px;
}

.group-name {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-1);
}

.group-desc {
  font-size: 13px;
  color: var(--text-2);
  margin: var(--sp-16) 0;
  min-height: 20px;
}

.group-meta {
  display: flex;
  gap: var(--sp-24);
  font-size: 13px;
  color: var(--text-3);
  padding: var(--sp-16) 0;
  border-top: 1px solid var(--border);
  margin-bottom: var(--sp-16);
}

.group-actions {
  display: flex;
  gap: var(--sp-8);
}

.drawer-body {
  display: flex;
  flex-direction: column;
  gap: var(--sp-16);
}

.drawer-desc {
  font-size: 13px;
  color: var(--text-2);
}

.drawer-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
</style>
