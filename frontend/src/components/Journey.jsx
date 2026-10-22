import { useEffect, useMemo, useRef, useState } from 'react'
import { outcome as outcomeOf, VERDICT } from '../api.js'
import { IconChevron, IconDot, IconExternal, TOOL_ICON } from '../icons.jsx'
import Opportunity, { FitTable } from './Opportunity.jsx'
import { Digest } from './Signals.jsx'

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
  plan: ['Plan', 'Writes search queries from the business profile.'],
  search: ['Search', 'Runs each query and keeps one copy of each page.'],
  rank: ['Rank', 'Orders the search results and chooses which sites to read.'],
  fetch: ['Fetch', 'Reads each chosen site, following a few links on it.'],
  extract: ['Extract', 'Names the opportunities on each site and builds a record for each one pursued.'],
  evaluate: ['Evaluate', 'Judges each record against the business profile, condition by condition.'],
  store: ['Store', 'Saves the records.'],
}

// A competitor-watch run's steps, worded for what they do there.
const WATCH_NODE = {
  plan: ['Plan', 'Writes the market searches from the business profile.'],
  search: ['Search', "Searches each competitor's site, the market and each competitor's name for pages published since the last run, then skips pages judged before."],
  evaluate: ['Judge', 'Decides which new pages report something that happened, who it concerns and how much it matters, and links follow-ups to known stories.'],
}

// Shown inside the step they belong to, not as steps of their own.
const DROP = new Set(['dedupe', 'expired'])
const RECORD = new Set(['extract', 'actionability', 'grounding'])

const STEP_NAME = {
  plan: 'Plan',
  search: 'Search',
  shortlist: 'Choose sites',
  select_links: 'Follow links',
  scrape: 'Read page',
  memory: 'Memory',
  analyze: 'Analyze',
  extract: 'Build record',
  grounding: 'Check quotes',
  dedupe: 'Drop duplicate',
  expired: 'Drop closed',
  actionability: 'Check if live',
  feasibility: 'Judge conditions',
  fit: 'Judge fit',
  seen: 'Skip seen pages',
  judge: 'Judge signals',
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
      {e.assessment && (
        <div className="why-block">
          <span className="why-label">Assessment of the searches so far</span>
          <div>{e.assessment}</div>
        </div>
      )}
      {!!(e.gaps || []).length && (
        <p className="small tight">Still missing: {e.gaps.join(' · ')}</p>
      )}
      {e.outcome === 'stop' && <p className="small muted tight">No further search: the results cover what is needed.</p>}
      {e.outcome === 'repeat' && <p className="small muted tight">Stopped: the proposed search repeated one already run.</p>}
      {e.outcome === 'failed' && e.detail && <p className="err small tight">{e.detail}</p>}
      {!!(e.queries || []).length && <table className="grid">
        <thead><tr><th style={{ width: '38%' }}>Query</th>{(e.queries || []).some((q) => q.track) && <th style={{ width: 80 }}>Track</th>}<th>Why</th></tr></thead>
        <tbody>
          {(e.queries || []).map((q, i) => (
            <tr key={i}>
              <td className="mono">{q.query}</td>
              {(e.queries || []).some((x) => x.track) && <td><span className="tag muted">{q.track}</span></td>}
              <td className="why">{q.rationale}</td>
            </tr>
          ))}
        </tbody>
      </table>}
    </>
  )
}

