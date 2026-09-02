import { useCallback, useEffect, useRef, useState } from 'react'

const MODELS = [
  'google/gemma-4-31b-it',
  'qwen/qwen3-32b',
  'z-ai/glm-4.7-flash',
  'ibm-granite/granite-4.1-8b',
]

const api = async (path, options) => {
  const res = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!res.ok) throw new Error(`${path} → ${res.status}`)
  return res.json()
}

/* ---------------------------------------------------------------- metrics */

function Metrics({ m }) {
  if (!m) return null
  const { verdicts, criteria } = m
  const total = criteria.met + criteria.not_met + criteria.unclear
  return (
    <div className="grid cols-4">
      <Stat n={m.opportunities} l="opportunities stored" />
      <Stat n={m.programs} l="programs tracked" />
      <Stat
        n={`${m.extraction_success}/${m.extraction_success + m.extraction_failed}`}
        l="extractions succeeded"
      />
      <div className="card stat">
        <div className="n">
          {verdicts.high}<span className="muted" style={{ fontSize: 14 }}> high</span>
          {' '}
          {verdicts.low}<span className="muted" style={{ fontSize: 14 }}> low</span>
        </div>
        <div className="l">confidence · {verdicts.unevaluated} unevaluated</div>
        {total > 0 && (
          <div className="bar" style={{ marginTop: 10 }}>
            <i className="met" style={{ width: `${(criteria.met / total) * 100}%` }} />
            <i className="not_met" style={{ width: `${(criteria.not_met / total) * 100}%` }} />
            <i className="unclear" style={{ width: `${(criteria.unclear / total) * 100}%` }} />
          </div>
        )}
        {total > 0 && (
          <div className="l" style={{ marginTop: 6 }}>
            {criteria.met} met · {criteria.not_met} not met · {criteria.unclear} unclear
          </div>
        )}
      </div>
    </div>
  )
}

const Stat = ({ n, l }) => (
  <div className="card stat"><div className="n">{n}</div><div className="l">{l}</div></div>
)

/* ------------------------------------------------------------ run journey */

function Step({ e }) {
  const cls = `step ${e.tool}${e.outcome === 'failed' ? ' failed' : ''}`
  return (
    <div className={cls}>
      <div className="t">t+{e.t}s</div>
      <div className="tool">{e.tool}</div>
      <div>
        {e.tool === 'search' && (
          <>
            <div className="mono">{e.query}</div>
            <details style={{ marginTop: 8 }}>
              <summary className="muted small">
                {(e.results || []).length} result(s) returned
              </summary>
              {(e.results || []).map((r) => (
                <a className="result" key={r.url} href={r.url} target="_blank" rel="noreferrer">
                  <div>{r.title}</div>
                  <div className="u">{r.url}</div>
                </a>
              ))}
            </details>
          </>
        )}

        {e.tool === 'scrape' && (
          <div className="row">
            <a href={e.url} target="_blank" rel="noreferrer" className="mono small">{e.url}</a>
            {e.outcome === 'ok'
              ? <span className="pill muted">{e.chars} chars</span>
              : <span className="pill not_met">scrape failed</span>}
            {e.bare_domain && <span className="pill unclear">homepage</span>}
            {e.detail && <div className="small err">{e.detail}</div>}
          </div>
        )}

        {e.tool === 'extract' && (
          e.outcome === 'ok' ? (
            <>
              <div><strong>{e.record?.title}</strong></div>
              <div className="row small muted" style={{ marginTop: 4 }}>
                <span>{e.record?.organizing_body}</span>
                <span className="pill muted">{e.record?.category}</span>
                <span className="pill muted">cycle {e.record?.cycle_year}</span>
                <span className={`pill ${e.record?.deadline_verified ? 'met' : 'unclear'}`}>
                  deadline {e.record?.submission_deadline || 'none'}
                  {e.record?.deadline_verified ? ' verified' : ' unverified'}
                </span>
              </div>
              {!!(e.record?.criteria || []).length && (
                <details style={{ marginTop: 8 }}>
                  <summary className="muted small">
                    {e.record.criteria.length} eligibility criteria extracted
                  </summary>
                  <ul className="crit">
                    {e.record.criteria.map((c, i) => <li key={i}>{c}</li>)}
                  </ul>
                </details>
              )}
            </>
          ) : (
            <div>
              <a href={e.url} target="_blank" rel="noreferrer" className="mono small">{e.url}</a>
              <div className="row" style={{ marginTop: 4 }}>
                <span className="pill not_met">{e.reason}</span>
              </div>
              <div className="small err">{e.detail}</div>
            </div>
          )
        )}

        {e.tool === 'save_opportunity' && (
          <div>
            <span className="pill met">{e.action}</span>{' '}
            <strong>{e.title}</strong>
            {(e.warnings || []).map((w, i) => <div className="flag" key={i}>⚠ {w}</div>)}
          </div>
        )}

        {e.tool === 'read_memory' && <span className="muted small">loaded profile + registry</span>}
      </div>
    </div>
  )
}

