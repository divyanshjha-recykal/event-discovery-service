/** CSV export. RFC 4180 quoting, so commas and newlines in reasoning survive. */

const cell = (value) => {
  if (value == null) return ''
  const text = Array.isArray(value) ? value.join(' | ') : String(value)
  return /[",\n\r]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text
}

const toCsv = (headers, rows) =>
  [headers.join(','), ...rows.map((r) => r.map(cell).join(','))].join('\r\n')

const verdictLabel = { met: 'met', not_met: 'not met', unclear: 'your call' }

/** One row per opportunity. */
export function opportunitiesCsv(saved) {
  const headers = [
    'title', 'organizing_body', 'base_title', 'cycle_year', 'category',
    'submission_deadline', 'deadline_verified', 'deadline_note', 'event_date',
    'conditions_met', 'conditions_not_met', 'conditions_for_you_to_judge',
    'judging_criteria', 'application_requirements',
    'extraction_completeness', 'completeness_gaps', 'extractor_uncertainty',
    'source_url', 'evidence_urls',
  ]
  const rows = saved.map((o) => {
    const e = o.eligibility
    const results = e?.criteria_results || []
    const pick = (status) => results.filter((r) => r.status === status).map((r) => r.criterion)
    const judge = [
      ...pick('unclear'),
      ...(e?.qualitative_notes || []).map((n) => n.criterion),
    ]
    return [
      o.title, o.organizing_body, o.base_title, o.cycle_year, o.category,
      o.submission_deadline, o.submission_deadline ? String(!!o.deadline_verified) : '',
      o.deadline_note, o.event_date,
      pick('met'), pick('not_met'), judge,
      o.judging_criteria, o.application_requirements,
      o.extraction_completeness
        ? `${Math.round((o.extraction_completeness.score || 0) * 100)}%` : '',
      o.extraction_completeness?.gaps,
      o.confidence_note,
      o.source_url, o.evidence_urls,
    ]
  })
  return toCsv(headers, rows)
}

/** One row per eligibility condition — the list a person actually works through. */
export function conditionsCsv(saved) {
  const headers = [
    'opportunity', 'organizing_body', 'submission_deadline',
    'condition', 'verdict', 'reasoning', 'source_url',
  ]
  const rows = []
  saved.forEach((o) => {
    const e = o.eligibility
    if (!e) {
      ;(o.eligibility_criteria || []).forEach((c) => {
        rows.push([o.title, o.organizing_body, o.submission_deadline, c,
                   'not evaluated', '', o.source_url])
      })
      return
    }
    ;(e.criteria_results || []).forEach((r) => {
      rows.push([o.title, o.organizing_body, o.submission_deadline, r.criterion,
                 verdictLabel[r.status] || r.status, r.reasoning, o.source_url])
    })
    ;(e.qualitative_notes || []).forEach((n) => {
      rows.push([o.title, o.organizing_body, o.submission_deadline, n.criterion,
                 'your call', n.note, o.source_url])
    })
  })
  return toCsv(headers, rows)
}

/** One row per journey step — the full run log, for an audit trail. */
export function journeyCsv(events) {
  const headers = ['seq', 't_seconds', 'node', 'tool', 'outcome', 'target', 'detail']
  const rows = events.map((e) => [
    e.seq, e.t, e.node, e.tool, e.outcome,
    e.url || e.query || e.title || '',
    e.reason || e.detail || e.rationale || '',
  ])
  return toCsv(headers, rows)
}

export function downloadCsv(filename, csv) {
  // A BOM so Excel opens UTF-8 correctly rather than mangling accents.
  const blob = new Blob(['﻿', csv], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

export async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text)
    return true
  } catch {
    // clipboard API needs a secure context; fall back to a hidden textarea.
    try {
      const area = document.createElement('textarea')
      area.value = text
      area.style.position = 'fixed'
      area.style.opacity = '0'
      document.body.appendChild(area)
      area.select()
      const ok = document.execCommand('copy')
      area.remove()
      return ok
    } catch {
      return false
    }
  }
}
