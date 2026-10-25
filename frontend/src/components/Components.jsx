import { Fragment, useEffect, useMemo, useState } from 'react'
import { api } from '../api.js'

const rupees = (n) => `₹${Math.round(n).toLocaleString('en-IN')}`
const pct = (n) => `${n > 0 ? '+' : ''}${Math.round(n)}%`
const RUPEE = new Set(['INR', '₹', 'RS', 'RS.'])

// How each verdict reads at a glance.
const VERDICT_TAG = {
  'Cheaper seller found': 'ok',
  'Cheaper drop-in found': 'ok',
  'Changes needed to save': 'warn',
  'We pay the lowest found': 'live',
  'No comparable price': 'muted',
  'Could not be judged': 'bad',
  'Nothing found': 'muted',
  'Low spend, not searched this run': 'muted',
  'Custom, not searched': 'muted',
}

/** A component run's decisions, rows and findings, refetched while the run is live. */
function useRun(runId, live, tick) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [epoch, setEpoch] = useState(0)
  useEffect(() => {
    api(`/api/runs/${runId}/components`).then((d) => { setData(d); setError(null) }).catch((e) => setError(e.message))
  }, [runId, live, epoch, tick])
  return [data, error, () => setEpoch((n) => n + 1)]
}

/** The price exactly as the seller lists it. */
function Listed({ o }) {
  if (o.price == null) return <span className="muted">no price shown</span>
  return (
    <>
      {o.currency} {o.price.toLocaleString('en-IN')} per {o.price_unit || 'unit not stated'}
      <div className="muted">GST {o.price_before_gst != null && o.price_before_gst < o.price ? 'included' : o.gst}</div>
      {o.price_before_gst != null && o.price_before_gst !== o.price && (
        <div className="muted">{o.price_before_gst.toLocaleString('en-IN')} before GST</div>
      )}
    </>
  )
}

/** The seller's price per unit (as our BOM counts it) against our rate, or why it was not compared. */
function Compared({ o }) {
  if (o.unit_price == null) {
    if (o.price == null) return <span className="muted">—</span>
    return (
      <span className="muted">
        not compared: {RUPEE.has(o.currency.trim().toUpperCase()) ? `listed per ${o.price_unit || 'an unstated unit'}, not clearly one of our units` : 'not a rupee price'}
      </span>
    )
  }
  return (
    <>
      {rupees(o.unit_price)} per unit
      <div className={o.diff_pct < 0 ? 'ok-text' : 'muted'}>{pct(o.diff_pct)} vs ours {rupees(o.rate)}</div>
      {o.compared_on !== 'before GST' && <div className="muted">{o.compared_on?.startsWith('before GST') ? o.compared_on : `on their price, GST ${o.gst}`}</div>}
    </>
  )
}

function Effort({ o }) {
  return o.relation === 'same part' ? <span className="tag ok">same part</span> : <span className="tag muted">{o.effort}</span>
}

function Option({ o }) {
  return (
    <>
      <a className="u" href={o.url} target="_blank" rel="noreferrer">{o.product || o.title}</a>
      <div className="small">{o.seller} <span className="muted">· {o.page_kind || 'page'} · stock: {o.in_stock}</span>
        {o.discontinued && <span className="tag bad" style={{ marginLeft: 6 }}>discontinued</span>}</div>
    </>
  )
}

/** Procurement records whether the lead held when they asked the seller. */
function Check({ o, onSaved }) {
  const [value, setValue] = useState(o.check || '')
  const [error, setError] = useState('')
  const save = async (check) => {
    setValue(check)
    try {
      await api(`/api/components/offers/${o.offer_id}`, { method: 'PATCH', body: JSON.stringify({ check, note: '' }) })
      setError(''); onSaved()
    } catch (e) { setError(e.message); setValue(o.check || '') }
  }
  return (
    <>
      <select value={value} onChange={(e) => save(e.target.value)}>
        <option value="">not checked</option>
        <option value="holds">holds</option>
        <option value="does not hold">does not hold</option>
      </select>
      {error && <div className="err small">{error}</div>}
    </>
  )
}