function RunPanel({ run }) {
  if (!run) return <p className="muted tight">No run selected.</p>
  const b = run.budget || {}
  const c = run.counts || {}
  return (
    <>
      <div className="row" style={{ marginBottom: 12 }}>
        <span className={`pill ${run.status === 'completed' ? 'met' : run.status === 'failed' ? 'not_met' : 'unclear'}`}>
          {run.status}
        </span>
        <span className="mono small">{run.model}</span>
        <span className="muted small">
          {b.spent ?? 0}/{b.tool_calls} calls · {c.searched ?? 0} searches ·
          {' '}{c.scraped ?? 0} scraped · {c.extracted ?? 0} extracted ·
          {' '}{c.saved ?? 0} saved · {c.failed ?? 0} failed
        </span>
        <div className="spacer" />
        {run.trace_url && (
          <a href={run.trace_url} target="_blank" rel="noreferrer" className="small">
            Langfuse trace ↗
          </a>
        )}
      </div>

      {!!(run.thinking || []).length && (
        <details style={{ marginBottom: 12 }}>
          <summary>Agent reasoning ({run.thinking.length} step{run.thinking.length > 1 ? 's' : ''})</summary>
          {run.thinking.map((t, i) => (
            <p key={i} className="small" style={{ whiteSpace: 'pre-wrap' }}>{t}</p>
          ))}
        </details>
      )}

      <div>{(run.journey || []).map((e) => <Step key={e.seq} e={e} />)}</div>

      {run.summary && (
        <details style={{ marginTop: 12 }}>
          <summary>Agent summary</summary>
          <p className="small" style={{ whiteSpace: 'pre-wrap' }}>{run.summary}</p>
        </details>
      )}
    </>
  )
}

/* ----------------------------------------------------------- opportunity */

