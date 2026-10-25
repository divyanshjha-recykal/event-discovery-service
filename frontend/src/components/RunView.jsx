import { useCallback, useEffect, useRef, useState } from 'react'
import { useParams } from 'react-router-dom'
import { api, category as categoryOf, outcome as outcomeOf, runLabel, runStatus, shortId, STAGES, STAGE_OF } from '../api.js'
import { IconExternal, IconStop } from '../icons.jsx'
import ExportPanel from './ExportPanel.jsx'
import Journey from './Journey.jsx'
import Signals from './Signals.jsx'
import ComponentRun from './Components.jsx'
import Opportunity from './Opportunity.jsx'

function Stages({ run, events, stages = STAGES, labels = stages }) {
  const reached = new Set(events.map((e) => STAGE_OF[e.tool]).filter(Boolean))
  const running = run?.status === 'running'
  let current = -1
  stages.forEach((s, i) => { if (reached.has(s)) current = i })

  return (
    <div className="stages">
      {stages.map((stage, i) => {
        const done = running ? i < current : reached.has(stage)
        const active = running && i === current
        return (
          <span key={stage} className="stage-wrap">
            {i > 0 && <span className="stage-arrow" />}
            <span className={`stage${done ? ' done' : ''}${active ? ' active' : ''}`}>
              {labels[i]}
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
    <table className="grid">
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
              <span className={`tag ${outcomeOf(r.kind || r.outcome).cls}`}>
                {outcomeOf(r.kind || r.outcome).label}
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
  // Which kind of opportunity the Results tab is showing. A focused run still
  // keeps anything good it finds of another kind — the focus steers the search
  // and never discards — so the filtering belongs here, in the view.
  const [kind, setKind] = useState('all')
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
        if (meta.eligibility_done !== undefined || ['competitors', 'components'].includes(meta.budget?.focus)
            || settled.current++ > 12) {
          await loadResults()
          onRunFinished?.()
          return true
        }
      }
      return false
    }

    // The next poll starts only after this one ends, so two never share a cursor.
    const loop = async () => {
      let done = false
      try { done = await tick() } finally {
        if (!stopped && !done) timer = setTimeout(loop, 1500)
      }
    }
    loop()
    return () => { stopped = true; clearTimeout(timer) }
  }, [runId, loadResults, onRunFinished])

  if (error && !run) return <div className="card err">{error}</div>
  if (!run) return <div className="card muted">Loading run {shortId(runId)}…</div>

  const running = run.status === 'running'
  const b = run.budget || {}
  const counts = run.counts || {}
  const watch = b.focus === 'competitors'
  const parts = b.focus === 'components'
  // Both watches: plan, search, judge; no scrapes.
  const lean = watch || parts
  // A component run opens on its decisions; its steps are under How it ran.
  const partTabs = ['decisions', 'parts', 'trace']
  // A component run opens on How it ran, with its Result underneath; it never switches on its own.
  const autoTab = 'trace'
  const shownTab = parts ? (partTabs.includes(tab) ? tab : autoTab) : (partTabs.includes(tab) ? 'journey' : tab)
  const saved = results?.saved || []
  // One source of truth. The header used to count save operations while the
  // tabs counted stored records, so a run showed "5 ready" above "Results (3)".
  const totals = results?.totals || {
    ready: counts.saved ?? 0,
    needs_deeper: counts.needs_deeper ?? 0,
    set_aside: counts.rejected ?? 0,
  }
  // Ready first, then the ones that need more evidence.
  const found = [...saved].sort(
    (a, b) => (a.record_state === 'needs_deeper_read') - (b.record_state === 'needs_deeper_read'),
  )

  // Counts per kind, commonest first.
  const kinds = Object.entries(
    found.reduce((acc, o) => ({ ...acc, [o.category]: (acc[o.category] || 0) + 1 }), {}),
  ).sort((a, b) => b[1] - a[1])
  const shown = kind === 'all' ? found : found.filter((o) => o.category === kind)

  return (
    <>
      <div className="run-head">
        <div className="run-title">
          <div className="row">
            <span className={`tag ${runStatus(running ? 'running' : run.status).cls}`}>
              {runStatus(running ? 'running' : run.status).label}
            </span>
            <h2>{runLabel(run)}</h2>
            <span className="mono small muted">{shortId(run.run_id)}</span>
          </div>
          <div className="row small muted" style={{ marginTop: 4 }}>
            {parts ? (
              <>
                <span>{b.product}</span>
                <span>{{ priority: 'Top 80% of spend', all: 'All parts', named: 'Named parts' }[b.scope] || ''}</span>
                <span>{counts.offers ?? 0} findings</span>
                <span>{counts.searched_parts ?? 0} of {counts.parts ?? b.parts ?? 0} parts searched</span>
                <span>{counts.dropped ?? 0} pages dropped</span>
              </>
            ) : watch ? (
              <>
                <span>{counts.signals ?? 0} new signals</span>
                <span>{counts.merged ?? 0} added to known stories</span>
                <span>{counts.context ?? 0} low-relevance context</span>
                <span>{counts.dropped ?? 0} dropped</span>
                {b.since && <span>since {b.since}</span>}
              </>
            ) : (
              <>
                <span>{totals.ready} ready</span>
                <span>{totals.needs_deeper} need a deeper read</span>
                <span>{totals.set_aside} set aside</span>
              </>
            )}
            {b.elapsed != null && <span>{Math.round(b.elapsed)}s{lean ? '' : ' in discovery'}</span>}
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
                     kind={parts ? 'components' : watch ? 'competitors' : 'opportunities'}
                     onClose={() => setExporting(false)} />
      )}

      <div className="card">
        {lean
          ? <Stages run={run} events={events} stages={['plan', 'search', 'evaluate']} labels={['plan', 'search', 'judge']} />
          : <Stages run={run} events={events} />}
        <div className="meters">
          <Meter label="tool calls" used={b.spent ?? 0} cap={b.tool_calls ?? 0} />
          <Meter label="searches" used={b.searches ?? counts.searched ?? 0} cap={b.max_searches ?? 0} />
          {!lean && <Meter label="scrapes" used={b.scrapes ?? counts.scraped ?? 0} cap={b.max_scrapes ?? 0} />}
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
        {(parts ? [
          ['trace', 'How it ran'],
          ['decisions', 'Decisions'],
          ['parts', `Parts (${counts.parts ?? b.parts ?? 0})`],
        ] : watch ? [
          ['journey', `Journey (${events.length})`],
          ['signals', `Signals (${counts.signals ?? 0})`],
        ] : [
          ['journey', `Journey (${events.length})`],
          ['opportunities', `Results (${totals.ready + totals.needs_deeper})`],
          ['aside', `Set aside (${totals.set_aside})`],
        ]).map(([key, label]) => (
          <button key={key} type="button"
                  className={`tab${shownTab === key ? ' on' : ''}`}
                  onClick={() => setTab(key)}>
            {label}
          </button>
        ))}
      </div>

      <div className="card">
        {shownTab === 'journey' && (
          <Journey run={run} events={events} saved={found} totals={totals} live={running} />
        )}

        {shownTab === 'opportunities' && (
          found.length ? (
            <>
              {kinds.length > 1 && (
                <div className="kind-filter">
                  <button type="button"
                          className={`focus-opt${kind === 'all' ? ' on' : ''}`}
                          onClick={() => setKind('all')}>
                    All {found.length}
                  </button>
                  {kinds.map(([key, count]) => (
                    <button key={key} type="button"
                            className={`focus-opt${kind === key ? ' on' : ''}`}
                            onClick={() => setKind(key)}>
                      {categoryOf(key).label} {count}
                    </button>
                  ))}
                </div>
              )}
              {shown.map((o) => (
                <Opportunity key={`${o.source_url}-${o.base_title}`} o={o} />
              ))}
              {!shown.length && (
                <p className="muted tight">
                  Nothing of that kind in this run&rsquo;s results.
                </p>
              )}
              {!!(results?.missing || []).length && (
                <p className="small muted">
                  {results.missing.length} record(s) this run saved now belong to a
                  later run that updated them, or the database was cleared.
                </p>
              )}
            </>
          ) : (
            <p className="muted tight">
              {running ? 'Nothing found yet.' : 'This run saved no opportunities.'}
            </p>
          )
        )}

        {shownTab === 'aside' && <SetAside results={results} />}

        {shownTab === 'signals' && <Signals runId={runId} count={counts.signals} live={running} />}

        {parts && <ComponentRun runId={runId} live={running} events={events} tab={shownTab} partsTotal={b.parts ?? 0}
                                  status={run.status} summary={run.summary} />}
      </div>
    </>
  )
}
