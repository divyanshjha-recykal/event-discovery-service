import { useMemo, useState } from 'react'
import {
  conditionsCsv, copyText, downloadCsv, journeyCsv, opportunitiesCsv,
} from '../export.js'
import { shortId } from '../api.js'

const SHEETS = [
  ['opportunities', 'Opportunities', 'One row per opportunity this run stored.'],
  ['conditions', 'Eligibility conditions', 'One row per condition with its verdict and reasoning — the list to work through.'],
  ['journey', 'Run log', 'One row per step the agent took, for an audit trail.'],
]

export default function ExportPanel({ runId, saved, events, onClose }) {
  const [sheet, setSheet] = useState('opportunities')
  const [copied, setCopied] = useState(false)

  const csv = useMemo(() => {
    if (sheet === 'conditions') return conditionsCsv(saved)
    if (sheet === 'journey') return journeyCsv(events)
    return opportunitiesCsv(saved)
  }, [sheet, saved, events])

  const rows = csv ? csv.split('\r\n').length - 1 : 0
  const filename = `opportunity-radar-${sheet}-${shortId(runId)}.csv`

  const copy = async () => {
    setCopied(await copyText(csv))
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div className="modal-back" onClick={onClose}>
      <div className="modal wide" onClick={(ev) => ev.stopPropagation()}>
        <h3>Export this run</h3>

        <div className="tabs" style={{ marginTop: 12 }}>
          {SHEETS.map(([key, label]) => (
            <button key={key} type="button"
                    className={`tab${sheet === key ? ' on' : ''}`}
                    onClick={() => setSheet(key)}>
              {label}
            </button>
          ))}
        </div>

        <p className="small muted tight">
          {SHEETS.find(([k]) => k === sheet)[2]} — {rows} row(s).
        </p>

        <textarea className="csv-preview" readOnly value={csv}
                  onFocus={(ev) => ev.target.select()} spellCheck="false" />

        <div className="row" style={{ marginTop: 14 }}>
          <button type="button" onClick={() => downloadCsv(filename, csv)} disabled={!rows}>
            Download CSV
          </button>
          <button className="ghost" type="button" onClick={copy} disabled={!rows}>
            {copied ? 'Copied' : 'Copy to clipboard'}
          </button>
          <span className="spacer" />
          <button className="ghost" type="button" onClick={onClose}>Close</button>
        </div>
        <p className="hint" style={{ marginTop: 8 }}>
          Saved as <code>{filename}</code>. Lists inside a cell are separated by
          <code> | </code>.
        </p>
      </div>
    </div>
  )
}