function Opportunity({ o }) {
  const e = o.eligibility
  const deadlineOk = o.submission_deadline
    && new Date(o.submission_deadline) >= new Date(new Date().toDateString())

  return (
    <details open>
      <summary>
        <strong>{o.title}</strong>{' '}
        {o.dry_run && <span className="pill unclear">fixture</span>}{' '}
        {e
          ? <span className={`pill ${e.confidence}`}>confidence: {e.confidence}</span>
          : <span className="pill muted">not evaluated</span>}{' '}
        <span className={`pill ${deadlineOk ? 'met' : 'muted'}`}>
          {o.submission_deadline || 'no deadline'}
          {o.submission_deadline && (o.deadline_verified ? ' ✓ verified' : ' unverified')}
        </span>
      </summary>

      <div className="row small muted" style={{ marginBottom: 10 }}>
        <span>{o.organizing_body}</span>
        <span className="pill muted">{o.category}</span>
        <span className="pill muted">cycle {o.cycle_year}</span>
        <a href={o.source_url} target="_blank" rel="noreferrer" className="mono">{o.source_url}</a>
      </div>

      {!e && !!(o.eligibility_criteria || []).length && (
        <table className="crit-table">
          <thead><tr><th>Condition</th></tr></thead>
          <tbody>
            {o.eligibility_criteria.map((c, i) => <tr key={i}><td>{c}</td></tr>)}
          </tbody>
        </table>
      )}

      {e && (
        <>
          <table className="crit-table">
            <thead>
              <tr><th style={{ width: '46%' }}>Condition</th><th style={{ width: 96 }}>Verdict</th><th>Reason</th></tr>
            </thead>
            <tbody>
              {e.criteria_results.map((r, i) => (
                <tr key={i}>
                  <td>{r.criterion}</td>
                  <td><span className={`pill ${r.status}`}>{r.status.replace('_', ' ')}</span></td>
                  <td className="why">{r.reasoning}</td>
                </tr>
              ))}
              {e.qualitative_notes.map((n, i) => (
                <tr key={`q${i}`}>
                  <td>{n.criterion}</td>
                  <td><span className="pill note">qualitative</span></td>
                  <td className="why">{n.note}</td>
                </tr>
              ))}
            </tbody>
          </table>

          <p className="small muted" style={{ marginTop: 10 }}>
            {/* Score never stands alone: a flat criteria list scores alternative
                award categories as joint requirements, so the number can
                understate a genuine match. The parts are always shown with it. */}
            <strong>score {e.score === null ? 'n/a' : e.score.toFixed(2)}</strong>
            {' '}· confidence <strong>{e.confidence}</strong> ·{' '}
            {e.criteria_results.filter((r) => r.status === 'met').length} met,{' '}
            {e.criteria_results.filter((r) => r.status === 'not_met').length} not met,{' '}
            {e.criteria_results.filter((r) => r.status === 'unclear').length} unclear
            {' '}(unclear excluded from score)
          </p>
          {e.classification_flags.map((f, i) => <div className="flag" key={i}>⚠ {f}</div>)}
        </>
      )}
    </details>
  )
}

/* --------------------------------------------------- not taken forward */

