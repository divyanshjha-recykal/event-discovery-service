import { VERDICT, category } from '../api.js'

const List = ({ items }) => <ul className="plain">{items.map((x, i) => <li key={i}>{x}</li>)}</ul>

export default function Opportunity({ o }) {
  const e = o.eligibility
  const kind = category(o.category)
  const isResearch = o.category === 'research'
  const requirements = o.application_requirements || []
  const judging = o.judging_criteria || []
  const rows = [
    ...(e?.criteria_results || []).map((r) => ({ criterion: r.criterion, verdict: r.status, reason: r.reasoning })),
    ...(e?.qualitative_notes || []).map((n) => ({ criterion: n.criterion, verdict: 'qualitative', reason: n.note })),
  ].sort((a, b) => (VERDICT[a.verdict]?.order ?? 3) - (VERDICT[b.verdict]?.order ?? 3))
  const count = (v) => rows.filter((r) => r.verdict === v).length
  const notes = [o.deadline_note, o.confidence_note].filter(Boolean)
  const sources = [...new Set([o.source_url, ...(o.evidence_urls || [])])]

  return (
    <article className="opp">
      <h3>{o.title}</h3>
      <div className="row small muted" style={{ marginBottom: 6 }}>
        <span>{o.organizing_body}</span>
        <span className={`pill ${kind.cls}`}>{kind.label}</span>
        <span className={`pill ${o.submission_deadline ? 'met' : 'muted'}`}>
          {o.submission_deadline ? `deadline ${o.submission_deadline}` : 'no deadline found'}
        </span>
        {o.event_date && <span className="pill muted">event {o.event_date}</span>}
        {o.record_state === 'needs_deeper_read'
          ? <span className="tag warn">Needs more evidence</span>
          : <span className="tag ok">Ready</span>}
        {o.dry_run && <span className="pill unclear">fixture</span>}
      </div>

      <div className="section-label">About</div>
      {o.summary && <p className="tight">{o.summary}</p>}
      {o.why_pursued && <p className="small muted tight">Why it was pursued: {o.why_pursued}</p>}

      <div className="section-label">
        {isResearch ? 'Scope' : 'Eligibility'}
        {!!rows.length && (
          <span className="muted"> — {count('met')} met · {count('not_met')} not met · {count('unclear') + count('qualitative')} need review</span>
        )}
      </div>
      {rows.length ? (
        <table className="grid">
          <thead>
            <tr>
              <th style={{ width: '42%' }}>{isResearch ? 'Topic' : 'Condition'}</th>
              <th style={{ width: 104 }}>Verdict</th>
              <th>Reason</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={i}>
                <td>{r.criterion}</td>
                <td><span className={`tag ${VERDICT[r.verdict]?.cls || 'muted'}`}>{VERDICT[r.verdict]?.label || r.verdict}</span></td>
                <td className="why">{r.reason}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <p className="muted small tight">
          {(o.eligibility_criteria || []).length
            ? 'Conditions found but not yet judged.'
            : 'The pages read state no conditions.'}
        </p>
      )}

      {!!(requirements.length || judging.length) && (
        <>
          <div className="section-label">How to apply</div>
          {!!requirements.length && <List items={requirements} />}
          {!!judging.length && (
            <>
              <p className="small muted tight" style={{ marginTop: 8 }}>Judged on</p>
              <List items={judging} />
            </>
          )}
        </>
      )}

      {!!notes.length && (
        <>
          <div className="section-label">Notes</div>
          {notes.map((n, i) => <p className="small tight" key={i}>{n}</p>)}
        </>
      )}

      <details className="diag">
        <summary className="small muted">Sources ({sources.length})</summary>
        {sources.map((u) => <a key={u} className="u mono" href={u} target="_blank" rel="noreferrer">{u}</a>)}
      </details>
    </article>
  )
}
