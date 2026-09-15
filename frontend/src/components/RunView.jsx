import { useCallback, useEffect, useRef, useState } from 'react'
import { useParams } from 'react-router-dom'
import { api, runLabel, shortId, STAGES, STAGE_OF } from '../api.js'
import { IconExternal, IconStop } from '../icons.jsx'
import ExportPanel from './ExportPanel.jsx'
import Journey from './Journey.jsx'
import Opportunity from './Opportunity.jsx'

const STATUS_CLASS = {
  completed: 'met',
  completed_with_rejections: 'met',
  running: 'unclear',
  failed: 'not_met',
}

function Stages({ run, events }) {
  const reached = new Set(events.map((e) => STAGE_OF[e.tool]).filter(Boolean))
  const running = run?.status === 'running'
  let current = -1
  STAGES.forEach((s, i) => { if (reached.has(s)) current = i })

  return (
    <div className="stages">
      {STAGES.map((stage, i) => {
        const done = running ? i < current : reached.has(stage)
        const active = running && i === current
        return (
          <span key={stage} className="stage-wrap">
            {i > 0 && <span className="stage-arrow" />}
            <span className={`stage${done ? ' done' : ''}${active ? ' active' : ''}`}>
              {stage}
            </span>
          </span>
        )
      })}
    </div>
  )
}

function Meter({ label, used, cap }) {
  const pct = cap ? Math.min(100, (used / cap) * 100) : 0
  return (
    <div className="meter">
      <div className="meter-top">
        <span className="small muted">{label}</span>
        <span className="small mono">{used}<span className="muted">/{cap}</span></span>
      </div>
      <div className="track"><i style={{ width: `${pct}%` }} className={pct >= 100 ? 'full' : ''} /></div>
    </div>
  )
}

