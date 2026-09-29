<template>
  <section class="page" data-module="noisecomplaint">
    <header class="page-head">
      <div>
        <h2>噪声投诉管理</h2>
        <p class="page-desc">勾选一条即可带起同一投诉点位的记录，降噪措施逐条填、转办部门统一记；确认无效的单独剔除，只把有效投诉转给属地。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" :disabled="!selectedIds.length" @click="openBatch">
          批量提交转办（{{ selectedIds.length }}）
        </button>
        <button class="btn" type="button" @click="exportRows">导出投诉台账</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label class="filter-item">
        <span>投诉编号</span>
        <input v-model="filters.keyword" placeholder="按投诉编号检索" />
      </label>
      <label class="filter-item">
        <span>投诉点位</span>
        <input v-model="filters.point" placeholder="按投诉点位检索" />
      </label>
      <label class="filter-item">
        <span>投诉状态</span>
        <select v-model="filters.status">
          <option value="">全部</option>
          <option v-for="status in statuses" :key="status" :value="status">{{ status }}</option>
        </select>
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th>
            <input
              type="checkbox"
              :checked="allSubmittableChecked"
              title="选中本页全部可提交记录"
              @change="toggleAllSubmittable"
            />
          </th>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td>
            <input
              type="checkbox"
              :checked="selectedIds.includes(Number(row.id))"
              :disabled="!submittable(row)"
              :title="submittable(row) ? '勾选后同一投诉点位的记录会一次选上' : '当前状态不可提交'"
              @change="togglePointGroup(row)"
            />
          </td>
          <td v-for="column in columns" :key="column">
            <button v-if="column === '投诉编号'" class="link" type="button" @click="openDetail(row)">
              {{ row[column] ?? '—' }}
            </button>
            <span v-else-if="column === '投诉状态'">{{ row.status ?? '—' }}</span>
            <template v-else>{{ row[column] ?? '—' }}</template>
          </td>
          <td class="row-actions">
            <button
              v-for="action in rowActions(row)"
              :key="action"
              class="link"
              type="button"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
            <span v-if="!rowActions(row).length">—</span>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 2" class="empty-state">暂无噪声投诉数据</td>
        </tr>
      </tbody>
    </table>

    <section v-if="batchOpen" class="batch-panel">
      <h3>批量提交转办（{{ batchItems.length }} 件）</h3>
      <p class="panel-hint">
        降噪措施逐条填写，缺失的不允许提交；结论为「有效」的统一按转办部门转给属地，「无效」的单独剔除、不转办。
      </p>
      <label class="filter-item department-item">
        <span>转办部门（整批统一）</span>
        <input v-model="department" placeholder="如：属地生态环境所" />
      </label>
      <table class="data-table">
        <thead>
          <tr><th>投诉编号</th><th>投诉点位</th><th>降噪措施（逐条填）</th><th>核实结论</th></tr>
        </thead>
        <tbody>
          <tr v-for="item in batchItems" :key="item.id">
            <td>{{ item.投诉编号 }}</td>
            <td>{{ item.投诉点位 }}</td>
            <td>
              <input
                v-model="item.measure"
                class="measure-input"
                :class="{ 'input-invalid': !item.measure.trim() }"
                placeholder="必填：填写降噪措施"
              />
              <span v-if="!item.measure.trim()" class="error-text">降噪措施缺失，不允许提交</span>
            </td>
            <td>
              <select v-model="item.conclusion">
                <option value="有效">有效</option>
                <option value="无效">无效</option>
              </select>
            </td>
          </tr>
        </tbody>
      </table>
      <div class="panel-actions">
        <button class="btn primary" type="button" :disabled="!canSubmit" @click="submitBatch">
          {{ submitting ? '提交中…' : '确认提交' }}
        </button>
        <button class="btn ghost" type="button" @click="closeBatch">取消</button>
        <span v-if="needsDepartment && !department.trim()" class="error-text">含有效投诉，转办部门不能为空</span>
      </div>
    </section>

    <section v-if="detail" class="batch-panel">
      <h3>处置单流水：{{ detail.投诉编号 }}</h3>
      <p class="panel-hint">
        台账核实结论：{{ detail.核实结论 || '—' }}；
        <span :class="detail.consistent ? 'ok-text' : 'error-text'">
          {{ detail.consistent ? '台账与处置单结论一致' : '台账与处置单结论不一致，请核查' }}
        </span>
      </p>
      <table class="data-table">
        <thead>
          <tr><th>处置单号</th><th>批次号</th><th>结论</th><th>降噪措施</th><th>转办部门</th><th>提交时间</th></tr>
        </thead>
        <tbody>
          <tr v-for="sheet in detailSheets" :key="sheet.单号">
            <td>{{ sheet.单号 }}</td>
            <td>{{ sheet.批次号 }}</td>
            <td>{{ sheet.结论 }}</td>
            <td>{{ sheet.降噪措施 }}</td>
            <td>{{ sheet.转办部门 || '—' }}</td>
            <td>{{ sheet.提交时间 }}</td>
          </tr>
          <tr v-if="!detailSheets.length">
            <td colspan="6" class="empty-state">尚未提交过处置单</td>
          </tr>
        </tbody>
      </table>
      <div class="panel-actions">
        <button class="btn ghost" type="button" @click="detail = null">收起</button>
      </div>
    </section>

    <footer class="page-foot">
      <span>共 {{ total }} 条噪声投诉记录</span>
      <span v-if="resultMessage" class="ok-text">{{ resultMessage }}</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
    <div v-if="failedReasons.length" class="failed-list">
      <p class="error-text">以下记录未提交成功，已保留在提交面板中，修正后可重新提交：</p>
      <ul>
        <li v-for="failure in failedReasons" :key="failure.id">#{{ failure.id }}：{{ failure.reason }}</li>
      </ul>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Row = {
  id: number
  status?: string
  [key: string]: unknown
}

