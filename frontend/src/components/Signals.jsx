import { useEffect, useState } from 'react'
import { api } from '../api.js'

const IMPORTANCE = {
  high: { label: 'High', cls: 'bad' },
  medium: { label: 'Medium', cls: 'warn' },
  low: { label: 'Low', cls: 'muted' },
}

/** A run's signals grouped by section, refetched while the run is live. */
function useSections(runId, count, live) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  useEffect(() => {
    api(`/api/runs/${runId}/signals`).then((d) => { setData(d.sections); setError(null) }).catch((e) => setError(e.message))
  }, [runId, count, live])
  return [data, error]
}

function Signal({ s }) {
  const imp = IMPORTANCE[s.importance] || { label: s.importance, cls: 'muted' }
  const also = s.also_reported_by || []
  return (
    <article className="opp">
      <div className="row small muted" style={{ marginBottom: 6 }}>
        <span className={`tag ${imp.cls}`}>{imp.label}</span>
        <span>{s.competitor}</span>
        <span className="pill muted">{s.kind}</span>
        <span className="pill muted">{s.date || 'undated'}</span>
        <span className="pill muted">found via {s.lane} search</span>
      </div>
      <h3>{s.headline}</h3>
      <p className="tight">{s.what_happened}</p>
      <p className="small tight"><span className="muted">Why it matters:</span> {s.why_it_matters}</p>
      <a className="u mono small" href={s.url} target="_blank" rel="noreferrer">{s.url}</a>
      {!!also.length && (
        <details className="diag">
          <summary className="small muted">Also reported by ({also.length})</summary>
          {also.map((u) => <a key={u} className="u mono small" href={u} target="_blank" rel="noreferrer">{u}</a>)}
        </details>
      )}
    </article>
  )
}

/** The run's digest: each section's findings as title, summary and link. */
export function Digest({ runId, count }) {
  const [sections, error] = useSections(runId, count, false)
  if (error) return <p className="err small tight">{error}</p>
  if (!sections) return <p className="muted tight">Loading digest…</p>
  if (!sections.length) return <p className="muted tight">Nothing new since the last watch run.</p>
  return sections.map((sec) => (
    <div key={sec.title}>
      <div className="section-label">{sec.title}</div>
      <ul className="plain">
        {sec.signals.map((s) => (
          <li key={s.signal_id}>
            <strong>{s.headline}</strong>{' '}
            <a className="u small" href={s.url} target="_blank" rel="noreferrer">link</a>
            <p className="small tight">{s.what_happened}</p>
          </li>
        ))}
      </ul>
    </div>
  ))
}

/** Every signal of a competitor-watch run in full, by section. */
export default function Signals({ runId, count, live }) {
  const [sections, error] = useSections(runId, count, live)
  if (error) return <p className="err small tight">{error}</p>
  if (!sections) return <p className="muted tight">Loading signals…</p>
  if (!sections.length) return <p className="muted tight">{live ? 'Nothing judged yet.' : 'No new signals in this run.'}</p>
  return sections.map((sec) => (
    <div key={sec.title}>
      <div className="section-label">{sec.title}</div>
      {sec.signals.map((s) => <Signal key={s.signal_id} s={s} />)}
    </div>
  ))
}