function NotConsidered({ skipped, failures }) {
  const total = (skipped?.length || 0) + (failures?.length || 0)
  if (!total) return <p className="muted tight">Nothing was set aside.</p>
  return (
    <table className="crit-table">
      <thead><tr><th style={{ width: '52%' }}>Page</th><th style={{ width: 150 }}>Outcome</th><th>Why</th></tr></thead>
      <tbody>
        {(failures || []).map((f) => (
          <tr key={f.source_url}>
            <td><a href={f.source_url} target="_blank" rel="noreferrer" className="mono small">{f.source_url}</a></td>
            <td><span className="pill not_met">{f.reason}</span></td>
            <td className="why">
              {f.detail}
              {f.trace_url && <> · <a href={f.trace_url} target="_blank" rel="noreferrer">trace ↗</a></>}
            </td>
          </tr>
        ))}
        {(skipped || []).map((s) => (
          <tr key={s.url}>
            <td><a href={s.url} target="_blank" rel="noreferrer" className="mono small">{s.url}</a></td>
            <td><span className="pill muted">not pursued</span></td>
            <td className="why">
              Fetched ({s.chars} chars) but the agent judged it not worth extracting
              {s.bare_domain && ' · homepage, not a call for entries'}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

/* ------------------------------------------------------------------- app */

export default function App() {
  const [data, setData] = useState(null)
  const [run, setRun] = useState(null)
  const [runId, setRunId] = useState(null)
  const [model, setModel] = useState(MODELS[0])
  const [budget, setBudget] = useState(18)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const timer = useRef(null)
  const pollsAfterDone = useRef(0)

  const refresh = useCallback(async () => {
    try { setData(await api('/api/state')) } catch (e) { setError(e.message) }
  }, [])

  useEffect(() => { refresh() }, [refresh])

  // Poll while a run is in flight. The journey is written to Mongo step by
  // step, so this fills in live without holding a connection open.
  useEffect(() => {
    if (!runId) return
    const tick = async () => {
      try {
        const r = await api(`/api/runs/${runId}`)
        setRun(r)
        if (r.status !== 'running') {
          // Discovery is done, but a full-pipeline run then evaluates
          // eligibility. Keep refreshing until the verdicts land.
          refresh()
          if (r.eligibility_done !== undefined || pollsAfterDone.current++ > 12) {
            clearInterval(timer.current)
            setBusy(false)
          }
        }
      } catch { /* run record not written yet */ }
    }
    timer.current = setInterval(tick, 1500)
    tick()
    return () => clearInterval(timer.current)
  }, [runId, refresh])

  const startRun = async (dry) => {
    setBusy(true); setError(null); setRun(null)
    try {
      const r = await api('/api/runs', {
        method: 'POST',
        body: JSON.stringify({ model, budget: Number(budget), dry_run: dry }),
      })
      setRunId(r.run_id)
    } catch (e) { setError(e.message); setBusy(false) }
  }

  const startPipeline = async (dry) => {
    setBusy(true); setError(null); setRun(null); pollsAfterDone.current = 0
    try {
      const r = await api('/api/pipeline', {
        method: 'POST',
        body: JSON.stringify({ model, budget: Number(budget), dry_run: dry }),
      })
      setRunId(r.run_id)
    } catch (e) { setError(e.message); setBusy(false) }
  }

  const startEligibility = async () => {
    setBusy(true); setError(null)
    try {
      await api('/api/eligibility', { method: 'POST', body: JSON.stringify({ model }) })
      setTimeout(() => { refresh(); setBusy(false) }, 4000)
    } catch (e) { setError(e.message); setBusy(false) }
  }

  return (
    <div className="wrap">
      <header className="top">
        <div>
          <h1>Opportunity Radar</h1>
          <div className="sub">discovery → extraction → eligibility, end to end</div>
        </div>
        <div className="spacer" />
        <select value={model} onChange={(e) => setModel(e.target.value)}>
          {MODELS.map((m) => <option key={m}>{m}</option>)}
        </select>
        <input
          type="number" min="1" max="60" value={budget} style={{ width: 70 }}
          onChange={(e) => setBudget(e.target.value)}
        />
        <button onClick={() => startPipeline(false)} disabled={busy}>
          {busy ? 'Running…' : '▶ Run full pipeline'}
        </button>
        <button className="ghost" onClick={() => startRun(false)} disabled={busy}>Discovery only</button>
        <button className="ghost" onClick={startEligibility} disabled={busy}>Eligibility only</button>
        <button className="ghost" onClick={() => startPipeline(true)} disabled={busy}>Dry run</button>
        <button className="ghost" onClick={refresh}>Refresh</button>
      </header>

      {error && <div className="card err" style={{ marginBottom: 16 }}>{error}</div>}

      <Metrics m={data?.metrics} />

      <div className="grid cols-2" style={{ marginTop: 16 }}>
        <div className="card">
          <h2>Agent journey</h2>
          <RunPanel run={run} />
        </div>

        <div className="card">
          <h2>Recent runs</h2>
          {(data?.runs || []).map((r) => (
            <div
              key={r.run_id}
              className="row small"
              style={{ padding: '7px 0', borderBottom: '1px solid var(--border)', cursor: 'pointer' }}
              onClick={() => { setRunId(r.run_id); setBusy(false) }}
            >
              <span className={`pill ${r.status === 'completed' ? 'met' : r.status === 'failed' ? 'not_met' : 'unclear'}`}>
                {r.status}
              </span>
              <span className="mono">{r.model}</span>
              <span className="muted">
                {r.counts?.saved ?? 0} saved · {r.counts?.failed ?? 0} failed
              </span>
            </div>
          ))}
          {!(data?.runs || []).length && <p className="muted tight">No runs yet.</p>}

        </div>
      </div>

      <div className="card" style={{ marginTop: 16 }}>
        <h2>Opportunities &amp; eligibility</h2>
        {(data?.opportunities || []).map((o) => <Opportunity key={o.source_url} o={o} />)}
        {!(data?.opportunities || []).length && (
          <p className="muted tight">Nothing stored yet — run the pipeline.</p>
        )}
        {!!(data?.opportunities || []).length
          && !(data.opportunities || []).some((o) => (o.eligibility_criteria || []).length) && (
          <p className="muted small tight" style={{ marginTop: 10 }}>
            Eligibility ran but had nothing to evaluate: no stored record carries
            eligibility criteria. Event and forum pages often state none.
          </p>
        )}
      </div>

      <div className="card" style={{ marginTop: 16 }}>
        <h2>Considered but not taken forward</h2>
        <NotConsidered skipped={data?.skipped} failures={data?.failures} />
      </div>
    </div>
  )
}
