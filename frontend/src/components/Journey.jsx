import { useEffect, useMemo, useRef, useState } from 'react'
import { IconChevron, IconDot, IconExternal, IconSave, TOOL_ICON } from '../icons.jsx'

/** Re-sync local open/closed state when Expand all / Collapse all is pressed. */
function useExpandAll(epoch, apply) {
  const seen = useRef(epoch)
  useEffect(() => {
    if (seen.current !== epoch) { seen.current = epoch; apply() }
  })
}

const BAD = new Set(['failed', 'insufficient'])
const WARN = new Set(['fallback', 'skipped', 'no_new_evidence', 'partial', 'historical', 'reject'])

const toneOf = (e) => (BAD.has(e.outcome) ? 'bad' : WARN.has(e.outcome) ? 'warn' : 'ok')
const plural = (n, one, many) => `${n} ${n === 1 ? one : many}`

const NODE_TITLE = {
  plan: 'Plan queries',
  research: 'Research',
  analyze: 'Analyze',
  finalize: 'Finalize',
}

const NODE_PURPOSE = {
  plan: 'Reads the business profile and writes the search plan for this run.',
  research: 'Runs each query, picks which results are worth fetching, then fetches those pages and the links it judges most likely to state entry rules.',
  analyze: 'Reads each site’s evidence and decides which opportunities on it are worth pursuing.',
  finalize: 'Extracts a structured record, checks it is still actionable, and stores it.',
}

/** The one line shown on a collapsed card. */
function summaryOf(e) {
  switch (e.tool) {
    case 'plan':
      return e.outcome === 'fallback'
        ? 'planner failed — deterministic fallback plan used'
        : plural((e.queries || []).length, 'query planned', 'queries planned')
    case 'search':
      return e.query
    case 'shortlist':
      return e.outcome === 'ok'
        ? `${(e.picked || []).length} of ${e.considered} results chosen to research`
        : `shortlist failed — fell back to search-engine order (${e.considered} hits)`
    case 'select_links':
      return e.outcome === 'ok'
        ? `${(e.picked || []).length} of ${e.considered} links followed`
        : 'link selection failed — followed nothing'
    case 'scrape':
      if (e.outcome === 'ok') return `${(e.chars ?? 0).toLocaleString()} chars · depth ${e.depth ?? 0}`
      if (e.outcome === 'insufficient') return 'too little content — treated as a failed fetch'
      return 'could not fetch'
    case 'analyze': {
      const c = e.candidates || []
      const pursue = c.filter((x) => x.decision === 'pursue').length
      return c.length
        ? `${pursue} to pursue · ${c.length - pursue} skipped`
        : e.outcome === 'no_new_evidence' ? 'no new evidence to analyse' : e.outcome
    }
    case 'extract':
      return e.outcome === 'ok' ? e.record?.title || e.url : `${e.reason} — ${e.url}`
    case 'actionability':
      return `${e.outcome} — ${e.title || e.url}`
    case 'skip':
      return e.title || e.url
    case 'save_opportunity':
      return `${e.action} — ${e.title}`
    default:
      return e.url || e.query || e.outcome || ''
  }
}

/** What the run was trying to achieve with this step, independent of its result. */
const INTENT = {
  plan: 'Turn the business profile into search queries covering different fields, years and kinds of recognition.',
  search: 'Ask Tavily for pages matching one planned query.',
  shortlist: 'Decide which results belong to an organisation that runs a programme, rather than one writing about someone else’s.',
  select_links: 'From the fetched page, follow only links likely to state who can enter.',
  scrape: 'Fetch the page as markdown so it can be read.',
  analyze: 'Identify the distinct opportunities on this site and decide pursue or skip.',
  extract: 'Build one structured record from the evidence, or fail with a named reason.',
  actionability: 'Check by date and HTTP status whether this is still worth acting on.',
  skip: 'Record a candidate the analyser decided against.',
  save_opportunity: 'Upsert the record on its identity key.',
}

const Url = ({ href }) => (
  <a className="u mono" href={href} target="_blank" rel="noreferrer">{href}</a>
)

/** The model's stated reasoning, given its own visual weight. */
const Why = ({ children, label = 'Reasoning' }) =>
  children ? (
    <div className="why-block">
      <span className="why-label">{label}</span>
      <div>{children}</div>
    </div>
  ) : null

