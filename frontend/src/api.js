export const api = async (path, options) => {
  const res = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!res.ok) {
    let detail = ''
    try { detail = (await res.json()).detail || '' } catch { /* not JSON */ }
    throw new Error(`${path} → ${res.status}${detail ? `: ${detail}` : ''}`)
  }
  return res.json()
}

// The graph's nodes in execution order, and which node each journey event
// belongs to — progress is inferred from the journey rather than reported.
export const STAGES = ['plan', 'research', 'analyze', 'finalize']

export const STAGE_OF = {
  plan: 'plan',
  search: 'research',
  shortlist: 'research',
  select_links: 'research',
  scrape: 'research',
  analyze: 'analyze',
  extract: 'finalize',
  save_opportunity: 'finalize',
  actionability: 'finalize',
  skip: 'finalize',
}

export const DEFAULT_CONFIG = {
  model: '',
  budget: 40,
  max_searches: 12,
  max_scrapes: 14,
  max_llm_calls: 16,
  wall_clock_seconds: 900,
  queries: '',
}

const CONFIG_KEY = 'or-config'

export const loadConfig = () => {
  try {
    return { ...DEFAULT_CONFIG, ...JSON.parse(localStorage.getItem(CONFIG_KEY) || '{}') }
  } catch {
    return { ...DEFAULT_CONFIG }
  }
}

export const saveConfig = (config) => {
  try { localStorage.setItem(CONFIG_KEY, JSON.stringify(config)) } catch { /* private mode */ }
}

/** Config as the API wants it: blank model means "use OPENROUTER_MODEL". */
export const toRequest = (config, dryRun) => ({
  model: config.model.trim() || null,
  budget: Number(config.budget),
  max_searches: Number(config.max_searches),
  max_scrapes: Number(config.max_scrapes),
  max_llm_calls: Number(config.max_llm_calls),
  wall_clock_seconds: Number(config.wall_clock_seconds),
  queries: config.queries.split('\n').map((q) => q.trim()).filter(Boolean),
  dry_run: dryRun,
})

export const shortId = (id) => (id || '').slice(0, 6)

export const runLabel = (run) => {
  const when = run.started_at
    ? new Date(run.started_at).toLocaleString(undefined, {
        month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
      })
    : 'unknown time'
  return `${when} · ${run.model || 'default model'}`
}
