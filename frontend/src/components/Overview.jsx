import { useState } from 'react'
import Opportunity from './Opportunity.jsx'

const Stat = ({ n, l, children }) => (
  <div className="stat">
    <div className="n">{n}</div>
    <div className="l">{l}</div>
    {children}
  </div>
)

export default function Overview({ data }) {
  const [filter, setFilter] = useState('all')
  const m = data?.metrics
  const opportunities = data?.opportunities || []

  const dated = opportunities.filter((o) => o.submission_deadline || o.event_date)
  const undated = opportunities.filter((o) => !o.submission_deadline && !o.event_date)
  const shown = filter === 'dated' ? dated : filter === 'undated' ? undated : opportunities

  const total = m ? m.criteria.met + m.criteria.not_met + m.criteria.unclear : 0

  return (
    <>
      <div className="run-head">
        <div className="run-title">
          <h2>Everything stored</h2>
          <div className="small muted">
            Every opportunity across all runs. Pick a run on the left to see what that
            run alone found and how it got there.
          </div>
        </div>
      </div>

      {m && (
        <div className="stats">
          <Stat n={m.opportunities} l="opportunities stored" />
          <Stat n={m.programs} l="recurring programmes tracked" />
          <Stat n={`${m.extraction_success}/${m.extraction_success + m.extraction_failed}`}
                l="latest-run extractions succeeded" />
          <Stat n={total} l={`conditions judged · ${m.verdicts.unevaluated} records unevaluated`}>
            {total > 0 && (
              <>
                <div className="bar">
                  <i className="met" style={{ width: `${(m.criteria.met / total) * 100}%` }} />
                  <i className="not_met" style={{ width: `${(m.criteria.not_met / total) * 100}%` }} />
                  <i className="unclear" style={{ width: `${(m.criteria.unclear / total) * 100}%` }} />
                </div>
                <div className="l">
                  {m.criteria.met} met · {m.criteria.not_met} not met ·{' '}
                  {m.criteria.unclear} need review
                </div>
              </>
            )}
          </Stat>
        </div>
      )}

      <div className="tabs">
        {[
          ['all', `All (${opportunities.length})`],
          ['dated', `Dated and open (${dated.length})`],
          ['undated', `No date confirmed (${undated.length})`],
        ].map(([key, label]) => (
          <button key={key} type="button"
                  className={`tab${filter === key ? ' on' : ''}`}
                  onClick={() => setFilter(key)}>
            {label}
          </button>
        ))}
      </div>

      <div className="card">
        {filter === 'undated' && (
          <p className="small muted" style={{ marginTop: 0 }}>
            Real programmes, but no deadline was found in the evidence — check the
            source page before relying on these.
          </p>
        )}
        {shown.map((o) => <Opportunity key={o.source_url} o={o} />)}
        {!shown.length && <p className="muted tight">Nothing stored yet. Start a run on the left.</p>}
      </div>

      {!!(data?.programs || []).length && (
        <div className="card">
          <h2 className="card-title">Recurring programme registry</h2>
          <p className="small muted" style={{ marginTop: -4 }}>
            Built from saved editions. A typical window appears once two dated
            editions are known, and predicts when the next cycle opens.
          </p>
          <table className="grid">
            <thead>
              <tr><th>Programme</th><th style={{ width: 180 }}>Editions</th><th style={{ width: 190 }}>Typical window</th></tr>
            </thead>
            <tbody>
              {data.programs.map((p, i) => (
                <tr key={i}>
                  <td>{p.base_title}<div className="small muted">{p.organizing_body}</div></td>
                  <td className="small mono">
                    {(p.editions || []).map((e) => e.year).join(', ') || '—'}
                  </td>
                  <td className="small">
                    {p.typical_window
                      ? `months ${p.typical_window.month_start}–${p.typical_window.month_end}`
                      : <span className="muted">not enough history</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  )
}
