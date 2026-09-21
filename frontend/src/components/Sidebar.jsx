import { NavLink } from 'react-router-dom'
import { DEFAULT_CONFIG, FOCUS, estimateCalls, runLabel, runStatus, shortId } from '../api.js'
import { IconChevron, IconMoon, IconPlay, IconSun, IconTrash } from '../icons.jsx'

// Suggestions only — the field is free text so any OpenRouter model id works,
// and blank means the server's OPENROUTER_MODEL.
const SUGGESTED = [
  'deepseek/deepseek-v4.1-flash',
  'tencent/hy3',
  'qwen/qwen3-32b',
  'z-ai/glm-5.3-flash',
  'xiaomi/mimo-v2.5',
  'ibm-granite/granite-4.1-8b',
]

const CAPS = [
  ['budget', 'Tool calls', 1, 200, 'Hard ceiling on every paid call in the run.'],
  ['max_searches', 'Searches', 1, 60, 'Tavily calls.'],
  ['max_scrapes', 'Scrapes', 1, 60, 'Firecrawl page fetches, including retries.'],
  ['max_llm_calls', 'Model calls', 1, 60, 'Every reasoning call the run makes.'],
  ['wall_clock_seconds', 'Wall clock (s)', 30, 3600, 'Stops a run that hangs on a provider.'],
]

const REACH = [
  ['max_candidates', 'Sites to read', 1, 12, 'Top-k search results taken forward.'],
  ['max_links_per_page', 'Links per page', 0, 6, 'Links followed from each page read.'],
  ['max_pages_per_seed', 'Pages per site', 1, 10, 'Total pages read per site, seed included.'],
  ['max_depth', 'Depth', 0, 3, '1 = seed plus its links. 2 = one level further.'],
]