type DisposalSheet = {
  单号: string
  批次号: string
  结论: string
  降噪措施: string
  转办部门: string
  提交时间: string
}

type Detail = {
  id: number
  投诉编号?: string
  核实结论?: string
  consistent?: boolean
  处置单?: DisposalSheet[]
}

type BatchItem = {
  id: number
  投诉编号: string
  投诉点位: string
  measure: string
  conclusion: '有效' | '无效'
}

type BatchResult = {
  ok: boolean
  message: string
  failed: { id: number; reason: string }[]
}

const ENDPOINT = '/api/noisecomplaint'
const columns = ["投诉编号", "投诉点位", "投诉时间", "投诉人", "噪声源", "投诉内容", "降噪措施", "核实结论", "转办部门", "投诉状态"]
const statuses = ["待提交", "已转办", "已退回", "无效投诉", "已办结"]
const SUBMITTABLE = ["待提交", "已退回"]

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const resultMessage = ref('')
const filters = ref({ keyword: '', point: '', status: '' })

const selectedIds = ref<number[]>([])
const batchOpen = ref(false)
const batchItems = ref<BatchItem[]>([])
const department = ref('')
const submitting = ref(false)
const failedReasons = ref<{ id: number; reason: string }[]>([])
const detail = ref<Detail | null>(null)

const stats = computed(() => [
  { label: '待提交', value: countStatus('待提交') },
  { label: '已转办', value: countStatus('已转办') },
  { label: '已退回', value: countStatus('已退回') },
  { label: '无效投诉', value: countStatus('无效投诉') },
])

const submittableIds = computed(() => rows.value.filter(submittable).map((row) => Number(row.id)))
const allSubmittableChecked = computed(
  () => submittableIds.value.length > 0 && submittableIds.value.every((id) => selectedIds.value.includes(id)),
)
const needsDepartment = computed(() => batchItems.value.some((item) => item.conclusion === '有效'))
const canSubmit = computed(
  () =>
    batchItems.value.length > 0 &&
    !submitting.value &&
    batchItems.value.every((item) => item.measure.trim().length > 0) &&
    (!needsDepartment.value || department.value.trim().length > 0),
)
const detailSheets = computed(() => detail.value?.处置单 ?? [])

function countStatus(status: string) {
  return rows.value.filter((row) => row.status === status).length
}

function submittable(row: Row) {
  return SUBMITTABLE.includes(String(row.status ?? ''))
}

function rowActions(row: Row) {
  return row.status === '已转办' ? ['退回', '办结'] : []
}

function togglePointGroup(row: Row) {
  if (!submittable(row)) {
    return
  }
  const point = String(row.投诉点位 ?? '')
  const groupIds = rows.value
    .filter((item) => String(item.投诉点位 ?? '') === point && submittable(item))
    .map((item) => Number(item.id))
  const allChecked = groupIds.every((id) => selectedIds.value.includes(id))
  selectedIds.value = allChecked
    ? selectedIds.value.filter((id) => !groupIds.includes(id))
    : Array.from(new Set([...selectedIds.value, ...groupIds]))
}