/** Every finding for one part: listed price, per-unit comparison, per-machine cost, and the judge's notes. */
function Findings({ offers }) {
  return (
    <table className="grid">
      <thead><tr><th style={{ width: 95 }}>Type</th><th style={{ width: '20%' }}>Product · seller</th><th style={{ width: 130 }}>Listed price</th><th style={{ width: 140 }}>Per unit vs ours</th><th style={{ width: 120 }}>Per machine</th><th>Why, what would change, concerns</th></tr></thead>
      <tbody>
        {offers.map((o) => (
          <tr key={o.offer_id}>
            <td className="small"><Effort o={o} /></td>
            <td><Option o={o} />{!!o.offers.length && <div className="small muted">{o.offers.join(', ')}</div>}</td>
            <td className="small"><Listed o={o} /></td>
            <td className="small"><Compared o={o} /></td>
            <td className="small">
              {o.machine_theirs == null ? <span className="muted">—</span>
                : <>{rupees(o.machine_theirs)}<div className="muted">ours {rupees(o.machine_ours)} for {o.qty ?? 1}</div></>}
            </td>
            <td className="small">
              {o.why && <div>{o.why}</div>}
              {o.changes && <div><span className="muted">Would change:</span> {o.changes}</div>}
              {!!o.checks.length && <div className="muted">{o.checks.map((c) => `${c.requirement}: ${c.status}`).join(' · ')}</div>}
              {o.concerns && <div><span className="muted">Concerns:</span> {o.concerns}</div>}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

function Kpi({ value, label, hint }) {
  return (
    <div className="kpi" title={hint}>
      <div className="kpi-value">{value}</div>
      <div className="small muted">{label}</div>
    </div>
  )
}

/** What to do: the saving on the table, the leads to act on, and what needs engineering to judge. */
function Decisions({ data, refresh, live }) {
  const ov = data.overview
  const v = ov.verdicts
  const checked = ov.checks.holds + ov.checks['does not hold']
  return (
    <>
      {live && <p className="small warn-line">Run in progress: these numbers fill in as each part is judged.</p>}
      <div className="kpis">
        <Kpi value={data.same_part.length} label={`parts with the same part cheaper elsewhere (${rupees(data.same_part.reduce((n, r) => n + r.best_same.saving_per_machine, 0))} per machine)`} />
        <Kpi value={data.upgrades.length} label="parts with a better or newer option that fits" />
        <Kpi value={data.alternatives.length} label={`parts with a cheaper alternative (${data.alternatives.filter((r) => r.best_alternative.effort === 'drop-in').length} fit as is)`} />
        <Kpi value={v['We pay the lowest found']} label="parts where we already pay the lowest found" />
        <Kpi value={`${ov.searched} of ${ov.parts}`} label={`parts searched (${Math.round(ov.searched_share * 100)}% of off-the-shelf spend)`}
             hint={`${ov.deferred} low-spend part(s) left for a full run; ${ov.custom} custom part(s) are never searched.`} />
        <Kpi value={checked ? `${ov.checks.holds} of ${checked}` : '—'} label="leads that held when checked" />
      </div>

      <div className="section-label">1. Same part, cheaper seller ({data.same_part.length})</div>
      {data.same_part.length ? (
        <table className="grid">
          <thead><tr><th style={{ width: '20%' }}>Part</th><th style={{ width: 100 }}>Ours, before GST</th><th>Seller</th><th style={{ width: 150 }}>Listed price</th><th style={{ width: 150 }}>Per unit vs ours</th><th style={{ width: 100 }}>Saving per machine</th><th style={{ width: 130 }}>Checked with seller</th></tr></thead>
          <tbody>
            {data.same_part.map((r) => (
              <tr key={r.part_id}>
                <td><strong>{r.part_id}</strong> {r.item}<div className="small muted">{r.subsystem}</div></td>
                <td className="small">{rupees(r.line_cost)}<div className="muted">{r.qty ?? 1} × {rupees(r.rate)}{r.gst != null && ` · ${rupees(r.line_cost * (1 + r.gst))} with ${Math.round(r.gst * 100)}% GST`}</div></td>
                <td><Option o={r.best_same} /></td>
                <td className="small"><Listed o={r.best_same} /></td>
                <td className="small"><Compared o={r.best_same} /></td>
                <td className="ok-text"><strong>{rupees(r.best_same.saving_per_machine)}</strong></td>
                <td><Check o={r.best_same} onSaved={refresh} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : <p className="muted tight">No other seller has the same part for less in this run.</p>}

      <div className="section-label">2. Better or newer, fits ({data.upgrades.length})</div>
      {data.upgrades.length ? (
        <table className="grid">
          <thead><tr><th style={{ width: '20%' }}>Part</th><th style={{ width: '22%' }}>Option · seller</th><th>What is better</th><th style={{ width: 150 }}>Fit</th><th style={{ width: 150 }}>Per unit vs ours</th></tr></thead>
          <tbody>
            {data.upgrades.map((r) => (
              <tr key={r.part_id}>
                <td><strong>{r.part_id}</strong> {r.item}<div className="small muted">{rupees(r.line_cost)} per machine</div></td>
                <td><Option o={r.best_upgrade} /></td>
                <td className="small"><strong>{r.best_upgrade.offers.join(', ')}</strong> — {r.best_upgrade.why}
                  {!!r.best_upgrade.checks.length && <div className="muted">{r.best_upgrade.checks.map((c) => `${c.requirement}: ${c.status}`).join(' · ')}</div>}</td>
                <td className="small"><Effort o={r.best_upgrade} />{r.best_upgrade.changes && <div className="muted">{r.best_upgrade.changes}</div>}</td>
                <td className="small"><Compared o={r.best_upgrade} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : <p className="muted tight">None shown to fit yet. Why chosen and Must Have in the workbook let the judge confirm fit.</p>}

      <div className="section-label">3. Cheaper alternatives: fits as is first, then needs adaptation ({data.alternatives.length})</div>
      {data.alternatives.length ? (
        <table className="grid">
          <thead><tr><th style={{ width: '20%' }}>Part</th><th style={{ width: 100 }}>Ours, before GST</th><th>Option · seller</th><th style={{ width: 150 }}>Per unit vs ours</th><th style={{ width: 100 }}>Saving per machine</th><th>What would change</th></tr></thead>
          <tbody>
            {data.alternatives.map((r) => (
              <tr key={r.part_id}>
                <td><strong>{r.part_id}</strong> {r.item}</td>
                <td className="small">{rupees(r.line_cost)}<div className="muted">{r.qty ?? 1} × {rupees(r.rate)}{r.gst != null && ` · ${rupees(r.line_cost * (1 + r.gst))} with ${Math.round(r.gst * 100)}% GST`}</div></td>
                <td><Option o={r.best_alternative} /><div className="small"><Effort o={r.best_alternative} /></div></td>
                <td className="small"><Compared o={r.best_alternative} /></td>
                <td className="small">{rupees(r.best_alternative.saving_per_machine)}</td>
                <td className="small">{r.best_alternative.effort === 'drop-in' ? 'Fits as is' : r.best_alternative.changes}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : <p className="muted tight">None.</p>}

      <p className="small muted" style={{ marginTop: 12 }}>
        Prices are compared in rupees per unit as our BOM counts it, before GST: the seller's own before-GST price, or their
        GST-included price less our GST rate for the part. Options whose
        fit the pages could not confirm are marked fit unclear and never shown in these three sections; every finding is in
        the Parts tab. Prices are as listed on the day of the run; ask the
        seller before ordering, then record whether the lead held.
      </p>
    </>
  )
}

/** One row per BOM part with its verdict; a row opens to every finding for that part. */
function Parts({ data }) {
  const [verdict, setVerdict] = useState('')
  const [subsystem, setSubsystem] = useState('')
  const [open, setOpen] = useState(null)
  const findings = useMemo(() => Object.fromEntries(data.parts.map((p) => [p.part_id, p.offers])), [data])
  const rows = [...data.rows]
    .filter((r) => (!verdict || r.verdict === verdict) && (!subsystem || r.subsystem === subsystem))
    .sort((a, b) => b.line_cost - a.line_cost)
  const verdicts = Object.entries(data.overview.verdicts).filter(([, n]) => n)
  return (
    <>
      <div className="row" style={{ marginBottom: 10 }}>
        <select value={verdict} onChange={(e) => setVerdict(e.target.value)}>
          <option value="">All verdicts ({data.rows.length})</option>
          {verdicts.map(([v, n]) => <option key={v} value={v}>{v} ({n})</option>)}
        </select>
        <select value={subsystem} onChange={(e) => setSubsystem(e.target.value)}>
          <option value="">All subsystems</option>
          {['Embedded', 'Electrical', 'Mechanical'].map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
        <span className="small muted">Highest cost per machine first. Click a part to see every finding.</span>
      </div>
      <table className="grid">
        <thead><tr><th style={{ width: '24%' }}>Part</th><th style={{ width: 110 }}>Ours, before GST</th><th style={{ width: 170 }}>Verdict</th><th>Best option</th><th style={{ width: 80 }}>Findings</th></tr></thead>
        <tbody>
          {rows.map((r) => {
            const shown = r.best || r.best_alternative
            return (
              <Fragment key={r.part_id}>
                <tr className={findings[r.part_id] ? 'clickable' : ''} onClick={() => findings[r.part_id] && setOpen(open === r.part_id ? null : r.part_id)}>
                  <td><strong>{r.part_id}</strong> {r.item}<div className="small muted">{r.subsystem}</div></td>
                  <td className="small">{rupees(r.line_cost)}<div className="muted">{r.qty ?? 1} × {r.rate ? rupees(r.rate) : 'no rate'}{r.rate && r.gst != null && ` · ${rupees(r.line_cost * (1 + r.gst))} with ${Math.round(r.gst * 100)}% GST`}</div></td>
                  <td><span className={`tag ${VERDICT_TAG[r.verdict]}`}>{r.verdict}</span></td>
                  <td className="small">
                    {shown ? <>{shown.product} · {shown.seller}{shown.diff_pct != null && <span className={shown.diff_pct < 0 ? 'ok-text' : 'muted'}> · {pct(shown.diff_pct)}</span>}</>
                      : <span className="muted">{r.note}</span>}
                  </td>
                  <td className="small">{r.findings ? `${r.findings} ${open === r.part_id ? '▾' : '▸'}` : '—'}</td>
                </tr>
                {open === r.part_id && (
                  <tr><td colSpan={5}><p className="part-summary small">{r.note}</p><Findings offers={findings[r.part_id]} /></td></tr>
                )}
              </Fragment>
            )
          })}
        </tbody>
      </table>
    </>
  )
}

/** One line for a step in the live feed. */
function describe(e) {
  if (e.tool === 'plan' && e.parts) return `Planned ${e.parts.length} parts: ${e.parts.filter((p) => !p.off_the_shelf).length} custom, the rest to consider for search`
  if (e.tool === 'scope') return `Scope: ${e.searched.length} parts to search${e.deferred.length ? `, ${e.deferred.length} low-spend parts left for a full run` : ''}`
  if (e.tool === 'search') return `${e.part_id} [${e.lane}] "${e.query}" · ${e.count} results`
  if (e.tool === 'assess' && e.outcome === 'failed') return `${e.part_id} could not be judged: ${e.detail}`
  if (e.tool === 'assess') return `${e.part_id} judged: ${(e.kept || []).length} kept of ${e.considered} pages`
  return e.tool
}

/** The run's trace, built from its steps as they arrive: progress, a live feed, and one row per part. */
function HowItRan({ data, events, live, partsTotal }) {
  const planned = events.filter((e) => e.tool === 'plan').flatMap((e) => e.parts || [])
  const scope = events.find((e) => e.tool === 'scope')
  const toSearch = new Set(scope?.searched || [])
  const deferred = new Set((scope?.deferred || []).map((d) => d.part_id))
  const group = (tool) => events.filter((e) => e.tool === tool).reduce((acc, e) => ({ ...acc, [e.part_id]: [...(acc[e.part_id] || []), e] }), {})
  const searches = group('search')
  const judged = group('assess')
  const failed = new Set(events.filter((e) => e.tool === 'assess' && e.outcome === 'failed').map((e) => e.part_id))
  const verdict = Object.fromEntries((data?.rows || []).map((r) => [r.part_id, r.verdict]))
  const status = (p) => {
    if (!p.off_the_shelf) return ['Custom, not searched', 'muted']
    if (deferred.has(p.part_id)) return ['Low spend, not searched this run', 'muted']
    if (failed.has(p.part_id)) return ['Could not be judged', 'bad']
    if (judged[p.part_id]) return live ? ['Judged', 'ok'] : [verdict[p.part_id] || 'Judged', VERDICT_TAG[verdict[p.part_id]] || 'ok']
    // Once the run is over nothing is still searching: say the part was never judged.
    if (!live && (searches[p.part_id] || toSearch.has(p.part_id))) return ['Not judged: the run ended first', 'bad']
    if (searches[p.part_id]) return ['Searching…', 'live']
    if (toSearch.has(p.part_id)) return ['Queued', 'muted']
    return ['Planned', 'muted']
  }
  const n = (o) => Object.keys(o).length
  const feed = events.filter((e) => ['plan', 'scope', 'search', 'assess'].includes(e.tool)).slice(-8).reverse()
  const scopeText = scope && (scope.scope === 'priority'
    ? `parts making up ${Math.round(scope.share * 100)}% of off-the-shelf spend`
    : scope.scope === 'all' ? 'every off-the-shelf part' : 'the parts named')
  return (
    <>
      <p className="small tight">
        <strong>Planned {planned.length} of {partsTotal}</strong> · searched {n(searches)} of {scope ? toSearch.size : '…'} ·
        judged {n(judged) - failed.size} of {scope ? toSearch.size : '…'}{failed.size ? ` · ${failed.size} could not be judged` : ''}{scope && ` · scope: ${scopeText}`}
      </p>
      {live && (
        <>
          <div className="section-label">Latest steps</div>
          <ul className="live-feed">
            {feed.length ? feed.map((e) => <li key={e.seq}><span className="mono muted">t+{Math.round(e.t)}s</span> {describe(e)}</li>)
              : <li className="muted">Planning the first batch of parts…</li>}
          </ul>
        </>
      )}
      <p className="small muted tight">
        The plan decides for each part whether it is bought off the shelf and writes two searches: the same model from any
        seller, and other models that do the same job. The judge then reads every page found for that part.
      </p>
      <table className="grid">
        <thead><tr><th style={{ width: '22%' }}>Part</th><th style={{ width: 160 }}>Status</th><th>Searched for</th><th style={{ width: 90 }}>Kept</th><th style={{ width: '22%' }}>Dropped pages</th></tr></thead>
        <tbody>
          {planned.map((p) => {
            const j = (judged[p.part_id] || [])[0]
            const a = j?.outcome === 'failed' ? null : j
            const [label, cls] = status(p)
            const waiting = p.off_the_shelf && !deferred.has(p.part_id)
            return (
              <tr key={p.part_id}>
                <td><strong>{p.part_id}</strong> {p.item}</td>
                <td className="small"><span className={`tag ${cls}`}>{label}</span>
                  {!p.off_the_shelf && <div className="muted">{p.reason}</div>}
                  {j?.outcome === 'failed' && <div className="muted">{j.detail}</div>}</td>
                <td className="small">
                  {(searches[p.part_id] || []).map((x) => (
                    <div key={x.seq}><span className="muted">[{x.lane}]</span> <span className="mono">{x.query}</span> · {x.count} results</div>
                  ))}
                  {!searches[p.part_id] && <span className="muted">{waiting ? (p.queries || []).join(' · ') || '—' : '—'}</span>}
                </td>
                <td className="small">{a ? `${(a.kept || []).length} of ${a.considered}` : '—'}</td>
                <td className="small">
                  {a && !!(a.excluded || []).length ? (
                    <details>
                      <summary className="muted">{a.excluded.length} dropped</summary>
                      {a.excluded.map((x) => <div key={x.url}><a className="u" href={x.url} target="_blank" rel="noreferrer">{x.title || x.url}</a> — <span className="why">{x.reason}</span></div>)}
                    </details>
                  ) : '—'}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </>
  )
}

/** A component-watch run: Decisions, Parts or How it ran. */
export default function ComponentRun({ runId, live, events, tab, partsTotal, status, summary }) {
  // A run that stopped or failed says so at the top of every view.
  const ended = !live && status && status !== 'succeeded'
    ? `This run ${status === 'stopped' ? 'was stopped' : 'failed'}: ${summary || 'no reason recorded'}. Parts below without a verdict were never judged.`
    : ''
  // Refetch the decisions each time another part is judged.
  const tick = events.filter((e) => e.tool === 'assess').length
  const [data, error, refresh] = useRun(runId, live, tick)
  // Parts whose judge reply failed are named on every view, whatever the run's status.
  const unjudged = data?.unjudged?.length
    ? `${data.unjudged.length} part(s) could not be judged because the model's reply failed: ${data.unjudged.map((u) => `${u.part_id} ${u.item} (${u.reason})`).join('; ')}.`
    : ''
  const banner = <>{ended && <p className="err small">{ended}</p>}{unjudged && <p className="err small">{unjudged}</p>}</>
  if (tab === 'trace') {
    return (
      <>
        {banner}
        <HowItRan data={data} events={events} live={live} partsTotal={partsTotal} />
        {/* The run's result under its trace, as on the other tracks. */}
        <section className="pass final" style={{ marginTop: 16 }}>
          <div className="pass-head static">
            <span className="pass-name">Result</span>
            <span className="small muted">{live ? 'filling in as parts are judged' : ''}</span>
          </div>
          <div className="pass-body">
            {error ? <p className="err small tight">{error}</p>
              : data?.rows.length ? <Decisions data={data} refresh={refresh} live={live} />
                : <p className="muted tight">Available once the parts are planned.</p>}
          </div>
        </section>
      </>
    )
  }
  if (error) return <p className="err small tight">{error}</p>
  if (!data) return <p className="muted tight">Loading…</p>
  if (!data.rows.length) return <p className="muted tight">Planning the parts… open How it ran to watch.</p>
  if (tab === 'parts') return <>{banner}<Parts data={data} /></>
  return <>{banner}<Decisions data={data} refresh={refresh} live={live} /></>
}