function SearchBody({ e, followed = [] }) {
  const rows = e.results || []
  const [open, setOpen] = useState(null)
  const types = Object.entries(e.types || {})
  return (
    <>
      {e.rationale && <p className="why small tight">{e.rationale}</p>}
      {e.detail && <p className="err small tight">{e.detail}</p>}
      {!!types.length && (
        <p className="small muted tight">
          Exa type labels: {types.map(([t, n]) => `${t} ${n}`).join(' · ')}
          {e.on_type != null && ` — ${e.on_type} of ${rows.length} match this run's type`}
          {!!e.unreadable_summaries && <span className="err"> · {e.unreadable_summaries} summary not readable</span>}
        </p>
      )}
      {!rows.length && <p className="muted small tight">No results.</p>}
      {!!rows.length && (
        <table className="grid">
          <thead><tr><th style={{ width: '28%' }}>Title</th><th style={{ width: 200 }}>Link</th>
            {e.lane ? <th>Published</th> : <><th style={{ width: 90 }}>Type</th><th>Snippet</th></>}</tr></thead>
          <tbody>
            {rows.map((r) => [
              <tr key={r.url} className="clickable" onClick={() => setOpen(open === r.url ? null : r.url)}>
                <td>{r.title}</td>
                <td><Url href={r.url}>{r.url.replace(/^https?:\/\//, '').slice(0, 42)}</Url></td>
                {e.lane ? <td className="small muted">{r.published_date || 'undated'}</td> : <>
                  <td>{r.opportunity_type ? <span className="tag muted">{r.opportunity_type}</span> : <span className="muted small">—</span>}</td>
                  <td className="why clamp">{r.snippet}</td>
                </>}
              </tr>,
              open === r.url && (
                <tr key={`${r.url}-detail`}>
                  <td colSpan={4}>
                    {r.ranker_view
                      ? <><p className="small muted tight">What the ranker read for this result</p><pre className="mono small scraped">{r.ranker_view}</pre></>
                      : <p className="small muted tight">Not recorded for this run.</p>}
                    {r.summary_raw && (
                      <details className="raw">
                        <summary className="small muted">Exa summary as returned ({r.summary_status})</summary>
                        <pre className="mono small scraped">{r.summary_raw}</pre>
                      </details>
                    )}
                  </td>
                </tr>
              ),
            ])}
          </tbody>
        </table>
      )}
      {!!followed.length && (
        <div className="nested">
          <div className="nested-label">{plural(followed.length, 'result dropped', 'results dropped')}</div>
          {followed.map((d) => (
            <div className="nested-item small" key={d.seq}>
              {d.title} <Url href={d.url}>{(d.url || '').replace(/^https?:\/\//, '').slice(0, 60)}</Url>
              <span className="muted"> — {headline(d)}</span>
            </div>
          ))}
        </div>
      )}
    </>
  )
}

function ChooseSitesBody({ e }) {
  if (e.outcome !== 'ok') {
    return <p className="err small tight">{e.detail || 'Ranking failed; the run stopped.'}</p>
  }
  const ranked = e.picked || []
  if (!ranked.length) {
    return (
      <p className="small tight">
        Nothing in {e.considered} results was worth fetching. The run searches
        again rather than spending scrapes on the least-bad result.
      </p>
    )
  }
  // The whole ranking, not only what was fetched. Seeing the near-misses just
  // below the cut is the point: whether the good programme sat one place too
  // low used to be unanswerable.
  return (
    <>
      {e.observation && <p className="why small tight">{e.observation}</p>}
      <table className="grid">
        <thead>
          <tr>
            <th style={{ width: 34 }}>#</th>
            <th style={{ width: '32%' }}>Site</th>
            <th style={{ width: 200 }}>Link</th>
            <th>Why ranked here</th>
          </tr>
        </thead>
        <tbody>
          {ranked.map((p, i) => (
            <tr key={i} className={p.fetched === false ? 'dim' : undefined}>
              <td className="mono small">
                {p.rank ?? i + 1}
                {p.fetched === false && <span className="muted"> ·</span>}
              </td>
              <td>{p.title}</td>
              <td><Url href={p.url}>{p.url.replace(/^https?:\/\//, '').slice(0, 42)}</Url></td>
              <td className="why">{p.reason}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {ranked.some((p) => p.fetched === false) && (
        <p className="hint small">
          Dimmed rows were ranked but fell outside the scrape budget.
        </p>
      )}
      {!!(e.excluded || []).length && (
        <div className="nested">
          <div className="nested-label">Left out — the ranker's reasons</div>
          {e.excluded.map((x, i) => (
            <div className="nested-item small" key={i}>
              {x.title} <Url href={x.url}>{(x.url || '').replace(/^https?:\/\//, '').slice(0, 60)}</Url>
              <div className="why">{x.reason}</div>
            </div>
          ))}
        </div>
      )}
    </>
  )
}

function LinkChoice({ c }) {
  return (
    <div className="why-block">
      <span className="why-label">Link choice — {c.considered ?? 0} links offered, {(c.picked || []).length} followed</span>
      {c.covered && <div><strong>Page states:</strong> {c.covered}</div>}
      {c.missing && <div><strong>Missing:</strong> {c.missing}</div>}
      {c.reason && <div><strong>Why:</strong> {c.reason}</div>}
      {c.detail && <div className="err">{c.detail}</div>}
    </div>
  )
}

function PageBody({ e, followed }) {
  const choice = followed.find((x) => x.tool === 'select_links')
  const pages = followed.filter((x) => x.tool === 'scrape')
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
          {e.anchors_found != null && <span className="tag muted">{e.anchors_found} links in page HTML</span>}
        </div>
      </div>
      {e.page_title && <div className="pagetitle">{e.page_title}</div>}
      {e.detail && (
        <p className="err small tight">
          {e.source === 'firecrawl' ? 'Firecrawl error: ' : ''}{e.detail}
        </p>
      )}
      {e.preview && (
        <details className="raw">
          <summary className="small muted">
            Page content as read{e.truncated ? ' (first 20,000 chars)' : ''}
          </summary>
          <pre className="mono small scraped">{e.preview}</pre>
        </details>
      )}
      {choice && <LinkChoice c={choice} />}
      {!!pages.length && (
        <div className="nested">
          <div className="nested-label">
            {plural(pages.length, 'page followed from here', 'pages followed from here')}
          </div>
          {pages.map((child) => (
            <div className="nested-item" key={child.seq}>
              <PageBody e={child} followed={[]} />
            </div>
          ))}
        </div>
      )}
    </>
  )
}

const dash = (v) => (v === null || v === undefined || v === '' || v === 0 ? 'not stated' : v)

function List({ title, items }) {
  if (!items?.length) return null
  return (
    <table className="grid tightgrid">
      <thead><tr><th>{title} ({items.length})</th></tr></thead>
      <tbody>{items.map((x, j) => <tr key={j}><td>{x}</td></tr>)}</tbody>
    </table>
  )
}

function RecordLine({ r }) {
  if (r.tool === 'extract') {
    if (r.outcome !== 'ok') return <p className="err small tight">Record not built: {r.reason} {r.detail}</p>
    return <p className="small tight"><span className="tag ok">Record built</span></p>
  }
  if (r.tool === 'actionability') {
    return <p className="warn-line small tight">Set aside ({outcomeOf(r.outcome).label}): {r.reason}</p>
  }
  return (
    <p className="small muted tight">
      Quotes checked on the page: {headline(r)}
      {(r.fields || []).filter((f) => !f.found).map((f) => ` · ${f.field} quote not found`).join('')}
    </p>
  )
}

function Candidate({ c, records }) {
  const research = c.category === 'research'
  const deadline = c.submission_deadline
    ? `${c.submission_deadline}${c.deadline_note ? ` (${c.deadline_note})` : ''}`
    : c.deadline_note || 'not stated'
  const facts = [
    ['Organiser', dash(c.organizing_body)],
    ['Field', dash(c.domain)],
    ['Edition', dash(c.cycle_year)],
    ['Entry deadline', deadline],
    ['Event date', dash(c.event_date)],
    ['Status on the page', dash(c.status)],
  ]
  const quotes = Object.entries(c.quotes || {}).filter(([, q]) => q)
  return (
    <div className="cand">
      <div className="kv">
        <div>
          <strong>{c.title}</strong>
          <Url href={c.url} />
        </div>
        <div className="tags">
          <span className={`tag ${c.decision === 'pursue' ? 'ok' : 'muted'}`}>
            {c.decision === 'pursue' ? 'Pursue' : 'Set aside'}
          </span>
          {c.category && <span className="tag muted">{c.category}</span>}
        </div>
      </div>
      {c.summary && <p className="tight">{c.summary}</p>}
      <table className="grid tightgrid">
        <tbody>
          {facts.map(([k, v]) => (
            <tr key={k}>
              <td className="muted" style={{ width: 150 }}>{k}</td>
              <td className={v === 'not stated' ? 'muted' : undefined}>{v}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="why-block">
        <span className="why-label">{c.decision === 'pursue' ? 'Why pursue' : 'Why set aside'}</span>
        <div>{c.reason}</div>
      </div>
      {records.map((r) => <RecordLine key={r.seq} r={r} />)}
      <List title={research ? 'Scope it asks for' : 'Eligibility conditions'} items={c.entry_eligibility} />
      {!research && !(c.entry_eligibility || []).length && (
        <p className="warn-line small">The pages state no eligibility conditions.</p>
      )}
      <List title="Judged on" items={c.judging_criteria} />
      <List title="What to submit" items={c.application_requirements} />
      {c.confidence_note && (
        <div className="why-block">
          <span className="why-label">Extractor&rsquo;s own uncertainty</span>
          <div>{c.confidence_note}</div>
        </div>
      )}
      {!!quotes.length && (
        <details className="raw">
          <summary className="small muted">Sentences the values were read from</summary>
          {quotes.map(([k, q]) => <p className="small tight" key={k}><strong>{k}:</strong> &ldquo;{q}&rdquo;</p>)}
        </details>
      )}
    </div>
  )
}

function AnalyzeBody({ e, followed = [] }) {
  const cands = e.candidates || []
  return (
    <>
      <Url href={e.url} />
      {e.picked_because && <p className="small muted tight">Chosen because: {e.picked_because}</p>}
      {!cands.length && <p className="muted small tight">No opportunities identified on this site.</p>}
      {cands.map((c, i) => (
        <Candidate key={i} c={c} records={followed.filter((r) => r.url === c.url)} />
      ))}
      {(e.errors || []).map((x, i) => (
        <p className="err small" key={i}>{x.seed_url}: {x.detail}</p>
      ))}
    </>
  )
}

function SkipBody({ e, all = [] }) {
  const firecrawl = e.source ? e.source === 'firecrawl' : !e.chars
  const fetchError = all.find(
    (x) => x.tool === 'scrape' && x.node === 'fetch' && x.url === e.url && x.outcome !== 'ok',
  )
  return (
    <>
      <Url href={e.url} />
      <div className="why-block">
        <span className="why-label">{firecrawl ? 'Firecrawl could not load the page' : 'Our pipeline refused the page'}</span>
        <div>{e.detail}</div>
      </div>
      {fetchError?.detail && <pre className="mono small scraped">{fetchError.detail}</pre>}
    </>
  )
}

function EvaluateBody({ e }) {
  if (e.outcome !== 'ok') return <p className="err small tight">{e.detail}</p>
  const rows = [
    ...(e.criteria_results || []).map((r) => ({ criterion: r.criterion, verdict: r.status, reason: r.reasoning })),
    ...(e.qualitative_notes || []).map((n) => ({ criterion: n.criterion, verdict: 'qualitative', reason: n.note })),
  ]
  return (
    <>
      <Url href={e.url} />
      {!rows.length && <p className="muted small tight">No conditions recorded for this run.</p>}
      {!!rows.length && (
        <table className="grid">
          <thead>
            <tr><th style={{ width: '40%' }}>Condition</th><th style={{ width: 118 }}>Against our profile</th><th>Reason</th></tr>
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
      )}
      {e.confidence && <p className="small muted tight">Confidence: {e.confidence}</p>}
    </>
  )
}

function FitBody({ e }) {
  if (e.outcome !== 'ok') return <p className="err small tight">{e.detail}</p>
  return (
    <>
      <Url href={e.url} />
      <FitTable fit={e} />
    </>
  )
}

function JudgeBody({ e }) {
  if (e.outcome !== 'ok') return <p className="err small tight">{e.detail}</p>
  const kept = e.kept || []
  const excluded = e.excluded || []
  return (
    <>
      {!!kept.length && (
        <table className="grid">
          <thead>
            <tr><th style={{ width: 80 }}>Importance</th><th style={{ width: '22%' }}>About</th><th>Headline</th><th style={{ width: 180 }}>Link</th></tr>
          </thead>
          <tbody>
            {kept.map((k, i) => (
              <tr key={i}>
                <td className="small">{k.merged_into ? 'added to a known story' : k.importance}</td>
                <td>{k.competitor}</td>
                <td>{k.headline}</td>
                <td><Url href={k.url}>{k.url.replace(/^https?:\/\//, '').slice(0, 34)}</Url></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {!!excluded.length && (
        <details className="raw">
          <summary className="small muted">Dropped ({excluded.length}) — the judge's reasons</summary>
          {excluded.map((x, i) => (
            <p key={i} className="small tight"><Url href={x.url}>{x.title || x.url}</Url> — <span className="why">{x.reason}</span></p>
          ))}
        </details>
      )}
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
  feasibility: EvaluateBody,
  fit: FitBody,
  judge: JudgeBody,
}

/* ------------------------------------------------------------------ step */

function headline(e) {
  switch (e.tool) {
    case 'plan':
      if (e.outcome === 'failed') return 'planning failed'
      if (e.outcome === 'short') return `${(e.queries || []).length} of ${e.asked} queries`
      if (e.step) return e.outcome === 'ok' ? `search step ${e.step}: ${e.queries?.[0]?.query || ''}` : `search step ${e.step}: stopped`
      return plural((e.queries || []).length, 'query', 'queries')
    case 'search': {
      const n = (e.results || []).length
      const fit = e.on_type != null ? ` · ${e.on_type} of ${n} on-type` : ''
      return `${e.lane ? `[${e.lane}] ` : ''}${e.query} · ${plural(n, 'result', 'results')}${fit}`
    }
    case 'shortlist': {
      if (e.outcome !== 'ok') return 'selection failed'
      const ranked = e.picked || []
      if (!ranked.length) return `nothing worth fetching in ${e.considered}`
      // "to fetch", not "fetched": this is what the ranking chose, and the
      // fetches happen after. A stopped run showed "5 fetched of 10" with zero
      // scrapes on the meter.
      const taken = ranked.filter((p) => p.fetched !== false).length
      return `${taken} to fetch of ${ranked.length} ranked, from ${e.considered}`
    }
    case 'scrape':
      if (e.node === 'extract') return `${(e.url || '').replace(/^https?:\/\//, '')} — not read, the fetch failed`
      return (e.url || '').replace(/^https?:\/\//, '')
    case 'analyze': {
      const c = e.candidates || []
      const p = c.filter((x) => x.decision === 'pursue').length
      const site = (e.url || '').replace(/^https?:\/\//, '').slice(0, 50)
      return `${site} — ${c.length ? `${p} to pursue, ${c.length - p} set aside` : 'nothing found'}`
    }
    case 'extract':
      return e.outcome === 'ok' ? e.record?.title : e.reason
    case 'expired': return `closed: deadline ${e.entry_deadline || '-'}, event ${e.event_date || '-'}`
    case 'dedupe': return `same page as ${(e.duplicate_of || '').replace(/^https?:\/\//, '')}`
    case 'grounding': {
      const f = e.fields || []
      const found = f.filter((x) => x.found).length
      return f.length ? `${found} of ${f.length} quoted from the page` : 'nothing to check'
    }
    case 'memory': return e.detail
    case 'seen': return e.detail
    case 'judge': {
      if (e.outcome !== 'ok') return 'judging failed'
      const kept = e.kept || []
      return `${kept.length} kept of ${e.considered} new pages · ${kept.filter((k) => k.merged_into).length} added to known stories`
    }
    case 'fit': {
      if (e.outcome !== 'ok') return `${e.title || ''} — fit check failed`
      const works = e.works || []
      return `${e.title || ''} — ${works.filter((w) => w.fit !== 'no').length} of ${works.length} lines of our work fit`
    }
    case 'feasibility': {
      if (e.outcome !== 'ok') return `${e.title || ''} — evaluation failed`
      const n = e.counts || {}
      return `${e.title || ''} — ${n.met ?? 0} met, ${n.not_met ?? 0} not met, ${(n.unclear ?? 0) + (e.qualitative ?? 0)} need review`
    }
    default: return e.title || (e.url || '').replace(/^https?:\/\//, '')
  }
}

function Step({ e, followed, all, expandAll, expandEpoch }) {
  const [override, setOverride] = useState(null)
  useExpandAll(expandEpoch, () => setOverride(null))
  const open = override ?? expandAll
  const Icon = TOOL_ICON[e.tool] || IconDot
  const Body = e.tool === 'scrape' && e.node === 'extract' ? SkipBody : BODY[e.tool] || SimpleBody
  return (
    <div className={`step tone-${toneOf(e)} s-${e.tool}`}>
      <button className="step-head" type="button" onClick={() => setOverride(!open)}>
        <span className="chev"><IconChevron open={open} /></span>
        <span className="step-icon"><Icon /></span>
        <span className="step-tool">
          {e.tool === 'scrape' && e.node === 'extract' ? 'Skip site' : STEP_NAME[e.tool] || e.tool}
        </span>
        <span className="step-summary">{headline(e)}</span>
        <span className="spacer" />
        <span className="step-time mono">t+{e.t}s</span>
      </button>
      {open && (
        <div className="step-body">
          <Body e={e} followed={followed} all={all} />
          <Raw e={e} />
        </div>
      )}
    </div>
  )
}

/* ------------------------------------------------------------ final output */

function FinalOutput({ saved, totals, live, watch, counts = {}, runId }) {
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
  if (watch) {
    return (
      <section className="pass final">
        <div className="pass-head static">
          <span className="pass-name">Result</span>
          <span className="spacer" />
          <span className="small muted mono">
            {counts.signals ?? 0} new signals · {counts.merged ?? 0} added to known stories ·{' '}
            {counts.context ?? 0} low-relevance context · {counts.dropped ?? 0} dropped
          </span>
        </div>
        <div className="pass-body">
          <Digest runId={runId} count={counts.signals} />
        </div>
      </section>
    )
  }
  return (
    <section className="pass final">
      <div className="pass-head static">
        <span className="pass-name">Result</span>
        <span className="spacer" />
        <span className="small muted mono">
          {totals.ready} ready · {totals.needs_deeper} need more evidence ·{' '}
          {totals.set_aside} set aside
        </span>
      </div>
      <div className="pass-body">
        {!saved.length && (
          <p className="muted tight">
            Nothing ready to act on. Set aside shows what was considered and why.
          </p>
        )}
        {saved.map((o) => <Opportunity key={`${o.source_url}-${o.base_title}`} o={o} />)}
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

/** Child events hang off the step they belong to, not as steps of their own. */
function nestPages(events) {
  const followedBy = new Map()
  const hidden = new Set()
  const attach = (parent, child) => {
    if (!followedBy.has(parent)) followedBy.set(parent, [])
    followedBy.get(parent).push(child)
    hidden.add(child.seq)
  }
  // Followed pages: under the seed page that reached them.
  let currentSeed = null
  events.forEach((e) => {
    if (e.tool !== 'scrape' || e.node === 'extract') return
    if ((e.depth ?? 0) === 0) currentSeed = e.seq
    else if (currentSeed != null) attach(currentSeed, e)
  })
  // Dropped results: recorded just before the search they came from.
  let pending = []
  events.forEach((e) => {
    if (DROP.has(e.tool)) pending.push(e)
    else if (e.tool === 'search') { pending.forEach((d) => attach(e.seq, d)); pending = [] }
  })
  // Record steps: under the site whose candidate they belong to.
  events.forEach((e) => {
    if (!RECORD.has(e.tool)) return
    const site = [...events].reverse().find(
      (a) => a.tool === 'analyze' && a.seq < e.seq && (a.candidates || []).some((c) => c.url === e.url),
    )
    if (site) attach(site.seq, e)
  })
  // Link choices: under the page they were made on.
  events.forEach((e) => {
    if (e.tool !== 'select_links') return
    const page = [...events].reverse().find((p) => p.tool === 'scrape' && p.url === e.url && p.seq < e.seq)
    if (page) attach(page.seq, e)
  })
  return {
    // "Follow links" is folded into the page card it belongs to.
    visible: events.filter((e) => !hidden.has(e.seq) && e.tool !== 'select_links'),
    followedBy,
  }
}

function StagePass({ pass, all, expandAll, expandEpoch, live, isLast, nodes = NODE }) {
  const [open, setOpen] = useState(isLast)
  useExpandAll(expandEpoch, () => setOpen(expandAll))
  const [title, purpose] = nodes[pass.node] || NODE[pass.node] || [pass.node, '']
  const { visible, followedBy } = useMemo(() => nestPages(pass.events), [pass.events])
  const problems = pass.events.filter((e) => toneOf(e) === 'bad').length
  const span = Math.max(0, pass.events[pass.events.length - 1].t - (pass.prevEnd ?? 0))

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
              <Step key={e.seq} e={e} followed={followedBy.get(e.seq) || []} all={all}
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

export default function Journey({ run, events = [], saved = [], totals, live = false }) {
  const [expand, setExpand] = useState({ on: false, epoch: 0 })
  const [failuresOnly, setFailuresOnly] = useState(false)

  const focus = run?.budget?.focus
  const passes = useMemo(() => {
    const all = groupByNode(events)
    all.forEach((p, i) => {
      p.ordinal = i
      const prev = all[i - 1]?.events
      p.prevEnd = prev ? prev[prev.length - 1].t : 0
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
        <StagePass key={`${pass.node}-${pass.ordinal}`} pass={pass} all={events}
                   expandAll={expand.on} expandEpoch={expand.epoch}
                   live={live} isLast={i === passes.length - 1}
                   nodes={focus === 'competitors' ? WATCH_NODE : NODE} />
      ))}
      {!passes.length && <p className="muted tight">No problem steps in this run.</p>}

      <FinalOutput saved={saved} totals={totals} live={live} watch={focus === 'competitors'}
                   counts={run?.counts} runId={run?.run_id} />

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
