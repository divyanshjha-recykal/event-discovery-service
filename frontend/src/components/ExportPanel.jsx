import { useEffect, useMemo, useState } from 'react'
import {
  conditionsCsv, copyText, downloadCsv, journeyCsv, opportunitiesCsv,
} from '../export.js'
import { api, shortId } from '../api.js'

const SHEETS = [
  ['opportunities', 'Opportunities', 'One row per opportunity this run stored.'],
  ['conditions', 'Eligibility conditions', 'One row per condition with its verdict and reasoning — the list to work through.'],
  ['journey', 'Run log', 'One row per step the agent took, for an audit trail.'],
]

export default function ExportPanel({ runId, saved, events, onClose }) {
  const [sheet, setSheet] = useState('opportunities')
  const [copied, setCopied] = useState(false)
  // Recipients come from SMTP_TO on the server; the page cannot choose them.
  const [mailTo, setMailTo] = useState(null)
  const [mail, setMail] = useState({ step: 'idle', note: '' })

  useEffect(() => {
    api('/api/mail').then((m) => setMailTo(m.to || [])).catch(() => setMailTo([]))
  }, [])

  const sendMail = async () => {
    setMail({ step: 'sending', note: '' })
    try {
      const r = await api(`/api/runs/${runId}/email`, { method: 'POST' })
      setMail({ step: 'sent', note: `Sent ${r.count} opportunit${r.count === 1 ? 'y' : 'ies'} to ${r.sent_to.join(', ')}.` })
    } catch (e) {
      setMail({ step: 'failed', note: e.message })
    }
  }

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

        <div className="mail-block" style={{ marginTop: 16, paddingTop: 12, borderTop: '1px solid var(--border)' }}>
          <h4 style={{ margin: '0 0 6px' }}>Email the opportunities CSV</h4>
          {mailTo === null && <p className="small muted tight">Checking mail settings…</p>}
          {mailTo && !mailTo.length && (
            <p className="small muted tight">Mail is not configured: set the SMTP settings and SMTP_TO in .env, then restart the API.</p>
          )}
          {!!mailTo?.length && (
            <>
              <p className="small muted tight">
                Every opportunity this run saved ({saved.length}), including those that need more evidence, as a CSV with a summary.
              </p>
              <div className="row" style={{ marginTop: 8 }}>
                {mail.step === 'confirm' ? (
                  <>
                    <span className="small">Send to <strong>{mailTo.join(', ')}</strong>?</span>
                    <button type="button" onClick={sendMail}>Send</button>
                    <button className="ghost" type="button" onClick={() => setMail({ step: 'idle', note: '' })}>Cancel</button>
                  </>
                ) : (
                  <button type="button" disabled={!saved.length || mail.step === 'sending'}
                          onClick={() => setMail({ step: 'confirm', note: '' })}>
                    {mail.step === 'sending' ? 'Sending…' : `Email to ${mailTo.join(', ')}`}
                  </button>
                )}
              </div>
              {mail.step === 'sent' && <p className="small tight" style={{ color: 'var(--ok)' }}>{mail.note}</p>}
              {mail.step === 'failed' && <p className="err small tight">{mail.note}</p>}
            </>
          )}
        </div>
        <p className="hint" style={{ marginTop: 8 }}>
          Saved as <code>{filename}</code>. Lists inside a cell are separated by
          <code> | </code>.
        </p>
      </div>
    </div>
  )
}
