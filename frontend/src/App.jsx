import { useCallback, useEffect, useRef, useState } from 'react'

const MODELS = [
  'google/gemma-4-31b-it',
  'qwen/qwen3-32b',
  'z-ai/glm-4.7-flash',
  'ibm-granite/granite-4.1-8b',
]

// The graph's nodes, in execution order — the live progress strip.
const STAGES = ['plan', 'research', 'analyze', 'finalize']

// Which stage a journey event belongs to, so progress is inferred from the
// journey itself rather than needing the backend to report a current node.
const STAGE_OF = {
  plan: 'plan',
  search: 'research',
  scrape: 'research',
  analyze: 'analyze',
  extract: 'finalize',
  save_opportunity: 'finalize',
  actionability: 'finalize',
  skip: 'finalize',
}

const api = async (path, options) => {
  const res = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!res.ok) throw new Error(`${path} → ${res.status}`)
  return res.json()
}

/* ------------------------------------------------------------------ theme */

const useTheme = () => {
  const [theme, setTheme] = useState(() => {
    try { return localStorage.getItem('or-theme') || 'dark' } catch { return 'dark' }
  })
  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
    try { localStorage.setItem('or-theme', theme) } catch { /* private mode */ }
  }, [theme])
  return [theme, () => setTheme((t) => (t === 'dark' ? 'light' : 'dark'))]
}

/* ---------------------------------------------------------------- metrics */

const Stat = ({ n, l }) => (
  <div className="card stat" style={{ marginBottom: 0 }}>
    <div className="n">{n}</div><div className="l">{l}</div>
  </div>
)

function Metrics({ m }) {
  if (!m) return null
  const { verdicts, criteria } = m
  const total = criteria.met + criteria.not_met + criteria.unclear
  return (
    <div className="grid cols-4" style={{ marginBottom: 16 }}>
      <Stat n={m.opportunities} l="opportunities stored" />
      <Stat n={m.programs} l="programs tracked" />
      <Stat n={`${m.extraction_success}/${m.extraction_success + m.extraction_failed}`}
            l="latest-run extractions succeeded" />
      <div className="card stat" style={{ marginBottom: 0 }}>
        <div className="n">
          {verdicts.high}<span className="muted" style={{ fontSize: 14 }}> high</span>{' '}
          {verdicts.low}<span className="muted" style={{ fontSize: 14 }}> low</span>
        </div>
        <div className="l">confidence · {verdicts.unevaluated} unevaluated</div>
        {total > 0 && (
          <>
            <div className="bar" style={{ marginTop: 10 }}>
              <i className="met" style={{ width: `${(criteria.met / total) * 100}%` }} />
              <i className="not_met" style={{ width: `${(criteria.not_met / total) * 100}%` }} />
              <i className="unclear" style={{ width: `${(criteria.unclear / total) * 100}%` }} />
            </div>
            <div className="l" style={{ marginTop: 6 }}>
              {criteria.met} met · {criteria.not_met} not met · {criteria.unclear} unclear
            </div>
          </>
        )}
      </div>
    </div>
  )
}

/* ------------------------------------------------------- live stage strip */

function Stages({ run, busy }) {
  const events = run?.journey || []
  const reached = new Set(events.map((e) => STAGE_OF[e.tool]).filter(Boolean))
  const running = busy && run?.status === 'running'
  let current = -1
  STAGES.forEach((s, i) => { if (reached.has(s)) current = i })

  return (
    <div className="stages">
      {STAGES.map((stage, i) => {
        const done = !running ? reached.has(stage) : i < current
        const active = running && i === current
        return (
          <span key={stage} style={{ display: 'contents' }}>
            {i > 0 && <span className="stage-arrow">→</span>}
            <span className={`stage${done ? ' done' : ''}${active ? ' active' : ''}`}>
              {stage}
            </span>
          </span>
        )
      })}
      <span className="muted small" style={{ marginLeft: 8 }}>
        {run ? (running ? 'running…' : run.status) : 'idle'}
      </span>
    </div>
  )
}

/* ------------------------------------------------------------ run journey */

