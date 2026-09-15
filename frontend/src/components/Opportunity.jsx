/* "unclear" and "qualitative" both mean the same thing to a reader: a human
   decides. One label, one bucket, nothing hidden. */
const VERDICT = {
  met: { label: 'Met', cls: 'met', order: 0 },
  not_met: { label: 'Not met', cls: 'not_met', order: 1 },
  unclear: { label: 'Your call', cls: 'unclear', order: 2 },
  qualitative: { label: 'Your call', cls: 'unclear', order: 2 },
}

export default function Opportunity({ o }) {
  const e = o.eligibility
  const requirements = o.application_requirements || []
  const judging = o.judging_criteria || []
  const rows = [
    ...(e?.criteria_results || []).map((r) => ({
      criterion: r.criterion, verdict: r.status, reason: r.reasoning,
    })),
    ...(e?.qualitative_notes || []).map((n) => ({
      criterion: n.criterion, verdict: 'qualitative', reason: n.note,
    })),
  ].sort((a, b) => (VERDICT[a.verdict]?.order ?? 3) - (VERDICT[b.verdict]?.order ?? 3))
  const judgeCount = rows.filter(
    (r) => r.verdict === 'unclear' || r.verdict === 'qualitative',
  ).length

  return (
    <article className="opp">
      <h3>{o.title}</h3>
      <div className="row small muted" style={{ marginBottom: 6 }}>
        <span>{o.organizing_body}</span>
        <span className="pill muted">{o.category}</span>
        <span className="pill muted">cycle {o.cycle_year}</span>
        <span className={`pill ${o.submission_deadline ? 'met' : 'muted'}`}>
          {o.submission_deadline || 'no deadline found'}
          {o.submission_deadline && (o.deadline_verified ? ' verified' : ' unverified')}
        </span>
        {o.event_date && <span className="pill muted">event {o.event_date}</span>}
        {o.dry_run && <span className="pill unclear">fixture</span>}
      </div>
      <a className="src mono" href={o.source_url} target="_blank" rel="noreferrer">
        {o.source_url}
      </a>

      {o.deadline_note && (
        <div className="why-block">
          <span className="why-label">Deadline note</span>
          <div>{o.deadline_note}</div>
        </div>
      )}

      {o.confidence_note && (
        <div className="why-block">
          <span className="why-label">Extractor&rsquo;s own uncertainty</span>
          <div>{o.confidence_note}</div>
        </div>
      )}

      {!!requirements.length && (
        <>
          <div className="section-label">What you have to submit</div>
          <ul className="plain">{requirements.map((r, i) => <li key={i}>{r}</li>)}</ul>
        </>
      )}

      {!!judging.length && (
        <>
          <div className="section-label">What you are judged on</div>
          <ul className="plain">{judging.map((r, i) => <li key={i}>{r}</li>)}</ul>
        </>
      )}

      <div className="section-label">
        Eligibility conditions
        {rows.length > 0 && <span className="muted"> — {rows.length} judged</span>}
      </div>

      {!e && !!(o.eligibility_criteria || []).length && (
        <>
          <p className="muted small tight">Extracted but not yet evaluated.</p>
          <ul className="plain">
            {o.eligibility_criteria.map((c, i) => <li key={i}>{c}</li>)}
          </ul>
        </>
      )}
      {!e && !(o.eligibility_criteria || []).length && (
        <p className="muted small tight">
          No eligibility conditions were extracted from this page, so it cannot be evaluated.
        </p>
      )}

      {e && (
        <>
          <table className="crit">
            <thead>
              <tr>
                <th style={{ width: '42%' }}>Condition</th>
                <th style={{ width: 104 }}>Verdict</th>
                <th>Reasoning</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r, i) => (
                <tr key={i}>
                  <td>{r.criterion}</td>
                  <td>
                    <span className={`pill ${VERDICT[r.verdict]?.cls || 'muted'}`}>
                      {VERDICT[r.verdict]?.label || r.verdict}
                    </span>
                  </td>
                  <td className="why">{r.reason}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="small muted" style={{ marginTop: 8 }}>
            {e.criteria_results.filter((r) => r.status === 'met').length} met ·{' '}
            {e.criteria_results.filter((r) => r.status === 'not_met').length} not met ·{' '}
            {judgeCount} for you to judge
          </p>
          {(e.classification_flags || []).map((f, i) => <div className="flag" key={i}>{f}</div>)}
        </>
      )}

      <details className="diag">
        <summary className="small muted">Extraction and evaluation detail</summary>

        {o.extraction_completeness && (
          <>
            <div className="section-label">
              Extraction completeness — {Math.round((o.extraction_completeness.score || 0) * 100)}%
            </div>
            <div className="row">
              {[
                ['identity', o.extraction_completeness.identity],
                ['open state', o.extraction_completeness.open_state],
                ['deadline', o.extraction_completeness.deadline],
                ['eligibility', o.extraction_completeness.eligibility],
                ['source coverage', o.extraction_completeness.source_coverage],
              ].map(([label, ok]) => (
                <span key={label} className={`pill ${ok ? 'met' : 'not_met'}`}>{label}</span>
              ))}
            </div>
          </>
        )}

        {e && (
          <>
            <div className="section-label">Evaluation</div>
            <div className="row">
              <span className={`pill ${e.confidence === 'high' ? 'met' : 'unclear'}`}>
                confidence {e.confidence}
              </span>
              <span className="pill muted">
                score {e.score == null ? 'not computable' : e.score.toFixed(2)}
              </span>
            </div>
            <p className="small muted reason">
              Confidence is high only when at least one condition was fact-checkable and
              none came back unclear. Score is met ÷ (met + not met) and misleads on
              programmes with alternative tracks, so read the per-condition verdicts above
              rather than the number.
            </p>
          </>
        )}

        <div className="section-label">Evidence pages read ({(o.evidence_urls || []).length})</div>
        {(o.evidence_urls || []).map((u, i) => (
          <a key={i} className="u mono" href={u} target="_blank" rel="noreferrer">{u}</a>
        ))}
        {!(o.evidence_urls || []).length && (
          <p className="small muted tight">Only the source page above.</p>
        )}

        <div className="section-label">Identity</div>
        <p className="small muted tight">
          <code>{o.organizing_body}</code> + <code>{o.base_title}</code> + {o.cycle_year}
          {o.discovery_run_id && (
            <> · last written by run <code>{o.discovery_run_id.slice(0, 6)}</code></>
          )}
        </p>
      </details>
    </article>
  )
}