const RawEvent = ({ e }) => (
  <details className="raw">
    <summary className="small muted">Raw event — every field exactly as recorded</summary>
    <pre className="mono small">{JSON.stringify(e, null, 2)}</pre>
  </details>
)

function StepBody({ e }) {
  switch (e.tool) {
    case 'plan':
      return (
        <>
          {e.outcome === 'fallback' && (
            <p className="err small tight">
              The planner model call failed, so the deterministic fallback plan ran instead.
              {e.detail ? ` ${e.detail}` : ''}
            </p>
          )}
          {(e.queries || []).map((q, i) => (
            <div className="qrow" key={i}>
              <div className="mono">{q.query}</div>
              <div className="row small muted" style={{ marginTop: 3 }}>
                {q.intent && <span className="pill muted">{q.intent}</span>}
                {q.geography && <span className="pill muted">{q.geography}</span>}
                {q.target_year != null && <span className="pill muted">{q.target_year}</span>}
              </div>
              <Why>{q.rationale}</Why>
            </div>
          ))}
        </>
      )

    case 'search':
      return (
        <>
          <div className="row small muted">
            {e.round && <span className="pill muted">round: {e.round}</span>}
            {e.geography && <span className="pill muted">{e.geography}</span>}
            <span className="pill muted">{plural((e.results || []).length, 'result', 'results')}</span>
          </div>
          <Why label="Why this query">{e.rationale}</Why>
          {e.detail && <div className="small err reason">{e.detail}</div>}
          <div className="results">
            {(e.results || []).map((r) => (
              <a className="result" key={r.url} href={r.url} target="_blank" rel="noreferrer">
                <div className="rt">{r.title}</div>
                <div className="u">{r.url}</div>
                {r.snippet && <div className="small muted snip">{r.snippet}</div>}
              </a>
            ))}
            {!(e.results || []).length && (
              <p className="small muted tight">This query returned nothing.</p>
            )}
          </div>
        </>
      )

    case 'shortlist':
      return (
        <>
          <p className="small muted tight">
            {e.considered} result(s) considered, {(e.picked || []).length} chosen.
          </p>
          {(e.picked || []).map((p, i) => (
            <div className="qrow" key={i}>
              <strong>{p.title}</strong>
              <Url href={p.url} />
              <Why label="Why chosen">{p.reason}</Why>
            </div>
          ))}
          {e.detail && <div className="small err reason">{e.detail}</div>}
        </>
      )

    case 'select_links':
      return (
        <>
          <span className="small muted">Links on </span><Url href={e.url} />
          <Why label="Why these links">{e.reason}</Why>
          {!!(e.picked || []).length && <div className="section-label">Followed</div>}
          {(e.picked || []).map((u, i) => <div className="u mono small" key={i}>{u}</div>)}
          {!(e.picked || []).length && (
            <p className="small muted tight">
              Nothing followed — the seed page alone is used as evidence.
            </p>
          )}
          {e.detail && <div className="small err reason">{e.detail}</div>}
        </>
      )

    case 'scrape':
      return (
        <>
          <Url href={e.url} />
          <div className="row small muted" style={{ marginTop: 6 }}>
            {e.status_code != null && (
              <span className={`pill ${e.status_code >= 200 && e.status_code < 300 ? 'muted' : 'not_met'}`}>
                HTTP {e.status_code}
              </span>
            )}
            {e.depth != null && (
              <span className="pill muted">
                {e.depth === 0 ? 'seed page' : `followed link, depth ${e.depth}`}
              </span>
            )}
            {e.bare_domain && <span className="pill unclear">site homepage</span>}
            {e.links_found != null && (
              <span className="pill muted">{e.links_found} links on page</span>
            )}
          </div>
          {(e.page_title || e.page_description) && (
            <div className="qrow">
              {e.page_title && <div><strong>{e.page_title}</strong></div>}
              {e.page_description && (
                <div className="small muted">{e.page_description}</div>
              )}
              <div className="small muted reason">
                Page metadata is passed to extraction as evidence — some sites render
                their name only as a logo image.
              </div>
            </div>
          )}
          {e.preview && (
            <details className="raw">
              <summary className="small muted">
                Fetched content — what the model actually read
                {e.truncated
                  ? ` (first 20,000 of ${(e.chars ?? 0).toLocaleString()} chars)`
                  : ` (${(e.chars ?? 0).toLocaleString()} chars, complete)`}
              </summary>
              <pre className="mono small scraped">{e.preview}</pre>
            </details>
          )}
          {e.detail && <Why label="Failure">{e.detail}</Why>}
        </>
      )

    case 'analyze':
      return (
        <>
          {(e.candidates || []).map((c, i) => (
            <div className="qrow" key={i}>
              <div className="row">
                <span className={`pill ${c.decision === 'pursue' ? 'met' : 'muted'}`}>
                  {c.decision}
                </span>
                <strong>{c.title}</strong>
                {c.category && <span className="pill muted">{c.category}</span>}
              </div>
              <Url href={c.url} />
              <Why label={c.decision === 'pursue' ? 'Why pursue' : 'Why skip'}>{c.reason}</Why>
              {!!(c.supporting_urls || []).length && (
                <>
                  <div className="section-label">Evidence pages used</div>
                  {c.supporting_urls.map((u, j) => (
                    <div className="u mono small" key={j}>{u}</div>
                  ))}
                </>
              )}
              {!!(c.entry_eligibility || []).length && (
                <>
                  <div className="section-label">
                    Entry eligibility read from the page ({c.entry_eligibility.length})
                  </div>
                  <ul className="plain small">
                    {c.entry_eligibility.map((x, j) => <li key={j}>{x}</li>)}
                  </ul>
                </>
              )}
              {!!(c.judging_criteria || []).length && (
                <>
                  <div className="section-label">Judged on</div>
                  <ul className="plain small">
                    {c.judging_criteria.map((x, j) => <li key={j}>{x}</li>)}
                  </ul>
                </>
              )}
              {!!(c.application_requirements || []).length && (
                <>
                  <div className="section-label">Must submit</div>
                  <ul className="plain small">
                    {c.application_requirements.map((x, j) => <li key={j}>{x}</li>)}
                  </ul>
                </>
              )}
            </div>
          ))}
          {(e.errors || []).map((x, i) => (
            <Why key={i} label="Analysis error">{`${x.seed_url}: ${x.detail}`}</Why>
          ))}
        </>
      )

    case 'extract': {
      if (e.outcome !== 'ok') {
        return (
          <>
            <Url href={e.url} />
            <div style={{ marginTop: 6 }}><span className="pill not_met">{e.reason}</span></div>
            <Why label="What went wrong">{e.detail}</Why>
          </>
        )
      }
      const r = e.record || {}
      return (
        <>
          <Url href={e.url} />
          <div className="row small muted" style={{ marginTop: 6 }}>
            <span>{r.organizing_body}</span>
            <span className="pill muted">{r.category}</span>
            <span className="pill muted">cycle {r.cycle_year}</span>
            <span className={`pill ${r.deadline_verified ? 'met' : 'unclear'}`}>
              {r.submission_deadline || 'no deadline'}
              {r.submission_deadline && (r.deadline_verified ? ' grounded in page' : ' NOT grounded')}
            </span>
            {r.event_date && <span className="pill muted">event {r.event_date}</span>}
          </div>
          {r.base_title && (
            <p className="small muted reason">
              Identity key uses base title <code>{r.base_title}</code>, cycle {r.cycle_year}.
            </p>
          )}
          {r.deadline_note && <Why label="Deadline note">{r.deadline_note}</Why>}
          <Why label="Model's own uncertainty">{r.confidence_note}</Why>
          {!!(r.criteria || []).length && (
            <>
              <div className="section-label">
                Eligibility conditions extracted ({r.criteria.length})
              </div>
              <ul className="plain small">
                {r.criteria.map((c, i) => <li key={i}>{c}</li>)}
              </ul>
            </>
          )}
          <Completeness c={e.completeness} />
        </>
      )
    }

    case 'actionability':
    case 'skip':
      return (
        <>
          <Url href={e.url} />
          <Why label={e.tool === 'skip' ? 'Why skipped' : 'Why this verdict'}>{e.reason}</Why>
        </>
      )

    case 'save_opportunity':
      return (
        <>
          <Url href={e.url} />
          <p className="small muted reason">
            Record <strong>{e.action}</strong> on its identity key.
          </p>
          {(e.warnings || []).map((w, i) => (
            <Why key={i} label="Caveat on this record">{w}</Why>
          ))}
          <Completeness c={e.completeness} />
        </>
      )

    default:
      return null
  }
}

