import { useEffect, useMemo, useRef, useState } from 'react'
import { outcome as outcomeOf, VERDICT } from '../api.js'
import { IconChevron, IconDot, IconExternal, TOOL_ICON } from '../icons.jsx'

const BAD = new Set(['failed', 'insufficient'])
const WARN = new Set(['fallback', 'no_new_evidence', 'partial'])
const toneOf = (e) => (BAD.has(e.outcome) ? 'bad' : WARN.has(e.outcome) ? 'warn' : 'ok')
const plural = (n, one, many) => `${n} ${n === 1 ? one : many}`

/** Re-sync open/closed state when Expand all / Collapse all is pressed. */
function useExpandAll(epoch, apply) {
  const seen = useRef(epoch)
  useEffect(() => {
    if (seen.current !== epoch) { seen.current = epoch; apply() }
  })
}

const NODE = {
  plan: ['Plan', 'Turns the business profile into a search plan.'],
  research: ['Research', 'Searches, chooses which sites to read, and fetches their pages.'],
  analyze: ['Analyze', 'Reads each site and produces the structured listing — what the opportunity is, its dates, and its entry conditions.'],
  finalize: ['Finalize', 'Checks each listing is still live, judges it against the business profile, and stores it.'],
}

const STEP_NAME = {
  plan: 'Plan',
  search: 'Search',
  shortlist: 'Choose sites',
  select_links: 'Follow links',
  scrape: 'Read page',
  memory: 'Memory',
  analyze: 'Analyze',
  extract: 'Build record',
  actionability: 'Check if live',
  feasibility: 'Check against profile',
  save_opportunity: 'Store',
}

const Url = ({ href, children }) => (
  <a className="u mono" href={href} target="_blank" rel="noreferrer">{children || href}</a>
)

const Raw = ({ e }) => (
  <details className="raw">
    <summary className="small muted">Raw event</summary>
    <pre className="mono small">{JSON.stringify(e, null, 2)}</pre>
  </details>
)

/* ------------------------------------------------------------ step bodies */