function Step({ e }) {
  const bad = e.outcome === 'failed' || e.outcome === 'insufficient'
  return (
    <div className={`step ${e.tool}${bad ? ' failed' : ''}`}>
      <div className="t">t+{e.t}s</div>
      <div className="tool">{e.tool}</div>
      <div>
        {e.tool === 'plan' && <div className="muted small">query plan produced</div>}

        {e.tool === 'search' && (
          <>
            <div className="mono">{e.query}</div>
            <details style={{ marginTop: 8 }}>
              <summary className="muted small">{(e.results || []).length} result(s)</summary>
              {(e.results || []).map((r) => (
                <a className="result" key={r.url} href={r.url} target="_blank" rel="noreferrer">
                  <div>{r.title}</div><div className="u">{r.url}</div>
                </a>
              ))}
            </details>
          </>
        )}

        {e.tool === 'scrape' && (
          <div>
            <a href={e.url} target="_blank" rel="noreferrer" className="mono small">{e.url}</a>
            <div className="row" style={{ marginTop: 4 }}>
              {e.outcome === 'ok' && <span className="pill muted">{e.chars} chars</span>}
              {e.outcome === 'insufficient' && <span className="pill not_met">too little content</span>}
              {e.outcome === 'failed' && <span className="pill not_met">scrape failed</span>}
              {e.bare_domain && <span className="pill unclear">homepage</span>}
              {e.depth != null && <span className="pill muted">L{e.depth}</span>}
            </div>
            {e.detail && <div className="small err" style={{ marginTop: 4 }}>{e.detail}</div>}
          </div>
        )}

        {e.tool === 'analyze' && (
          <div>
            <span className="pill muted">{e.outcome}</span>
            {(e.candidates || []).map((c, i) => (
              <div key={i} style={{ marginTop: 6 }}>
                <span className={`pill ${c.decision === 'pursue' ? 'met' : 'muted'}`}>
                  {c.decision}
                </span>{' '}
                <strong>{c.title}</strong>
                <div className="small muted">{c.reason}</div>
              </div>
            ))}
            {(e.errors || []).map((x, i) => (
              <div key={`e${i}`} className="small err" style={{ marginTop: 4 }}>
                {x.seed_url}: {x.detail}
              </div>
            ))}
          </div>
        )}

        {e.tool === 'extract' && (
          e.outcome === 'ok' ? (
            <div>
              <strong>{e.record?.title}</strong>
              <div className="row small muted" style={{ marginTop: 4 }}>
                <span>{e.record?.organizing_body}</span>
                <span className="pill muted">{e.record?.category}</span>
                <span className={`pill ${e.record?.deadline_verified ? 'met' : 'unclear'}`}>
                  {e.record?.submission_deadline || 'no deadline'}
                </span>
              </div>
            </div>
          ) : (
            <div>
              <a href={e.url} target="_blank" rel="noreferrer" className="mono small">{e.url}</a>
              <div style={{ marginTop: 4 }}><span className="pill not_met">{e.reason}</span></div>
              <div className="small err">{e.detail}</div>
            </div>
          )
        )}

        {(e.tool === 'skip' || e.tool === 'actionability') && (
          <div>
            <span className={`pill ${e.outcome === 'actionable' ? 'met' : 'unclear'}`}>
              {e.outcome}
            </span>{' '}
            {e.title && <strong>{e.title}</strong>}
            <div className="small muted">{e.reason}</div>
          </div>
        )}

        {e.tool === 'save_opportunity' && (
          <div>
            <span className="pill met">{e.action}</span> <strong>{e.title}</strong>
            {(e.warnings || []).map((w, i) => <div className="flag" key={i}>⚠ {w}</div>)}
          </div>
        )}
      </div>
    </div>
  )
}

/* ----------------------------------------------------------- opportunity */

function Opportunity({ o, latest }) {
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
  ]

  return (
    <div className={`opp${latest ? ' latest' : ''}`}>
      <h3>{o.title}</h3>
      <div className="row small muted" style={{ marginBottom: 6 }}>
        <span>{o.organizing_body}</span>
        <span className="pill muted">{o.category}</span>
        <span className="pill muted">cycle {o.cycle_year}</span>
        <span className={`pill ${o.submission_deadline ? 'met' : 'muted'}`}>
          {o.submission_deadline || 'no deadline'}
          {o.submission_deadline && (o.deadline_verified ? ' ✓' : ' unverified')}
        </span>
        {e && <span className={`pill ${e.confidence}`}>confidence: {e.confidence}</span>}
        {o.dry_run && <span className="pill unclear">fixture</span>}
      </div>
      <a className="src mono" href={o.source_url} target="_blank" rel="noreferrer">
        {o.source_url}
      </a>

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
        {rows.length > 0 && <span className="muted"> — {rows.length} extracted</span>}
      </div>

      {!e && !!(o.eligibility_criteria || []).length && (
        <ul className="plain">
          {o.eligibility_criteria.map((c, i) => <li key={i}>{c}</li>)}
        </ul>
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
                <th style={{ width: '44%' }}>Condition</th>
                <th style={{ width: 110 }}>Verdict</th>
                <th>Reason</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r, i) => (
                <tr key={i}>
                  <td>{r.criterion}</td>
                  <td><span className={`pill ${r.verdict}`}>{r.verdict.replace('_', ' ')}</span></td>
                  <td className="why">{r.reason}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="small muted" style={{ marginTop: 8 }}>
            score {e.score === null ? 'n/a' : e.score.toFixed(2)} · confidence {e.confidence} ·{' '}
            {e.criteria_results.filter((r) => r.status === 'met').length} met,{' '}
            {e.criteria_results.filter((r) => r.status === 'not_met').length} not met,{' '}
            {e.criteria_results.filter((r) => r.status === 'unclear').length} unclear,{' '}
            {e.qualitative_notes.length} qualitative
          </p>
          {(e.classification_flags || []).map((f, i) => <div className="flag" key={i}>⚠ {f}</div>)}
        </>
      )}

      {o.extraction_completeness && (
        <p className="small muted tight" style={{ marginTop: 6 }}>
          extraction completeness {Math.round((o.extraction_completeness.score || 0) * 100)}%
          {(o.extraction_completeness.gaps || []).length > 0 &&
            ` · gaps: ${o.extraction_completeness.gaps.join(', ')}`}
          {` · ${(o.evidence_urls || []).length || 1} source page(s)`}
        </p>
      )}
    </div>
  )
}

