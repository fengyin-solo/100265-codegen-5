<template>
  <section class="page" data-module="noisecomplaint">
    <header class="page-head">
      <div>
        <h2>噪声投诉管理</h2>
        <p class="page-desc">噪声投诉多选批量转办：同一投诉点位一次选上，降噪措施逐条填、转办部门统一记，无效记录单独挑出，退回不回滚已转办记录。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记投诉</button>
        <button class="btn" type="button" @click="exportRows">导出清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <div class="tab-bar">
      <button :class="{ active: view === 'ledger' }" type="button" @click="switchView('ledger')">投诉台账</button>
      <button :class="{ active: view === 'disposal' }" type="button" @click="switchView('disposal')">处置单</button>
    </div>

    <template v-if="view === 'ledger'">
      <form class="filter-bar" @submit.prevent="reload">
        <label class="filter-item">
          <span>投诉编号</span>
          <input v-model="filters.keyword" placeholder="按投诉编号检索" />
        </label>
        <label class="filter-item">
          <span>投诉点位</span>
          <input v-model="filters.location" placeholder="按投诉点位过滤" />
        </label>
        <label class="filter-item">
          <span>投诉状态</span>
          <select v-model="filters.status">
            <option value="">全部</option>
            <option v-for="s in statuses" :key="s" :value="s">{{ s }}</option>
          </select>
        </label>
        <button class="btn" type="submit">查询</button>
        <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
      </form>

      <div v-if="selected.size > 0" class="batch-toolbar">
        <span class="batch-info">已选 <strong>{{ selected.size }}</strong> 条</span>
        <button class="btn" type="button" @click="selectSameLocation">全选同点位</button>
        <button class="btn primary" type="button" @click="openBatchForward()">批量转办</button>
        <button class="btn ghost" type="button" @click="clearSelection">清除选择</button>
      </div>

      <table class="data-table">
        <thead>
          <tr>
            <th class="col-check">
              <input type="checkbox" :checked="allChecked" @change="toggleAll" />
            </th>
            <th v-for="column in columns" :key="column">{{ column }}</th>
            <th>可执行动作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in rows" :key="String(row.id)">
            <td class="col-check">
              <input type="checkbox" :value="row.id" v-model="selected" />
            </td>
            <td v-for="column in columns" :key="column">{{ row[column] ?? '—' }}</td>
            <td class="row-actions">
              <template v-if="canForward(row.status)">
                <button class="link" type="button" @click="openBatchForward([row])">转办</button>
              </template>
              <template v-if="row.status === '已转办'">
                <button class="link" type="button" @click="openReturn(row)">退回</button>
                <button class="link" type="button" @click="closeEntry(row)">办结</button>
              </template>
              <template v-if="row.status === '已退回'">
                <button class="link" type="button" @click="openResubmit(row)">重新提交</button>
                <button class="link" type="button" @click="closeEntry(row)">办结</button>
              </template>
            </td>
          </tr>
          <tr v-if="!rows.length">
            <td :colspan="columns.length + 2" class="empty-state">暂无噪声投诉数据，可先登记投诉</td>
          </tr>
        </tbody>
      </table>

      <footer class="page-foot">
        <span>共 {{ total }} 条噪声投诉记录</span>
        <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
      </footer>
    </template>

    <template v-if="view === 'disposal'">
      <table class="data-table">
        <thead>
          <tr>
            <th v-for="column in disposalColumns" :key="column">{{ column }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in disposals" :key="String(row.id)">
            <td v-for="column in disposalColumns" :key="column">{{ row[column] ?? '—' }}</td>
          </tr>
          <tr v-if="!disposals.length">
            <td :colspan="disposalColumns.length" class="empty-state">暂无处置单数据</td>
          </tr>
        </tbody>
      </table>
      <footer class="page-foot">
        <span>处置单结论与投诉台账保持一致</span>
      </footer>
    </template>

    <!-- 批量转办对话框 -->
    <div v-if="batchDialog.open" class="modal-mask" @click.self="closeBatchForward">
      <div class="modal">
        <header class="modal-head">
          <h3>批量转办噪声投诉</h3>
          <button class="modal-close" type="button" @click="closeBatchForward">×</button>
        </header>
        <div class="modal-body">
          <p class="modal-tip">共 {{ batchDialog.items.length }} 条记录。降噪措施逐条填写（必填），转办部门统一记录。</p>
          <div v-for="item in batchDialog.items" :key="String(item.id)" class="batch-item">
            <div class="batch-item-head">
              <span class="batch-no">{{ item['投诉编号'] }}</span>
              <span class="batch-loc">{{ item['投诉点位'] }}</span>
              <span class="batch-status" :class="statusClass(item.status)">{{ item.status }}</span>
            </div>
            <div v-if="canForward(item.status)" class="batch-item-body">
              <label class="batch-field">
                <span>降噪措施 <em>*</em></span>
                <input v-model="item.measure" placeholder="请填写降噪措施" />
              </label>
            </div>
            <div v-else class="batch-item-invalid">
              <span>当前状态不可转办，提交后将被单独标记并退回</span>
            </div>
          </div>
          <label class="batch-field batch-dept-field">
            <span>转办部门 <em>*</em></span>
            <input v-model="batchDialog.department" placeholder="统一填写转办部门" />
          </label>
        </div>
        <footer class="modal-foot">
          <button class="btn ghost" type="button" @click="closeBatchForward">取消</button>
          <button class="btn primary" type="button" @click="submitBatchForward">提交转办</button>
        </footer>
      </div>
    </div>

    <!-- 退回对话框 -->
    <div v-if="returnDialog.open" class="modal-mask" @click.self="returnDialog.open = false">
      <div class="modal">
        <header class="modal-head">
          <h3>退回投诉</h3>
          <button class="modal-close" type="button" @click="returnDialog.open = false">×</button>
        </header>
        <div class="modal-body">
          <p class="modal-tip">{{ returnDialog.entry?.['投诉编号'] }} 退回后仅该记录变为「已退回」，同批其他已转办记录不回滚。</p>
          <label class="batch-field">
            <span>退回原因 <em>*</em></span>
            <input v-model="returnDialog.reason" placeholder="请填写退回原因" />
          </label>
        </div>
        <footer class="modal-foot">
          <button class="btn ghost" type="button" @click="returnDialog.open = false">取消</button>
          <button class="btn primary" type="button" @click="submitReturn">确认退回</button>
        </footer>
      </div>
    </div>

    <!-- 重新提交对话框 -->
    <div v-if="resubmitDialog.open" class="modal-mask" @click.self="resubmitDialog.open = false">
      <div class="modal">
        <header class="modal-head">
          <h3>重新提交投诉</h3>
          <button class="modal-close" type="button" @click="resubmitDialog.open = false">×</button>
        </header>
        <div class="modal-body">
          <p class="modal-tip">{{ resubmitDialog.entry?.['投诉编号'] }} 补齐降噪措施与转办部门后重新转属地，其他已转办记录不受影响。</p>
          <label class="batch-field">
            <span>降噪措施 <em>*</em></span>
            <input v-model="resubmitDialog.measure" placeholder="请填写降噪措施" />
          </label>
          <label class="batch-field">
            <span>转办部门 <em>*</em></span>
            <input v-model="resubmitDialog.department" placeholder="请填写转办部门" />
          </label>
        </div>
        <footer class="modal-foot">
          <button class="btn ghost" type="button" @click="resubmitDialog.open = false">取消</button>
          <button class="btn primary" type="button" @click="submitResubmit">重新提交</button>
        </footer>
      </div>
    </div>

    <!-- 批量转办结果 -->
    <div v-if="resultBanner" class="result-banner" :class="resultBanner.type">
      <div class="result-content">
        <strong>{{ resultBanner.title }}</strong>
        <p v-if="resultBanner.forwarded.length">已转属地：{{ resultBanner.forwarded.join('、') }}</p>
        <p v-if="resultBanner.returned.length">单独标记：{{ resultBanner.returned.join('、') }}</p>
      </div>
      <button class="modal-close" type="button" @click="resultBanner = null">×</button>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | null>
type BatchItem = Row & { measure: string }

const ENDPOINT = '/api/noisecomplaint'
const columns = ['投诉编号', '投诉点位', '投诉人', '联系电话', '投诉时间', '投诉内容', '降噪措施', '转办部门', '处置结论', '投诉状态']
const disposalColumns = ['处置单编号', '投诉编号', '投诉点位', '降噪措施', '转办部门', '处置结论', '退回原因', '状态']
const statuses = ['待处理', '已转办', '已退回', '已办结']
const stats = ref([
  { label: '待处理', value: 0 },
  { label: '已转办', value: 0 },
  { label: '已退回', value: 0 },
  { label: '已办结', value: 0 },
])

const rows = ref<Row[]>([])
const disposals = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const view = ref<'ledger' | 'disposal'>('ledger')
const filters = ref<Record<string, string>>({})
const selected = ref<Set<number>>(new Set())

const batchDialog = reactive<{ open: boolean; items: BatchItem[]; department: string }>({
  open: false,
  items: [],
  department: '',
})

const returnDialog = reactive<{ open: boolean; entry: Row | null; reason: string }>({
  open: false,
  entry: null,
  reason: '',
})

const resubmitDialog = reactive<{ open: boolean; entry: Row | null; measure: string; department: string }>({
  open: false,
  entry: null,
  measure: '',
  department: '',
})

const resultBanner = ref<{
  type: 'success' | 'warning'
  title: string
  forwarded: string[]
  returned: string[]
} | null>(null)

const allChecked = computed(() => rows.value.length > 0 && rows.value.every((row) => selected.value.has(Number(row.id))))

function canForward(status: unknown): boolean {
  return status === '待处理' || status === '已退回'
}

function statusClass(status: unknown): string {
  if (status === '已转办') return 'tag-forwarded'
  if (status === '已退回') return 'tag-returned'
  if (status === '已办结') return 'tag-closed'
  return 'tag-pending'
}

function resetFilters() {
  filters.value = {}
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  errorMessage.value = '投诉登记入口尚未接入审批流'
}

function switchView(next: 'ledger' | 'disposal') {
  view.value = next
  if (next === 'disposal' && disposals.value.length === 0) {
    void reloadDisposals()
  }
}

function toggleAll(event: Event) {
  const checked = (event.target as HTMLInputElement).checked
  if (checked) {
    rows.value.forEach((row) => selected.value.add(Number(row.id)))
  } else {
    selected.value.clear()
  }
  selected.value = new Set(selected.value)
}

function clearSelection() {
  selected.value = new Set()
}

/** 勾选同一投诉点位的记录一次选上：按已选记录的点位，把当前列表中同点位记录全部选中。 */
function selectSameLocation() {
  if (selected.value.size === 0) return
  const locations = new Set(
    rows.value
      .filter((row) => selected.value.has(Number(row.id)))
      .map((row) => String(row['投诉点位'] ?? '')),
  )
  rows.value.forEach((row) => {
    if (locations.has(String(row['投诉点位'] ?? ''))) {
      selected.value.add(Number(row.id))
    }
  })
  selected.value = new Set(selected.value)
}

function openBatchForward(target?: Row[]) {
  const source = target ?? rows.value.filter((row) => selected.value.has(Number(row.id)))
  if (source.length === 0) {
    errorMessage.value = '请先勾选需要转办的投诉记录'
    return
  }
  errorMessage.value = ''
  batchDialog.items = source.map((row) => ({
    ...row,
    measure: canForward(row.status) ? String(row['降噪措施'] ?? '') : '',
  }))
  batchDialog.department = ''
  batchDialog.open = true
}

function closeBatchForward() {
  batchDialog.open = false
  batchDialog.items = []
  batchDialog.department = ''
}

async function submitBatchForward() {
  errorMessage.value = ''
  // 降噪措施逐条校验，缺失的整批拦下
  const missing = batchDialog.items.filter(
    (item) => canForward(item.status) && !String(item.measure ?? '').trim(),
  )
  if (missing.length > 0) {
    errorMessage.value = `有 ${missing.length} 条降噪措施缺失，不允许提交：${missing.map((item) => item['投诉编号']).join('、')}`
    return
  }
  if (!batchDialog.department.trim()) {
    errorMessage.value = '转办部门未填写，不允许提交'
    return
  }
  try {
    const response = await request(`${ENDPOINT}/batch-forward`, {
      method: 'POST',
      body: JSON.stringify({
        items: batchDialog.items.map((item) => ({
          id: Number(item.id),
          measure: item.measure,
        })),
        department: batchDialog.department,
      }),
    })
    const result = await response.json()
    if (!response.ok || !result.ok) {
      errorMessage.value = result.message || '批量转办未生效'
      return
    }
    resultBanner.value = {
      type: result.returned.length > 0 ? 'warning' : 'success',
      title: result.message,
      forwarded: result.forwarded.map((item: { complaint_no: string }) => item.complaint_no),
      returned: result.returned.map((item: { complaint_no: string; reason: string }) => `${item.complaint_no}（${item.reason}）`),
    }
    closeBatchForward()
    clearSelection()
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '批量转办失败'
  }
}

function openReturn(row: Row) {
  returnDialog.entry = row
  returnDialog.reason = ''
  returnDialog.open = true
}

async function submitReturn() {
  if (!returnDialog.entry) return
  if (!returnDialog.reason.trim()) {
    errorMessage.value = '退回原因未填写，不允许退回'
    return
  }
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${returnDialog.entry.id}/return`, {
      method: 'POST',
      body: JSON.stringify({ reason: returnDialog.reason }),
    })
    const result = await response.json()
    if (!response.ok || !result.ok) {
      errorMessage.value = result.message || '退回未生效'
      return
    }
    returnDialog.open = false
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '退回失败'
  }
}

function openResubmit(row: Row) {
  resubmitDialog.entry = row
  resubmitDialog.measure = String(row['降噪措施'] ?? '')
  resubmitDialog.department = String(row['转办部门'] ?? '')
  resubmitDialog.open = true
}

async function submitResubmit() {
  if (!resubmitDialog.entry) return
  if (!resubmitDialog.measure.trim()) {
    errorMessage.value = '降噪措施缺失，不允许提交'
    return
  }
  if (!resubmitDialog.department.trim()) {
    errorMessage.value = '转办部门未填写，不允许提交'
    return
  }
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${resubmitDialog.entry.id}/resubmit`, {
      method: 'POST',
      body: JSON.stringify({ measure: resubmitDialog.measure, department: resubmitDialog.department }),
    })
    const result = await response.json()
    if (!response.ok || !result.ok) {
      errorMessage.value = result.message || '重新提交未生效'
      return
    }
    resubmitDialog.open = false
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '重新提交失败'
  }
}