export default function Sidebar({
  config, setConfig, busy, onStart, runs, theme, toggleTheme, onClear,
  collapsed, onToggleCollapse, onDeleteRun,
}) {
  const set = (key) => (ev) => setConfig({ ...config, [key]: ev.target.value })

  if (collapsed) {
    return (
      <aside className="sidebar rail">
        <button className="ghost xs rail-toggle" type="button" onClick={onToggleCollapse}
                title="Expand the configurator">
          <IconChevron open />
        </button>
        <NavLink to="/" className="rail-brand" title="Opportunity Radar">
          <span className="dot" />
        </NavLink>
        <button className="rail-run" type="button" disabled={busy}
                onClick={() => onStart('/api/pipeline', false)}
                title="Run full pipeline">
          <IconPlay />
        </button>
        <div className="rail-runs">
          {runs.slice(0, 14).map((r) => (
            <NavLink key={r.run_id} to={`/run/${r.run_id}`}
                     title={`${runStatus(r.status).label} · ${runLabel(r)}`}
                     className={({ isActive }) => `rail-dot ${runStatus(r.status).cls}${isActive ? ' selected' : ''}`} />
          ))}
        </div>
        <div className="spacer" />
        <button className="ghost xs" type="button" onClick={toggleTheme} title="Toggle theme">
          {theme === 'dark' ? <IconSun /> : <IconMoon />}
        </button>
      </aside>
    )
  }

  return (
    <aside className="sidebar">
      <div className="side-top">
        <NavLink to="/" className="brand">
          <span className="dot" />
          <span>
            <strong>Opportunity Radar</strong>
            <span className="small muted">discovery → extraction → eligibility</span>
          </span>
        </NavLink>
        <button className="ghost xs collapse" type="button" onClick={onToggleCollapse}
                title="Collapse the configurator">
          <IconChevron />
        </button>
      </div>

      <section className="side-block">
        <h4>Model</h4>
        <input
          type="text"
          list="model-suggestions"
          value={config.model}
          placeholder="OPENROUTER_MODEL from .env"
          onChange={set('model')}
          spellCheck="false"
        />
        <datalist id="model-suggestions">
          {SUGGESTED.map((m) => <option key={m} value={m} />)}
        </datalist>
        <p className="hint">
          Any OpenRouter model id. Leave blank to use the one configured in <code>.env</code>.
        </p>
      </section>

      <section className="side-block">
        <h4>Looking for</h4>
        <div className="focus-picker">
          {FOCUS.map(([value, label, hint]) => (
            <button
              key={value}
              type="button"
              title={hint}
              className={`focus-opt${(config.focus || 'any') === value ? ' on' : ''}`}
              onClick={() => setConfig({ ...config, focus: value })}
            >
              {label}
            </button>
          ))}
        </div>
        <p className="hint">
          {(FOCUS.find(([v]) => v === (config.focus || 'any')) || [])[2]} Steers
          what gets searched for; nothing is discarded for being another kind.
        </p>
      </section>

      <section className="side-block">
        <h4>Budget caps</h4>
        {CAPS.map(([key, label, min, max, hint]) => (
          <label className="field" key={key} title={hint}>
            <span className="small muted">{label}</span>
            <input type="number" min={min} max={max} value={config[key]} onChange={set(key)} />
          </label>
        ))}
        <button className="link-btn" type="button"
                onClick={() => setConfig({ ...config, ...DEFAULT_CONFIG, model: config.model, focus: config.focus })}>
          Reset caps to defaults
        </button>
      </section>

      <section className="side-block">
        <h4>How far to look</h4>
        {REACH.map(([key, label, min, max, hint]) => (
          <label className="field" key={key} title={hint}>
            <span className="small muted">{label}</span>
            <input type="number" min={min} max={max} value={config[key]} onChange={set(key)} />
          </label>
        ))}
        <p className="hint">
          Roughly <strong>{estimateCalls(config)}</strong> tool calls per pass at these
          settings, against a budget of {config.budget}.
        </p>
      </section>

      <section className="side-block">
        <details>
          <summary>Seed queries (optional)</summary>
          <textarea
            rows="4"
            value={config.queries}
            placeholder={'One per line.\nLeave empty to let the planner write them.'}
            onChange={set('queries')}
          />
          <p className="hint">Supplied queries skip the planner and disable the re-plan step.</p>
        </details>
      </section>

      <section className="side-block actions">
        <button type="button" disabled={busy} onClick={() => onStart('/api/pipeline', false)}>
          <IconPlay /> Run full pipeline
        </button>
        <button className="ghost" type="button" disabled={busy}
                onClick={() => onStart('/api/runs', false)}>
          Discovery only
        </button>
        <button className="ghost" type="button" disabled={busy}
                onClick={() => onStart('/api/eligibility', false)}>
          Eligibility only
        </button>
        <button className="ghost" type="button" disabled={busy}
                onClick={() => onStart('/api/pipeline', true)}>
          Dry run (no API cost)
        </button>
      </section>

      <section className="side-block runs">
        <h4>Runs</h4>
        {!runs.length && <p className="hint">No runs yet.</p>}
        {runs.map((r) => (
          <div className="runrow-wrap" key={r.run_id}>
            <NavLink to={`/run/${r.run_id}`}
                     className={({ isActive }) => `runrow${isActive ? ' selected' : ''}`}>
              <div className="row">
                <span className={`tag ${runStatus(r.status).cls}`}>
                  {runStatus(r.status).label}
                </span>
                <span className="mono small muted">{shortId(r.run_id)}</span>
              </div>
              <div className="small">{runLabel(r)}</div>
              <div className="small muted">
                {r.counts?.saved ?? 0} ready · {r.counts?.needs_deeper ?? 0} thin ·{' '}
                {r.counts?.rejected ?? 0} aside
              </div>
            </NavLink>
            <button className="runrow-del" type="button"
                    title="Delete this run record"
                    disabled={r.status === 'running'}
                    onClick={() => onDeleteRun(r)}>
              <IconTrash />
            </button>
          </div>
        ))}
      </section>

      <div className="side-foot">
        <button className="ghost xs" type="button" onClick={toggleTheme}
                title="Toggle light and dark">
          {theme === 'dark' ? <IconSun /> : <IconMoon />}
        </button>
        <span className="spacer" />
        <button className="danger xs" type="button" onClick={onClear} disabled={busy}>
          Clear database
        </button>
      </div>
    </aside>
  )
}