function Completeness({ c }) {
  if (!c) return null
  const checks = [
    ['identity', c.identity], ['open state', c.open_state], ['deadline', c.deadline],
    ['eligibility', c.eligibility], ['source coverage', c.source_coverage],
  ]
  return (
    <>
      <div className="section-label">
        Extraction completeness — {Math.round((c.score || 0) * 100)}%
      </div>
      <div className="row">
        {checks.map(([label, ok]) => (
          <span key={label} className={`pill ${ok ? 'met' : 'not_met'}`}>{label}</span>
        ))}
      </div>
    </>
  )
}

function Step({ e, duration, expandAll, expandEpoch, animate }) {
  const [override, setOverride] = useState(null)
  // A step the user has clicked keeps its own state until the next global
  // toggle, which clears the override so Expand all reaches it too.
  useExpandAll(expandEpoch, () => setOverride(null))
  const open = override ?? expandAll
  const Icon = TOOL_ICON[e.tool] || IconDot
  return (
    <div className={`step tone-${toneOf(e)}${animate ? ' animate' : ''}`}>
      <button className="step-head" onClick={() => setOverride(!open)} type="button">
        <span className="chev"><IconChevron open={open} /></span>
        <span className={`step-icon ${e.tool}`}><Icon /></span>
        <span className="step-tool">{e.tool}</span>
        <span className="step-summary">{summaryOf(e)}</span>
        <span className="spacer" />
        {duration != null && duration >= 0.1 && (
          <span className="step-dur mono">{duration.toFixed(1)}s</span>
        )}
        <span className="step-time mono">t+{e.t}s</span>
      </button>
      {open && (
        <div className="step-body">
          <p className="intent small">{INTENT[e.tool] || ''}</p>
          <StepBody e={e} />
          <RawEvent e={e} />
        </div>
      )}
    </div>
  )
}