function PlanBody({ e }) {
  return (
    <>
      {e.outcome === 'fallback' && (
        <p className="err small tight">
          The planner call failed; the deterministic fallback plan ran instead.
          {e.detail ? ` ${e.detail}` : ''}
        </p>
      )}
      <table className="grid">
        <thead><tr><th style={{ width: '38%' }}>Query</th><th>Why</th></tr></thead>
        <tbody>
          {(e.queries || []).map((q, i) => (
            <tr key={i}>
              <td className="mono">{q.query}</td>
              <td className="why">{q.rationale}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  )
}

function SearchBody({ e }) {
  const rows = e.results || []
  return (
    <>
      {e.detail && <p className="err small tight">{e.detail}</p>}
      {!rows.length && <p className="muted small tight">No results.</p>}
      {!!rows.length && (
        <table className="grid">
          <thead><tr><th style={{ width: '30%' }}>Title</th><th style={{ width: 210 }}>Link</th><th>Snippet</th></tr></thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.url}>
                <td>{r.title}</td>
                <td><Url href={r.url}>{r.url.replace(/^https?:\/\//, '').slice(0, 42)}</Url></td>
                <td className="why clamp">{r.snippet}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </>
  )
}

function ChooseSitesBody({ e }) {
  if (e.outcome !== 'ok') {
    return <p className="err small tight">{e.detail || 'Selection failed; fell back to search order.'}</p>
  }
  return (
    <table className="grid">
      <thead><tr><th style={{ width: '34%' }}>Site</th><th style={{ width: 210 }}>Link</th><th>Why chosen</th></tr></thead>
      <tbody>
        {(e.picked || []).map((p, i) => (
          <tr key={i}>
            <td>{p.title}</td>
            <td><Url href={p.url}>{p.url.replace(/^https?:\/\//, '').slice(0, 42)}</Url></td>
            <td className="why">{p.reason}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

function PageBody({ e, followed }) {
  return (
    <>
      <div className="kv">
        <Url href={e.url} />
        <div className="tags">
          {e.status_code != null && (
            <span className={`tag ${e.status_code >= 200 && e.status_code < 300 ? 'muted' : 'bad'}`}>
              HTTP {e.status_code}
            </span>
          )}
          <span className="tag muted">{(e.chars ?? 0).toLocaleString()} chars</span>
          {e.bare_domain && <span className="tag warn">homepage</span>}
        </div>
      </div>
      {e.page_title && <div className="pagetitle">{e.page_title}</div>}
      {e.detail && <p className="err small tight">{e.detail}</p>}
      {e.preview && (
        <details className="raw">
          <summary className="small muted">
            Page content as read{e.truncated ? ' (first 20,000 chars)' : ''}
          </summary>
          <pre className="mono small scraped">{e.preview}</pre>
        </details>
      )}
      {!!followed.length && (
        <div className="nested">
          <div className="nested-label">
            {plural(followed.length, 'page followed from here', 'pages followed from here')}
          </div>
          {followed.map((child) => (
            <div className="nested-item" key={child.seq}>
              <PageBody e={child} followed={[]} />
            </div>
          ))}
        </div>
      )}
    </>
  )
}

function AnalyzeBody({ e }) {
  const cands = e.candidates || []
  if (!cands.length) {
    return <p className="muted small tight">No opportunities identified on this site.</p>
  }
  return (
    <>
      {cands.map((c, i) => (
        <div className="cand" key={i}>
          <div className="kv">
            <div>
              <strong>{c.title}</strong>
              <Url href={c.url} />
            </div>
            <div className="tags">
              <span className={`tag ${c.decision === 'pursue' ? 'ok' : 'muted'}`}>
                {c.decision === 'pursue' ? 'Pursue' : 'Not relevant'}
              </span>
              {c.category && <span className="tag muted">{c.category}</span>}
            </div>
          </div>
          <p className="why tight">{c.reason}</p>
          {!!(c.entry_eligibility || []).length && (
            <table className="grid tightgrid">
              <thead><tr><th>Entry conditions found on the page</th></tr></thead>
              <tbody>
                {c.entry_eligibility.map((x, j) => <tr key={j}><td>{x}</td></tr>)}
              </tbody>
            </table>
          )}
        </div>
      ))}
      {(e.errors || []).map((x, i) => (
        <p className="err small" key={i}>{x.seed_url}: {x.detail}</p>
      ))}
    </>
  )
}

function ExtractBody({ e }) {
  if (e.outcome !== 'ok') {
    return (
      <>
        <Url href={e.url} />
        <div className="tags"><span className="tag bad">{e.reason}</span></div>
        {e.detail && <p className="err small">{e.detail}</p>}
      </>
    )
  }
  const r = e.record || {}
  const crit = r.criteria || []
  return (
    <>
      <div className="kv">
        <div><strong>{r.title}</strong><Url href={e.url} /></div>
        <div className="tags">
          <span className="tag muted">{r.category}</span>
          <span className="tag muted">cycle {r.cycle_year}</span>
          {r.submission_deadline
            ? <span className="tag ok">closes {r.submission_deadline}</span>
            : <span className="tag muted">no deadline published</span>}
          {r.event_date && <span className="tag muted">event {r.event_date}</span>}
        </div>
      </div>
      {crit.length ? (
        <table className="grid tightgrid">
          <thead><tr><th>Entry conditions extracted ({crit.length})</th></tr></thead>
          <tbody>{crit.map((c, i) => <tr key={i}><td>{c}</td></tr>)}</tbody>
        </table>
      ) : (
        <p className="warn-line small">
          The page states no entry conditions, so there is nothing to judge yet.
          {r.confidence_note ? ` ${r.confidence_note}` : ''}
        </p>
      )}
    </>
  )
}

function SimpleBody({ e }) {
  const o = outcomeOf(e.outcome)
  return (
    <>
      <div className="kv">
        <Url href={e.url} />
        <div className="tags">
          <span className={`tag ${o.cls}`}>{o.label}</span>
          {e.action && <span className="tag muted">{e.action}</span>}
        </div>
      </div>
      {e.reason && <p className="why tight">{e.reason}</p>}
      {(e.warnings || []).map((w, i) => <p className="warn-line small" key={i}>{w}</p>)}
    </>
  )
}

const BODY = {
  plan: PlanBody,
  search: SearchBody,
  shortlist: ChooseSitesBody,
  scrape: PageBody,
  analyze: AnalyzeBody,
  extract: ExtractBody,
}

/* ------------------------------------------------------------------ step */

function headline(e) {
  switch (e.tool) {
    case 'plan':
      return e.outcome === 'fallback'
        ? 'fallback plan used'
        : plural((e.queries || []).length, 'query', 'queries')
    case 'search': return e.query
    case 'shortlist':
      return e.outcome === 'ok'
        ? `${(e.picked || []).length} of ${e.considered} results`
        : 'selection failed'
    case 'scrape': return (e.url || '').replace(/^https?:\/\//, '')
    case 'analyze': {
      const c = e.candidates || []
      const p = c.filter((x) => x.decision === 'pursue').length
      return c.length ? `${p} to pursue, ${c.length - p} set aside` : 'nothing found'
    }
    case 'extract':
      return e.outcome === 'ok' ? e.record?.title : e.reason
    case 'memory': return e.detail
    default: return e.title || (e.url || '').replace(/^https?:\/\//, '')
  }
}

function Step({ e, followed, expandAll, expandEpoch }) {
  const [override, setOverride] = useState(null)
  useExpandAll(expandEpoch, () => setOverride(null))
  const open = override ?? expandAll
  const Icon = TOOL_ICON[e.tool] || IconDot
  const Body = BODY[e.tool] || SimpleBody
  return (
    <div className={`step tone-${toneOf(e)} s-${e.tool}`}>
      <button className="step-head" type="button" onClick={() => setOverride(!open)}>
        <span className="chev"><IconChevron open={open} /></span>
        <span className="step-icon"><Icon /></span>
        <span className="step-tool">{STEP_NAME[e.tool] || e.tool}</span>
        <span className="step-summary">{headline(e)}</span>
        <span className="spacer" />
        <span className="step-time mono">t+{e.t}s</span>
      </button>
      {open && (
        <div className="step-body">
          <Body e={e} followed={followed} />
          <Raw e={e} />
        </div>
      )}
    </div>
  )
}

/* ------------------------------------------------------------ final output */

function FinalOutput({ run, saved, live }) {
  if (live) {
    return (
      <section className="pass final pending">
        <div className="pass-head static">
          <span className="pass-name">Result</span>
          <span className="small muted">available when the run finishes</span>
          <span className="spacer" /><span className="working-dot" />
        </div>
      </section>
    )
  }
  const c = run.counts || {}
  return (
    <section className="pass final">
      <div className="pass-head static">
        <span className="pass-name">Result</span>
        <span className="spacer" />
        <span className="small muted mono">
          {c.saved ?? 0} ready · {c.needs_deeper ?? 0} need a deeper read ·{' '}
          {c.rejected ?? 0} set aside
        </span>
      </div>
      <div className="pass-body">
        {!saved.length && (
          <p className="muted tight">
            Nothing ready to act on. Set aside shows what was considered and why.
          </p>
        )}
        {saved.map((o) => {
          const e = o.eligibility
          const rows = [
            ...(e?.criteria_results || []).map((r) => ({
              criterion: r.criterion, verdict: r.status, reason: r.reasoning,
            })),
            ...(e?.qualitative_notes || []).map((n) => ({
              criterion: n.criterion, verdict: 'qualitative', reason: n.note,
            })),
          ].sort((a, b) => (VERDICT[a.verdict]?.order ?? 3) - (VERDICT[b.verdict]?.order ?? 3))
          return (
            <div className="final-row" key={o.source_url}>
              <div className="kv">
                <div>
                  <strong>{o.title}</strong>
                  <div className="small muted">{o.organizing_body}</div>
                  <Url href={o.source_url} />
                </div>
                <div className="tags">
                  {o.record_state === 'needs_deeper_read'
                    ? <span className="tag warn">Needs deeper read</span>
                    : <span className="tag ok">Ready</span>}
                  {o.submission_deadline
                    ? <span className="tag ok">closes {o.submission_deadline}</span>
                    : <span className="tag muted">no deadline published</span>}
                  {o.event_date && <span className="tag muted">event {o.event_date}</span>}
                </div>
              </div>
              {rows.length ? (
                <table className="grid">
                  <thead>
                    <tr>
                      <th style={{ width: '40%' }}>Condition</th>
                      <th style={{ width: 118 }}>Against our profile</th>
                      <th>Reason</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((r, i) => (
                      <tr key={i}>
                        <td>{r.criterion}</td>
                        <td>
                          <span className={`tag ${VERDICT[r.verdict]?.cls || 'muted'}`}>
                            {VERDICT[r.verdict]?.label || r.verdict}
                          </span>
                        </td>
                        <td className="why">{r.reason}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : (
                <p className="warn-line small">
                  No entry conditions were found on the page, so this could not be
                  judged against the profile.
                </p>
              )}
            </div>
          )
        })}
      </div>
    </section>
  )
}

/* ----------------------------------------------------------------- passes */

function groupByNode(events) {
  const passes = []
  events.forEach((e) => {
    const node = e.node || 'other'
    const last = passes[passes.length - 1]
    if (last && last.node === node) last.events.push(e)
    else passes.push({ node, events: [e] })
  })
  return passes
}

/** Followed pages hang off the seed that reached them, not as their own steps. */
function nestPages(events) {
  const followedBy = new Map()
  const hidden = new Set()
  events.forEach((e) => {
    if (e.tool === 'scrape' && (e.depth ?? 0) > 0) hidden.add(e.seq)
  })
  let currentSeed = null
  events.forEach((e) => {
    if (e.tool !== 'scrape') return
    if ((e.depth ?? 0) === 0) { currentSeed = e.seq; followedBy.set(currentSeed, []) }
    else if (currentSeed != null) followedBy.get(currentSeed).push(e)
  })
  return {
    // "Follow links" is folded into the page card it belongs to.
    visible: events.filter((e) => !hidden.has(e.seq) && e.tool !== 'select_links'),
    followedBy,
  }
}

function StagePass({ pass, expandAll, expandEpoch, live, isLast }) {
  const [open, setOpen] = useState(isLast)
  useExpandAll(expandEpoch, () => setOpen(expandAll))
  const [title, purpose] = NODE[pass.node] || [pass.node, '']
  const { visible, followedBy } = useMemo(() => nestPages(pass.events), [pass.events])
  const problems = pass.events.filter((e) => toneOf(e) === 'bad').length
  const end = pass.nextStart ?? pass.events[pass.events.length - 1].t
  const span = Math.max(0, end - pass.events[0].t)

  return (
    <section className={`pass${problems ? ' has-problems' : ''}${live && isLast ? ' active' : ''}`}>
      <button className="pass-head" type="button" onClick={() => setOpen((v) => !v)}>
        <span className="chev"><IconChevron open={open} /></span>
        <span className="pass-name">{title}</span>
        <span className="pill muted">stage {(pass.ordinal ?? 0) + 1}</span>
        <span className="small muted">{plural(visible.length, 'step', 'steps')}</span>
        {problems > 0 && <span className="tag bad">{problems} problem</span>}
        <span className="spacer" />
        <span className="small muted mono">{span.toFixed(1)}s</span>
      </button>
      {open && (
        <div className="pass-body">
          <p className="pass-purpose small muted">{purpose}</p>
          <div className="steps">
            {visible.map((e) => (
              <Step key={e.seq} e={e} followed={followedBy.get(e.seq) || []}
                    expandAll={expandAll} expandEpoch={expandEpoch} />
            ))}
            {live && isLast && (
              <div className="step working">
                <span className="working-dot" />
                <span className="small muted">working…</span>
              </div>
            )}
          </div>
        </div>
      )}
    </section>
  )
}

export default function Journey({ run, events = [], saved = [], live = false }) {
  const [expand, setExpand] = useState({ on: false, epoch: 0 })
  const [failuresOnly, setFailuresOnly] = useState(false)

  const passes = useMemo(() => {
    const all = groupByNode(events)
    all.forEach((p, i) => {
      p.ordinal = i
      p.nextStart = all[i + 1]?.events[0]?.t
    })
    if (!failuresOnly) return all
    return all
      .map((p) => ({ ...p, events: p.events.filter((e) => toneOf(e) === 'bad') }))
      .filter((p) => p.events.length)
  }, [events, failuresOnly])

  if (!events.length) return <p className="muted tight">No steps recorded yet.</p>

  return (
    <>
      <div className="journey-bar">
        <span className="small muted">{plural(events.length, 'step', 'steps')}</span>
        {live && <span className="live-tag"><span className="live-dot" />live</span>}
        <span className="spacer" />
        <label className="small muted check">
          <input type="checkbox" checked={failuresOnly}
                 onChange={(ev) => setFailuresOnly(ev.target.checked)} />
          Problems only
        </label>
        <button className="ghost xs" type="button"
                onClick={() => setExpand((s) => ({ on: !s.on, epoch: s.epoch + 1 }))}>
          {expand.on ? 'Collapse all' : 'Expand all'}
        </button>
      </div>

      {passes.map((pass, i) => (
        <StagePass key={`${pass.node}-${pass.ordinal}`} pass={pass}
                   expandAll={expand.on} expandEpoch={expand.epoch}
                   live={live} isLast={i === passes.length - 1} />
      ))}
      {!passes.length && <p className="muted tight">No problem steps in this run.</p>}

      <FinalOutput run={run} saved={saved} live={live} />

      {run.trace_url && (
        <p className="small" style={{ marginTop: 12 }}>
          <a href={run.trace_url} target="_blank" rel="noreferrer">
            Prompts, responses and token counts in Langfuse <IconExternal />
          </a>
        </p>
      )}
    </>
  )
}