function SetAside({ results }) {
  const rows = [
    ...(results?.failures || []).map((f) => ({ ...f, kind: 'extraction failed' })),
    ...(results?.set_aside || []),
  ]
  if (!rows.length) return <p className="muted tight">Nothing was set aside in this run.</p>
  return (
    <table className="crit">
      <thead>
        <tr>
          <th style={{ width: '44%' }}>Page</th>
          <th style={{ width: 150 }}>Outcome</th>
          <th>Why</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r, i) => (
          <tr key={`${r.url}-${i}`}>
            <td>
              {r.title && <div>{r.title}</div>}
              <a className="u mono small" href={r.url} target="_blank" rel="noreferrer">{r.url}</a>
            </td>
            <td>
              <span className={`pill ${r.kind ? 'not_met' : 'muted'}`}>
                {r.kind || r.outcome}
              </span>
            </td>
            <td className="why">{r.reason || r.detail}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

export default function RunView({ onRunFinished, onStop, stopping }) {
  const { runId } = useParams()
  const [run, setRun] = useState(null)
  const [events, setEvents] = useState([])
  const [results, setResults] = useState(null)
  const [tab, setTab] = useState('journey')
  const [error, setError] = useState(null)
  const [exporting, setExporting] = useState(false)

  const cursor = useRef(0)      // journey rows already held
  const settled = useRef(0)     // polls since the run stopped running
  const savedSeen = useRef(-1)  // last saved count results were fetched for

  const loadResults = useCallback(async () => {
    try { setResults(await api(`/api/runs/${runId}/results`)) } catch { /* not ready */ }
  }, [runId])

  // Switching runs resets everything, including the delta cursor.
  useEffect(() => {
    setRun(null); setEvents([]); setResults(null); setError(null)
    cursor.current = 0; settled.current = 0; savedSeen.current = -1
  }, [runId])

  useEffect(() => {
    if (!runId) return undefined
    let timer
    let stopped = false

    const tick = async () => {
      let payload
      try {
        payload = await api(`/api/runs/${runId}/events?after=${cursor.current}`)
        setError(null)
      } catch (e) {
        setError(e.message)
        return
      }
      if (stopped) return

      const { events: fresh, ...meta } = payload
      if (fresh.length) {
        cursor.current += fresh.length
        setEvents((prev) => [...prev, ...fresh])
      }
      setRun(meta)

      // Refetch the saved records only when the count actually moves, so the
      // Opportunities tab fills in live without a heavy query every poll.
      const saved = meta.counts?.saved ?? 0
      if (saved !== savedSeen.current) {
        savedSeen.current = saved
        await loadResults()
      }

      if (meta.status !== 'running') {
        // Eligibility runs after discovery returns, so keep polling briefly
        // until it reports in rather than calling the run done too early.
        if (meta.eligibility_done !== undefined || settled.current++ > 12) {
          clearInterval(timer)
          await loadResults()
          onRunFinished?.()
        }
      }
    }

    tick()
    timer = setInterval(tick, 1500)
    return () => { stopped = true; clearInterval(timer) }
  }, [runId, loadResults, onRunFinished])

  if (error && !run) return <div className="card err">{error}</div>
  if (!run) return <div className="card muted">Loading run {shortId(runId)}…</div>

  const running = run.status === 'running'
  const b = run.budget || {}
  const counts = run.counts || {}
  const saved = results?.saved || []

  return (
    <>
      <div className="run-head">
        <div className="run-title">
          <div className="row">
            <span className={`pill ${STATUS_CLASS[run.status] || 'muted'}`}>
              {running ? 'running' : run.status}
            </span>
            <h2>{runLabel(run)}</h2>
            <span className="mono small muted">{shortId(run.run_id)}</span>
          </div>
          <div className="row small muted" style={{ marginTop: 4 }}>
            <span>{counts.saved ?? 0} saved</span>
            <span>{counts.extracted ?? 0} extracted</span>
            <span>{counts.rejected ?? 0} set aside</span>
            <span>{counts.failed ?? 0} failures</span>
            {b.elapsed != null && <span>{Math.round(b.elapsed)}s in discovery</span>}
            {/* Wall time covers eligibility too, which runs after the budget stops. */}
            {run.finished_at && run.started_at && (
              <span>
                {Math.round(
                  (new Date(run.finished_at) - new Date(run.started_at)) / 1000,
                )}s end to end
              </span>
            )}
          </div>
        </div>
        <span className="spacer" />
        {running && (
          <button className="ghost stop" onClick={onStop} disabled={stopping} type="button">
            <IconStop /> {stopping ? 'Stopping…' : 'Stop'}
          </button>
        )}
        <button className="ghost" type="button" onClick={() => setExporting(true)}
                disabled={!events.length}>
          Export
        </button>
        {run.trace_url && (
          <a className="ghost btnlike small" href={run.trace_url} target="_blank" rel="noreferrer">
            Trace <IconExternal />
          </a>
        )}
      </div>

      {exporting && (
        <ExportPanel runId={runId} saved={saved} events={events}
                     onClose={() => setExporting(false)} />
      )}

      <div className="card">
        <Stages run={run} events={events} />
        <div className="meters">
          <Meter label="tool calls" used={b.spent ?? 0} cap={b.tool_calls ?? 0} />
          <Meter label="searches" used={b.searches ?? counts.searched ?? 0} cap={b.max_searches ?? 0} />
          <Meter label="scrapes" used={b.scrapes ?? counts.scraped ?? 0} cap={b.max_scrapes ?? 0} />
          <Meter label="model calls" used={b.llm_calls ?? 0} cap={b.max_llm_calls ?? 0} />
        </div>
        {b.stop_reason && (
          <p className="small err tight" style={{ marginTop: 10 }}>Stopped: {b.stop_reason}</p>
        )}
        {run.eligibility_done && (
          <p className="small muted tight" style={{ marginTop: 10 }}>
            Eligibility evaluated {run.eligibility_evaluated ?? 0} record(s)
            {(run.eligibility_failures || []).length
              ? `, skipped ${run.eligibility_failures.length} with no usable criteria` : ''}
          </p>
        )}
      </div>

      <div className="tabs">
        {[
          ['journey', `Journey (${events.length})`],
          ['opportunities', `Opportunities (${saved.length})`],
          ['aside', `Set aside (${(results?.set_aside || []).length + (results?.failures || []).length})`],
        ].map(([key, label]) => (
          <button key={key} type="button"
                  className={`tab${tab === key ? ' on' : ''}`}
                  onClick={() => setTab(key)}>
            {label}
          </button>
        ))}
      </div>

      <div className="card">
        {tab === 'journey' && (
          <Journey run={run} events={events} saved={saved} live={running} />
        )}

        {tab === 'opportunities' && (
          saved.length ? (
            <>
              {saved.map((o) => <Opportunity key={o.source_url} o={o} />)}
              {!!(results?.missing || []).length && (
                <p className="small muted">
                  {results.missing.length} record(s) this run saved are no longer in
                  storage — the database was cleared after the run.
                </p>
              )}
            </>
          ) : (
            <p className="muted tight">
              {running ? 'Nothing saved yet.' : 'This run saved no opportunities.'}
            </p>
          )
        )}

        {tab === 'aside' && <SetAside results={results} />}
      </div>
    </>
  )
}