/** Consecutive events sharing a graph node become one pass through that node. */
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

function StagePass({ pass, index, total, elapsed, expandAll, expandEpoch, live, isLast }) {
  const [open, setOpen] = useState(index === total - 1)
  // Expand all must open the stage too — steps inside a collapsed stage are
  // not rendered at all, which is why it previously looked like a no-op.
  useExpandAll(expandEpoch, () => setOpen(expandAll))
  const first = pass.events[0]
  const last = pass.events[pass.events.length - 1]
  const end = pass.nextStart ?? elapsed ?? last.t
  const span = Math.max(0, end - first.t)
  const problems = pass.events.filter((e) => toneOf(e) !== 'ok').length

  const active = live && isLast
  const hidden = (pass.stepCount ?? pass.events.length) - pass.events.length
  return (
    <section className={`pass${problems ? ' has-problems' : ''}${active ? ' active' : ''}`}>
      <button className="pass-head" type="button" onClick={() => setOpen((v) => !v)}>
        <span className="chev"><IconChevron open={open} /></span>
        <span className="pass-name">{NODE_TITLE[pass.node] || pass.node}</span>
        {/* Execution order, always shown: a re-planned run visits plan and
            research twice, and the numbers make that visible. */}
        <span className="pill muted">stage {(pass.ordinal ?? index) + 1}</span>
        <span className="small muted">
          {hidden > 0
            ? `${pass.events.length} of ${pass.stepCount} steps`
            : plural(pass.events.length, 'step', 'steps')}
        </span>
        {problems > 0 && <span className="pill not_met">{problems} problem</span>}
        <span className="spacer" />
        <span className="small muted mono">{span.toFixed(1)}s</span>
      </button>
      {open && (
        <div className="pass-body">
          <p className="pass-purpose small muted">{NODE_PURPOSE[pass.node]}</p>
          <div className="steps">
            {pass.events.map((e, i) => (
              <Step
                key={e.seq}
                e={e}
                expandAll={expandAll}
                expandEpoch={expandEpoch}
                animate={live}
                duration={(pass.events[i + 1]?.t ?? end) - e.t}
              />
            ))}
            {/* A step is only recorded once it finishes, so what is running now
                is genuinely unknown — say that rather than guess. */}
            {active && (
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

/** The closing step: what the run actually produced, once everything is done. */
function FinalOutput({ run, saved, live }) {
  const counts = run.counts || {}
  if (live) {
    return (
      <section className="pass final pending">
        <div className="pass-head static">
          <span className="step-icon"><IconSave /></span>
          <span className="pass-name">Final output</span>
          <span className="small muted">available when the run finishes</span>
          <span className="spacer" />
          <span className="working-dot" />
        </div>
      </section>
    )
  }

  const ok = run.status !== 'failed'
  return (
    <section className={`pass final${ok ? '' : ' has-problems'}`}>
      <div className="pass-head static">
        <span className="step-icon"><IconSave /></span>
        <span className="pass-name">Final output</span>
        <span className={`pill ${ok ? 'met' : 'not_met'}`}>
          {ok ? 'run succeeded' : 'run failed'}
        </span>
        <span className="spacer" />
        <span className="small muted mono">
          {counts.saved ?? 0} stored · {counts.rejected ?? 0} set aside ·{' '}
          {counts.failed ?? 0} failures
        </span>
      </div>
      <div className="pass-body">
        {saved.length ? (
          <>
            <p className="pass-purpose small muted">
              Stored in the <code>opportunities</code> collection and judged against the
              business profile. This is the run&rsquo;s product.
            </p>
            {saved.map((o) => {
              const e = o.eligibility
              const met = (e?.criteria_results || []).filter((r) => r.status === 'met').length
              const notMet = (e?.criteria_results || []).filter((r) => r.status === 'not_met').length
              const judge = (e?.criteria_results || []).filter((r) => r.status === 'unclear').length
                + (e?.qualitative_notes || []).length
              return (
                <div className="final-row" key={o.source_url}>
                  <div className="row">
                    <strong>{o.title}</strong>
                    <span className="pill muted">{o.category}</span>
                    <span className={`pill ${o.submission_deadline ? 'met' : 'muted'}`}>
                      {o.submission_deadline || 'no date confirmed'}
                    </span>
                  </div>
                  <div className="small muted">{o.organizing_body}</div>
                  <a className="u mono" href={o.source_url} target="_blank" rel="noreferrer">
                    {o.source_url}
                  </a>
                  {e ? (
                    <div className="row small" style={{ marginTop: 5 }}>
                      <span className="pill met">{met} met</span>
                      <span className="pill not_met">{notMet} not met</span>
                      <span className="pill unclear">{judge} your call</span>
                    </div>
                  ) : (
                    <div className="small muted reason">
                      Not evaluated — no usable eligibility conditions were extracted.
                    </div>
                  )}
                </div>
              )
            })}
          </>
        ) : (
          <p className="muted tight">
            This run stored nothing. The steps above show where it stopped —
            check Set aside for pages it considered and rejected.
          </p>
        )}
        {run.summary && <p className="small muted reason">{run.summary}</p>}
      </div>
    </section>
  )
}

export default function Journey({ run, events = [], saved = [], live = false }) {
  const [expand, setExpand] = useState({ on: false, epoch: 0 })
  const [failuresOnly, setFailuresOnly] = useState(false)
  const [grouped, setGrouped] = useState(true)
  const expandAll = expand.on
  const setExpandAll = () => setExpand((s) => ({ on: !s.on, epoch: s.epoch + 1 }))
  const elapsed = run?.budget?.elapsed

  const shown = useMemo(
    () => (failuresOnly ? events.filter((e) => toneOf(e) !== 'ok') : events),
    [events, failuresOnly],
  )

  // Group the FULL journey first, then filter inside each pass. Filtering before
  // grouping let two separate visits to a node become adjacent and merge into
  // one pass — a re-planned run showed a single "research" pass whose span
  // included the analyze and plan time that actually sat between them.
  const passes = useMemo(() => {
    const all = groupByNode(events)
    all.forEach((p, i) => {
      p.ordinal = i                            // true position in the run
      p.stepCount = p.events.length            // before any filtering
      p.nextStart = all[i + 1]?.events[0]?.t   // true span boundary
    })
    if (!failuresOnly) return all
    return all
      .map((p) => ({ ...p, events: p.events.filter((e) => toneOf(e) !== 'ok') }))
      .filter((p) => p.events.length)
  }, [events, failuresOnly])

  if (!events.length) {
    return <p className="muted tight">No steps recorded yet.</p>
  }

  return (
    <>
      <div className="journey-bar">
        <span className="small muted">
          {plural(events.length, 'step', 'steps')} across {plural(passes.length, 'pass', 'passes')}
        </span>
        {live && <span className="live-tag"><span className="live-dot" />live</span>}
        <span className="spacer" />
        <label className="small muted check">
          <input type="checkbox" checked={grouped}
                 onChange={(ev) => setGrouped(ev.target.checked)} />
          Group by stage
        </label>
        <label className="small muted check">
          <input type="checkbox" checked={failuresOnly}
                 onChange={(ev) => setFailuresOnly(ev.target.checked)} />
          Problems only
        </label>
        <button className="ghost xs" type="button" onClick={setExpandAll}>
          {expandAll ? 'Collapse all' : 'Expand all'}
        </button>
      </div>

      {!!(run.thinking || []).length && (
        <details className="reasoning" open>
          <summary>
            Planner reasoning — the query plan and why each query was written
            ({run.thinking.length})
          </summary>
          {run.thinking.map((t, i) => <p key={i} className="small">{t}</p>)}
        </details>
      )}

      {!!(run.queries || []).length && (
        <details className="reasoning">
          <summary>Caller-supplied queries ({run.queries.length})</summary>
          <p className="small muted">
            These were given directly, so the planner did not write the plan and the
            re-plan step is disabled.
          </p>
          {run.queries.map((q, i) => <p key={i} className="small mono">{q}</p>)}
        </details>
      )}

      {!shown.length && <p className="muted tight">No problem steps in this run.</p>}

      {grouped ? (
        passes.map((pass, i) => (
          <StagePass key={`${pass.node}-${i}`} pass={pass} index={i} total={passes.length}
                     elapsed={elapsed} expandAll={expandAll} expandEpoch={expand.epoch}
                     live={live} isLast={i === passes.length - 1} />
        ))
      ) : (
        <div className="steps">
          {shown.map((e, i) => (
            <Step key={e.seq} e={e} expandAll={expandAll} expandEpoch={expand.epoch}
                  animate={live}
                  duration={(shown[i + 1]?.t ?? elapsed ?? e.t) - e.t} />
          ))}
          {live && (
            <div className="step working">
              <span className="working-dot" />
              <span className="small muted">working…</span>
            </div>
          )}
        </div>
      )}

      <FinalOutput run={run} saved={saved} live={live} />

      {!!(run.warnings || []).length && (
        <details className="reasoning" style={{ marginTop: 14 }} open>
          <summary>
            Caveats on what was stored ({run.warnings.length}) — records kept, but read these
          </summary>
          {run.warnings.map((w, i) => <p key={i} className="small">{w}</p>)}
        </details>
      )}

      {!!(run.failures || []).length && (
        <details className="reasoning" style={{ marginTop: 14 }}>
          <summary className="err">Failures during the run ({run.failures.length})</summary>
          {run.failures.map((f, i) => <p key={i} className="small">{f}</p>)}
        </details>
      )}

      {!!(run.eligibility_failures || []).length && (
        <details className="reasoning" style={{ marginTop: 14 }}>
          <summary>
            Records eligibility could not judge ({run.eligibility_failures.length})
          </summary>
          {run.eligibility_failures.map((f, i) => (
            <p key={i} className="small">
              <span className="mono">{f.source_url}</span> — {f.reason}
            </p>
          ))}
        </details>
      )}

      {run.summary && (
        <details className="reasoning" style={{ marginTop: 14 }} open>
          <summary>Run summary</summary>
          <p className="small">{run.summary}</p>
        </details>
      )}

      {run.trace_url && (
        <p className="small" style={{ marginTop: 12 }}>
          <a href={run.trace_url} target="_blank" rel="noreferrer">
            Full prompts, responses and token counts in Langfuse <IconExternal />
          </a>
        </p>
      )}
    </>
  )
}