async function closeEntry(row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/close`, { method: 'POST' })
    const result = await response.json()
    if (!response.ok || !result.ok) {
      errorMessage.value = result.message || '办结未生效'
      return
    }
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '办结失败'
  }
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams(filters.value as Record<string, string>).toString()
  try {
    const response = await request(`${ENDPOINT}?${query}`)
    if (!response.ok) throw new Error('投诉列表读取失败')
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
    // 统计卡片
    const all = await request(`${ENDPOINT}?size=200`)
    const allPayload = await all.json()
    const allRows: Row[] = allPayload.items ?? []
    stats.value = [
      { label: '待处理', value: allRows.filter((r) => r.status === '待处理').length },
      { label: '已转办', value: allRows.filter((r) => r.status === '已转办').length },
      { label: '已退回', value: allRows.filter((r) => r.status === '已退回').length },
      { label: '已办结', value: allRows.filter((r) => r.status === '已办结').length },
    ]
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '投诉列表读取失败'
  }
}

async function reloadDisposals() {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/disposals?size=200`)
    if (!response.ok) throw new Error('处置单列表读取失败')
    const payload = await response.json()
    disposals.value = payload.items ?? []
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '处置单列表读取失败'
  }
}

onMounted(reload)
</script>

<style scoped>
.tab-bar {
  display: flex;
  gap: 4px;
  margin-bottom: 12px;
  border-bottom: 1px solid var(--border);
}
.tab-bar button {
  border: none;
  background: none;
  padding: 8px 14px;
  cursor: pointer;
  font-size: 13px;
  color: var(--muted);
  border-bottom: 2px solid transparent;
  margin-bottom: -1px;
}
.tab-bar button.active {
  color: var(--brand);
  border-bottom-color: var(--brand);
}
.batch-toolbar {
  display: flex;
  align-items: center;
  gap: 10px;
  background: #eef4ff;
  border: 1px solid #c7d7f5;
  border-radius: 8px;
  padding: 8px 12px;
  margin-bottom: 12px;
}
.batch-info {
  font-size: 13px;
  color: var(--brand);
}
.col-check {
  width: 36px;
  text-align: center;
}
.modal-mask {
  position: fixed;
  inset: 0;
  background: rgba(15, 23, 42, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 100;
}
.modal {
  background: #fff;
  border-radius: 10px;
  width: 640px;
  max-width: 92vw;
  max-height: 86vh;
  display: flex;
  flex-direction: column;
}
.modal-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 14px 18px;
  border-bottom: 1px solid var(--border);
}
.modal-head h3 {
  margin: 0;
  font-size: 15px;
}
.modal-close {
  border: none;
  background: none;
  font-size: 20px;
  cursor: pointer;
  color: var(--muted);
}
.modal-body {
  padding: 16px 18px;
  overflow-y: auto;
}
.modal-tip {
  font-size: 13px;
  color: var(--muted);
  margin: 0 0 12px;
}
.batch-item {
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 10px 12px;
  margin-bottom: 10px;
}
.batch-item-head {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 8px;
}
.batch-no {
  font-weight: 600;
  font-size: 13px;
}
.batch-loc {
  font-size: 12px;
  color: var(--muted);
}
.batch-status {
  margin-left: auto;
  font-size: 12px;
  padding: 2px 8px;
  border-radius: 10px;
}
.tag-pending { background: #fef3c7; color: #92400e; }
.tag-forwarded { background: #dbeafe; color: #1e40af; }
.tag-returned { background: #fee2e2; color: #991b1b; }
.tag-closed { background: #d1fae5; color: #065f46; }
.batch-field {
  display: block;
}
.batch-field span {
  display: block;
  font-size: 12px;
  color: var(--muted);
  margin-bottom: 4px;
}
.batch-field em {
  color: #b42318;
  font-style: normal;
}
.batch-field input {
  width: 100%;
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 6px 10px;
  font-size: 13px;
}
.batch-dept-field {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px dashed var(--border);
}
.batch-item-invalid {
  font-size: 12px;
  color: #b42318;
}
.modal-foot {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding: 12px 18px;
  border-top: 1px solid var(--border);
}
.result-banner {
  position: fixed;
  bottom: 20px;
  right: 20px;
  background: #fff;
  border: 1px solid var(--border);
  border-left: 4px solid var(--brand);
  border-radius: 8px;
  padding: 12px 16px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.12);
  z-index: 110;
  max-width: 420px;
  display: flex;
  gap: 12px;
  align-items: flex-start;
}
.result-banner.warning {
  border-left-color: #d97706;
}
.result-content strong {
  font-size: 13px;
}
.result-content p {
  margin: 4px 0 0;
  font-size: 12px;
  color: var(--muted);
}
</style>