/* ------------------------------------------------------------------- app */

export default function App() {
  const [theme, toggleTheme] = useTheme()
  const [data, setData] = useState(null)
  const [run, setRun] = useState(null)
  const [runId, setRunId] = useState(null)
  const [model, setModel] = useState(MODELS[0])
  const [budget, setBudget] = useState(18)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [confirmClear, setConfirmClear] = useState(false)
  const timer = useRef(null)
  const pollsAfterDone = useRef(0)

  const refresh = useCallback(async () => {
    try { setData(await api('/api/state')) } catch (e) { setError(e.message) }
  }, [])

  useEffect(() => { refresh() }, [refresh])

  useEffect(() => {
    if (!runId) return
    const tick = async () => {
      try {
        const r = await api(`/api/runs/${runId}`)
        setRun(r)
        if (r.status !== 'running') {
          refresh()
          if (r.eligibility_done !== undefined || pollsAfterDone.current++ > 12) {
            clearInterval(timer.current); setBusy(false)
          }
        }
      } catch { /* run record not written yet */ }
    }
    timer.current = setInterval(tick, 1500)
    tick()
    return () => clearInterval(timer.current)
  }, [runId, refresh])

  const start = async (path, dry) => {
    setBusy(true); setError(null); setRun(null); pollsAfterDone.current = 0
    try {
      const r = await api(path, {
        method: 'POST',
        body: JSON.stringify({ model, budget: Number(budget), dry_run: dry }),
      })
      if (r.run_id) setRunId(r.run_id)
      else setTimeout(() => { refresh(); setBusy(false) }, 4000)
    } catch (e) { setError(e.message); setBusy(false) }
  }

  const clearDatabase = async () => {
    setConfirmClear(false); setBusy(true)
    try {
      await api('/api/database/clear', { method: 'POST' })
      setRun(null); setRunId(null); await refresh()
    } catch (e) { setError(e.message) } finally { setBusy(false) }
  }

  const opportunities = data?.opportunities || []
  const latest = opportunities.filter((o) => o.from_latest_run)
  const evaluated = opportunities.filter((o) => o.eligibility)

  return (
    <div className="wrap">
      <header className="top">
        <div>
          <h1>Opportunity Radar</h1>
          <div className="sub">discovery → extraction → eligibility, end to end</div>
        </div>
        <div className="spacer" />
        <select value={model} onChange={(ev) => setModel(ev.target.value)}>
          {MODELS.map((m) => <option key={m}>{m}</option>)}
        </select>
        <input type="number" min="1" max="60" value={budget} style={{ width: 68 }}
               onChange={(ev) => setBudget(ev.target.value)} />
        <button onClick={() => start('/api/pipeline', false)} disabled={busy}>
          {busy ? 'Running…' : '▶ Run full pipeline'}
        </button>
        <button className="ghost" onClick={() => start('/api/runs', false)} disabled={busy}>Discovery</button>
        <button className="ghost" onClick={() => start('/api/eligibility', false)} disabled={busy}>Eligibility</button>
        <button className="ghost" onClick={() => start('/api/pipeline', true)} disabled={busy}>Dry run</button>
        <button className="ghost" onClick={refresh}>Refresh</button>
        <button className="ghost" onClick={toggleTheme} title="Toggle light/dark">
          {theme === 'dark' ? '☀' : '☾'}
        </button>
        <button className="danger" onClick={() => setConfirmClear(true)} disabled={busy}>
          Clear DB
        </button>
      </header>

      {error && <div className="card err">{error}</div>}

      <div className="card" style={{ padding: '12px 16px' }}>
        <Stages run={run} busy={busy} />
      </div>

      <Metrics m={data?.metrics} />

      <div className="card">
        <h2>Recent runs</h2>
        {(data?.runs || []).map((r) => (
          <div key={r.run_id}
               className={`runrow${r.run_id === runId ? ' selected' : ''}`}
               onClick={() => { setRunId(r.run_id); setBusy(false) }}>
            <span className={`pill ${r.status === 'completed' ? 'met'
              : r.status === 'failed' ? 'not_met' : 'unclear'}`}>{r.status}</span>
            <span className="mono small">{r.model}</span>
            <span className="muted small">
              {r.counts?.saved ?? 0} saved · {r.counts?.rejected ?? 0} rejected ·{' '}
              {r.counts?.historical ?? 0} historical · {r.counts?.failed ?? 0} failed
            </span>
            <div className="spacer" />
            {r.trace_url && (
              <a href={r.trace_url} target="_blank" rel="noreferrer" className="small"
                 onClick={(ev) => ev.stopPropagation()}>trace ↗</a>
            )}
          </div>
        ))}
        {!(data?.runs || []).length && <p className="muted tight">No runs yet.</p>}
      </div>

      <div className="card">
        <h2>Agent journey</h2>
        {!run && <p className="muted tight">Select a run above, or start one.</p>}
        {run && (
          <>
            <div className="row small muted" style={{ marginBottom: 10 }}>
              <span className="mono">{run.model}</span>
              <span>
                {run.budget?.spent ?? 0}/{run.budget?.tool_calls} calls ·{' '}
                {run.counts?.searched ?? 0} searches · {run.counts?.scraped ?? 0} scraped ·{' '}
                {run.counts?.extracted ?? 0} extracted · {run.counts?.saved ?? 0} saved
              </span>
            </div>
            {!!(run.thinking || []).length && (
              <details style={{ marginBottom: 12 }}>
                <summary>Agent reasoning ({run.thinking.length})</summary>
                {run.thinking.map((t, i) => (
                  <p key={i} className="small" style={{ whiteSpace: 'pre-wrap' }}>{t}</p>
                ))}
              </details>
            )}
            {(run.journey || []).map((e) => <Step key={e.seq} e={e} />)}
            {run.summary && (
              <details style={{ marginTop: 12 }}>
                <summary>Run summary</summary>
                <p className="small" style={{ whiteSpace: 'pre-wrap' }}>{run.summary}</p>
              </details>
            )}
          </>
        )}
      </div>

      <div className="card">
        <h2>This run <span className="count">— {latest.length}</span></h2>
        {latest.map((o) => <Opportunity key={o.source_url} o={o} latest />)}
        {!latest.length && (
          <p className="muted tight">Nothing stored by the most recent run.</p>
        )}
      </div>

      <div className="card">
        <h2>All evaluated opportunities <span className="count">— {evaluated.length}</span></h2>
        <p className="muted small" style={{ marginTop: -6 }}>
          Every opportunity with an eligibility verdict, across all runs.
        </p>
        {evaluated.map((o) => <Opportunity key={`all-${o.source_url}`} o={o} />)}
        {!evaluated.length && <p className="muted tight">None evaluated yet.</p>}
      </div>

      <div className="card">
        <h2>Considered but not taken forward</h2>
        <table className="crit">
          <thead>
            <tr><th style={{ width: '50%' }}>Page</th><th style={{ width: 150 }}>Outcome</th><th>Why</th></tr>
          </thead>
          <tbody>
            {(data?.failures || []).map((f) => (
              <tr key={f.source_url}>
                <td><a href={f.source_url} target="_blank" rel="noreferrer" className="mono small">{f.source_url}</a></td>
                <td><span className="pill not_met">{f.reason}</span></td>
                <td className="why">
                  {f.detail}
                  {f.trace_url && <> · <a href={f.trace_url} target="_blank" rel="noreferrer">trace ↗</a></>}
                </td>
              </tr>
            ))}
            {(data?.skipped || []).map((s) => (
              <tr key={s.url}>
                <td><a href={s.url} target="_blank" rel="noreferrer" className="mono small">{s.url}</a></td>
                <td><span className="pill muted">{s.outcome || 'not pursued'}</span></td>
                <td className="why">
                  {s.reason || `Fetched (${s.chars} chars) but not taken forward`}
                  {s.bare_domain && ' · homepage'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {!(data?.failures || []).length && !(data?.skipped || []).length && (
          <p className="muted tight">Nothing set aside.</p>
        )}
      </div>

      {confirmClear && (
        <div className="modal-back" onClick={() => setConfirmClear(false)}>
          <div className="modal" onClick={(ev) => ev.stopPropagation()}>
            <h3>Clear the database?</h3>
            <p className="small muted">
              Deletes every stored opportunity, the program registry, all run history
              and extraction failures. The business profile and golden set are files
              and are not touched. This cannot be undone.
            </p>
            <div className="row" style={{ marginTop: 16 }}>
              <button className="danger" onClick={clearDatabase}>Yes, delete everything</button>
              <button className="ghost" onClick={() => setConfirmClear(false)}>Cancel</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