function toggleAllSubmittable() {
  selectedIds.value = allSubmittableChecked.value ? [] : [...submittableIds.value]
}

function openBatch() {
  batchItems.value = rows.value
    .filter((row) => selectedIds.value.includes(Number(row.id)))
    .map((row) => ({
      id: Number(row.id),
      投诉编号: String(row.投诉编号 ?? ''),
      投诉点位: String(row.投诉点位 ?? ''),
      measure: String(row.降噪措施 ?? ''),
      conclusion: '有效',
    }))
  department.value = ''
  resultMessage.value = ''
  failedReasons.value = []
  batchOpen.value = true
}

function closeBatch() {
  batchOpen.value = false
  batchItems.value = []
  failedReasons.value = []
}

async function submitBatch() {
  if (!canSubmit.value) {
    return
  }
  submitting.value = true
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/batch-submit`, {
      method: 'POST',
      body: JSON.stringify({
        department: department.value.trim(),
        items: batchItems.value.map((item) => ({
          id: item.id,
          measure: item.measure.trim(),
          conclusion: item.conclusion,
        })),
      }),
    })
    if (!response.ok) {
      throw new Error('批量提交未生效，请稍后重试')
    }
    const payload = (await response.json()) as BatchResult
    resultMessage.value = payload.message
    failedReasons.value = payload.failed ?? []
    if (failedReasons.value.length) {
      // 未提交的留在面板里，修正后可再次提交；已转办的不受影响
      const failedIds = failedReasons.value.map((failure) => failure.id)
      batchItems.value = batchItems.value.filter((item) => failedIds.includes(item.id))
    } else {
      closeBatch()
    }
    selectedIds.value = []
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '批量提交失败'
  } finally {
    submitting.value = false
  }
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  resultMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${Number(row.id)}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action } }),
    })
    const payload = (await response.json()) as { ok: boolean; message: string }
    if (!response.ok || !payload.ok) {
      errorMessage.value = payload.message || '噪声投诉动作未生效，请稍后重试'
    } else {
      resultMessage.value = payload.message
    }
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '噪声投诉操作失败'
  }
}

async function openDetail(row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${Number(row.id)}`)
    if (!response.ok) {
      throw new Error('投诉明细读取失败')
    }
    detail.value = (await response.json()) as Detail
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '投诉明细读取失败'
  }
}

function resetFilters() {
  filters.value = { keyword: '', point: '', status: '' }
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams()
  if (filters.value.keyword) {
    query.set('keyword', filters.value.keyword)
  }
  if (filters.value.point) {
    query.set('point', filters.value.point)
  }
  if (filters.value.status) {
    query.set('status', filters.value.status)
  }
  query.set('size', '200')
  try {
    const response = await request(`${ENDPOINT}?${query.toString()}`)
    if (!response.ok) {
      throw new Error('投诉列表读取失败')
    }
    const payload = (await response.json()) as { items?: Row[]; total?: number }
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
    selectedIds.value = selectedIds.value.filter((id) =>
      rows.value.some((row) => Number(row.id) === id && submittable(row)),
    )
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '投诉列表读取失败'
  }
}

onMounted(reload)
</script>

<style scoped>
.batch-panel { background: #fff; border: 1px solid var(--border); border-radius: 8px; padding: 12px; margin-top: 12px; }
.batch-panel h3 { margin: 0 0 8px; font-size: 14px; }
.panel-hint { color: var(--muted); font-size: 12px; margin: 0 0 10px; }
.panel-actions { display: flex; gap: 10px; align-items: center; margin-top: 10px; }
.department-item { display: block; margin-bottom: 10px; }
.department-item span { display: block; font-size: 12px; color: var(--muted); }
.batch-panel input, .batch-panel select { padding: 4px 6px; border: 1px solid var(--border); border-radius: 4px; }
.department-item input { min-width: 260px; }
.measure-input { min-width: 280px; }
.batch-panel input.input-invalid { border-color: #b42318; }
.ok-text { color: #067647; }
.failed-list { font-size: 12px; margin-top: 6px; }
.failed-list ul { margin: 4px 0 0; padding-left: 18px; }
</style>
