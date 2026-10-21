import { useEffect, useMemo, useState } from 'react'
import {
  conditionsCsv, copyText, downloadCsv, journeyCsv, opportunitiesCsv,
} from '../export.js'
import { api, shortId } from '../api.js'

const OPPORTUNITY_SHEETS = [
  ['opportunities', 'Opportunities', 'One row per opportunity this run stored.'],
  ['conditions', 'Eligibility conditions', 'One row per condition with its verdict and reasoning — the list to work through.'],
  ['email', 'Email preview', 'Exactly what the email will show; the opportunities CSV is attached.'],
  ['journey', 'Run log', 'One row per step the agent took, for an audit trail.'],
]
const WATCH_SHEETS = [
  ['signals', 'Signals', 'One row per signal, by section, with why it matters and its other sources.'],
  ['email', 'Email preview', 'Exactly what the email will show; the signals CSV is attached.'],
  ['journey', 'Run log', 'One row per step the agent took, for an audit trail.'],
]

export default function ExportPanel({ runId, saved, events, watch, onClose }) {
  const sheets = watch ? WATCH_SHEETS : OPPORTUNITY_SHEETS
  const [sheet, setSheet] = useState(sheets[0][0])
  const [copied, setCopied] = useState(false)
  // The server builds the email and the signals CSV, so the preview is what is sent.
  const [preview, setPreview] = useState(null)
  const [previewError, setPreviewError] = useState('')
  const [mail, setMail] = useState({ step: 'idle', note: '' })

  useEffect(() => {
    api(`/api/runs/${runId}/email`).then(setPreview).catch((e) => setPreviewError(e.message))
  }, [runId])

  const sendMail = async () => {
    setMail({ step: 'sending', note: '' })
    try {
      const r = await api(`/api/runs/${runId}/email`, { method: 'POST' })
      setMail({ step: 'sent', note: `Sent ${r.count} item(s) to ${r.sent_to.join(', ')}.` })
    } catch (e) {
      setMail({ step: 'failed', note: e.message })
    }
  }

  const csv = useMemo(() => {
    if (sheet === 'signals') return preview?.csv || ''
    if (sheet === 'conditions') return conditionsCsv(saved)
    if (sheet === 'journey') return journeyCsv(events)
    if (sheet === 'opportunities') return opportunitiesCsv(saved)
    return ''
  }, [sheet, saved, events, preview])

  const rows = csv ? csv.trim().split(/\r?\n/).length - 1 : 0
  const filename = sheet === 'signals' && preview ? preview.filename
    : `opportunity-radar-${sheet}-${shortId(runId)}.csv`
  const mailTo = preview?.to || []

  const copy = async () => {
    setCopied(await copyText(csv))
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div className="modal-back" onClick={onClose}>
      <div className="modal wide" onClick={(ev) => ev.stopPropagation()}>
        <h3>Export this run</h3>

        <div className="tabs" style={{ marginTop: 12 }}>
          {sheets.map(([key, label]) => (
            <button key={key} type="button"
                    className={`tab${sheet === key ? ' on' : ''}`}
                    onClick={() => setSheet(key)}>
              {label}
            </button>
          ))}
        </div>

        <p className="small muted tight">
          {sheets.find(([k]) => k === sheet)[2]}{sheet !== 'email' && ` — ${rows} row(s).`}
        </p>

        {sheet === 'email' ? (
          previewError ? <p className="err small tight">{previewError}</p>
            : !preview ? <p className="muted small tight">Building the email…</p>
              : (
                <>
                  <p className="small tight"><span className="muted">Subject:</span> {preview.subject}
                    {' · '}<span className="muted">Attached:</span> {preview.filename}</p>
                  <iframe title="Email preview" srcDoc={preview.html} sandbox=""
                          style={{ width: '100%', height: 420, border: '1px solid var(--border)', background: '#fff' }} />
                </>
              )
        ) : (
          <>
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
          </>
        )}

        <div className="mail-block" style={{ marginTop: 16, paddingTop: 12, borderTop: '1px solid var(--border)' }}>
          <h4 style={{ margin: '0 0 6px' }}>Email this run</h4>
          {!preview && !previewError && <p className="small muted tight">Checking mail settings…</p>}
          {previewError && <p className="small muted tight">Nothing to email: {previewError}</p>}
          {preview && !mailTo.length && (
            <p className="small muted tight">Mail is not configured: set the SMTP settings and SMTP_TO in .env, then restart the API.</p>
          )}
          {preview && !!mailTo.length && (
            <>
              <p className="small muted tight">
                A readable summary of {preview.count} {watch ? 'signal(s)' : 'opportunit(ies)'} in the email body, with {preview.filename} attached.
              </p>
              <div className="row" style={{ marginTop: 8 }}>
                {mail.step === 'confirm' ? (
                  <>
                    <span className="small">Send to <strong>{mailTo.join(', ')}</strong>?</span>
                    <button type="button" onClick={sendMail}>Send</button>
                    <button className="ghost" type="button" onClick={() => setMail({ step: 'idle', note: '' })}>Cancel</button>
                  </>
                ) : (
                  <button type="button" disabled={mail.step === 'sending'}
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
        {sheet !== 'email' && (
          <p className="hint" style={{ marginTop: 8 }}>
            Saved as <code>{filename}</code>. Lists inside a cell are separated by
            <code> | </code>.
          </p>
        )}
      </div>
    </div>
  )
}
