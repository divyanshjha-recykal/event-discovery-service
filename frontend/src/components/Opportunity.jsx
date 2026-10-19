import { FIT, VERDICT, category } from '../api.js'

const List = ({ items }) => <ul className="plain">{items.map((x, i) => <li key={i}>{x}</li>)}</ul>

/** Which of our work fits a research venue's call; shared with the journey. */
export function FitTable({ fit }) {
  const works = [...(fit?.works || [])].sort((a, b) => (FIT[a.fit]?.order ?? 3) - (FIT[b.fit]?.order ?? 3))
  const matched = works.filter((w) => w.fit !== 'no')
  return (
    <>
      {matched.length ? (
        <table className="grid">
          <thead>
            <tr>
              <th style={{ width: '28%' }}>Our work</th>
              <th style={{ width: 96 }}>Fit</th>
              <th style={{ width: '28%' }}>Call topic</th>
              <th>Reason</th>
            </tr>
          </thead>
          <tbody>
            {matched.map((w, i) => (
              <tr key={i}>
                <td>{w.work}</td>
                <td><span className={`tag ${FIT[w.fit]?.cls || 'muted'}`}>{FIT[w.fit]?.label || w.fit}</span></td>
                <td>{w.topic}</td>
                <td className="why">{w.reason}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : <p className="muted small tight">None of our work matches this call's topics.</p>}
      {works.length > matched.length && (
        <p className="small muted tight">
          Doesn't fit: {works.filter((w) => w.fit === 'no').map((w) => w.work).join(', ')}
        </p>
      )}
      {fit?.venue_note && <p className="small tight">Venue: {fit.venue_note}</p>}
    </>
  )
}

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

      {isResearch && (
        <>
          <div className="section-label">
            Fits our work
            {o.fit && <span className="muted"> — {(o.fit.works || []).filter((w) => w.fit !== 'no').length} of {(o.fit.works || []).length} lines of work</span>}
          </div>
          {o.fit ? <FitTable fit={o.fit} /> : <p className="muted small tight">Fit not judged yet.</p>}
          {!!(o.eligibility_criteria || []).length && (
            <>
              <div className="section-label">Topics of interest</div>
              <List items={o.eligibility_criteria} />
            </>
          )}
        </>
      )}

      {!isResearch && <>
      <div className="section-label">
        Eligibility
        {!!rows.length && (
          <span className="muted"> — {count('met')} met · {count('not_met')} not met · {count('unclear') + count('qualitative')} need review</span>
        )}
      </div>
      {rows.length ? (
        <table className="grid">
          <thead>
            <tr>
              <th style={{ width: '42%' }}>Condition</th>
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
      </>}

      {!!(requirements.length || judging.length) && (
        <>
          <div className="section-label">{isResearch ? 'How to submit' : 'How to apply'}</div>
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
