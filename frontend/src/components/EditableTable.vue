<script setup>
// Cell-editable table with row add/remove (specs/11 DraftEditorView).
// columns: [{ key, label, width?, type: 'text' | 'textarea' | 'select', options? }]
const props = defineProps({
  columns: { type: Array, required: true },
  newRow: { type: Function, default: () => ({}) },
  label: { type: String, default: '표' },
})
const rows = defineModel('rows', { type: Array, required: true })

function add(index) {
  rows.value.splice(index + 1, 0, props.newRow())
}
</script>

<template>
  <div class="table-responsive">
    <table class="table table-sm table-bordered align-top mb-1 small editable">
      <thead class="table-light">
        <tr>
          <th v-for="c in columns" :key="c.key" :style="c.width ? { width: c.width } : {}">
            {{ c.label }}
          </th>
          <th style="width: 3.5rem"></th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="(row, index) in rows" :key="index">
          <td v-for="c in columns" :key="c.key" class="p-0">
            <select
              v-if="c.type === 'select'"
              v-model="row[c.key]"
              class="form-select form-select-sm border-0 rounded-0"
              :aria-label="`${label} ${index + 1}행 ${c.label}`"
            >
              <option v-for="o in c.options" :key="o.value" :value="o.value">{{ o.label }}</option>
            </select>
            <textarea
              v-else-if="c.type === 'textarea'"
              v-model="row[c.key]"
              class="form-control form-control-sm border-0 rounded-0"
              rows="2"
              :aria-label="`${label} ${index + 1}행 ${c.label}`"
            ></textarea>
            <input
              v-else
              v-model="row[c.key]"
              class="form-control form-control-sm border-0 rounded-0"
              :aria-label="`${label} ${index + 1}행 ${c.label}`"
            />
          </td>
          <td class="text-nowrap text-center">
            <button
              type="button"
              class="btn btn-sm btn-link p-0 me-1"
              :aria-label="`${index + 1}행 아래에 행 추가`"
              title="아래에 행 추가"
              @click="add(index)"
            >
              <i class="bi bi-plus-lg"></i>
            </button>
            <button
              type="button"
              class="btn btn-sm btn-link text-danger p-0"
              :aria-label="`${index + 1}행 삭제`"
              title="행 삭제"
              @click="rows.splice(index, 1)"
            >
              <i class="bi bi-trash"></i>
            </button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="text-muted text-center">행이 없습니다.</td>
        </tr>
      </tbody>
    </table>
    <button
      type="button"
      class="btn btn-sm btn-outline-secondary"
      @click="rows.push(props.newRow())"
    >
      <i class="bi bi-plus-lg me-1"></i>행 추가
    </button>
  </div>
</template>

<style scoped>
.editable textarea {
  resize: vertical;
  min-height: 2.4rem;
}
</style>
