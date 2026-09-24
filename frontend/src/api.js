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

/* ------------------------------------------------------------ vocabulary --
   Three sets of words, and no others. The pipeline's internal identifiers are
   mapped here rather than renamed, so runs recorded before this still read
   correctly.                                                                */

/** A run either worked or it did not. */
export const RUN_STATUS = {
  succeeded: { label: 'Succeeded', cls: 'ok' },
  failed: { label: 'Failed', cls: 'bad' },
  running: { label: 'Running', cls: 'live' },
  stopped: { label: 'Stopped', cls: 'warn' },
  // Recorded by earlier versions.
  completed: { label: 'Succeeded', cls: 'ok' },
  completed_with_rejections: { label: 'Succeeded', cls: 'ok' },
}

export const runStatus = (status) =>
  RUN_STATUS[status] || { label: status || 'unknown', cls: 'muted' }

/** What became of one page or candidate. */
export const OUTCOME = {
  saved: { label: 'Saved', cls: 'ok' },
  needs_deeper_read: { label: 'Needs deeper read', cls: 'warn' },
  'not relevant': { label: 'Not relevant', cls: 'muted' },
  historical: { label: 'Closed or passed', cls: 'muted' },
  reject: { label: 'Closed or passed', cls: 'muted' },
  'could not fetch': { label: "Couldn't read", cls: 'bad' },
  'not pursued': { label: 'Not relevant', cls: 'muted' },
  'extraction failed': { label: "Couldn't read", cls: 'bad' },
}

export const outcome = (key) =>
  OUTCOME[key] || { label: key || 'unknown', cls: 'muted' }

/** What a run is looking for. Steers the search; filters nothing. */
export const FOCUS = [
  ['any', 'Everything', 'Awards, events and technical venues together.'],
  ['award', 'Awards', 'Prizes, rankings and honours we could be entered for.'],
  ['event', 'Events', 'Conferences, summits, forums and expos.'],
  ['research', 'Research', 'Conference papers, workshops, demo tracks and challenges.'],
]

/** What kind of opportunity a stored record is. */
export const CATEGORY = {
  award: { label: 'Award', cls: 'ok' },
  event: { label: 'Event', cls: 'live' },
  conference: { label: 'Conference', cls: 'live' },
  research: { label: 'Research venue', cls: 'warn' },
  grant: { label: 'Grant', cls: 'muted' },
}

export const category = (key) =>
  CATEGORY[key] || { label: key || 'Opportunity', cls: 'muted' }

/** One eligibility condition. */
export const VERDICT = {
  met: { label: 'Met', cls: 'ok', order: 0 },
  not_met: { label: 'Not met', cls: 'bad', order: 1 },
  unclear: { label: 'Needs review', cls: 'warn', order: 2 },
  qualitative: { label: 'Needs review', cls: 'warn', order: 2 },
}

/* ----------------------------------------------------------------- stages */

export const STAGES = [
  'plan', 'search', 'rank', 'fetch', 'extract', 'evaluate', 'store',
]

export const STAGE_OF = {
  plan: 'plan',
  search: 'search',
  shortlist: 'rank',
  memory: 'rank',
  select_links: 'fetch',
  scrape: 'fetch',
  analyze: 'extract',
  extract: 'extract',
  grounding: 'extract',
  dedupe: 'search',
  expired: 'search',
  actionability: 'extract',
  skip: 'extract',
  feasibility: 'evaluate',
  save_opportunity: 'store',
}

/* ----------------------------------------------------------------- config */

/** Where searches go. Exa reads dates and entry conditions off each page. */
export const SEARCH_PROVIDERS = [
  ['exa', 'Exa', 'Reads deadlines and who can enter off each page, so closed programmes drop before any scrape.'],
  ['tavily', 'Tavily', 'Query-matched extracts only; dates rarely come back.'],
]

export const DEFAULT_CONFIG = {
  model: '',
  budget: 70,
  max_searches: 8,
  max_scrapes: 20,
  max_llm_calls: 30,
  // Scrapes are paced for Firecrawl's per-minute cap, so waiting is by design.
  wall_clock_seconds: 1500,
  max_candidates: 6,
  max_links_per_page: 2,
  max_pages_per_seed: 3,
  max_depth: 1,
  focus: 'any',
  search_provider: 'exa',
  queries: '',
}

const CONFIG_KEY = 'or-config-v2'

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
  max_candidates: Number(config.max_candidates),
  max_links_per_page: Number(config.max_links_per_page),
  max_pages_per_seed: Number(config.max_pages_per_seed),
  max_depth: Number(config.max_depth),
  focus: config.focus || 'any',
  search_provider: config.search_provider || 'exa',
  queries: config.queries.split('\n').map((q) => q.trim()).filter(Boolean),
  dry_run: dryRun,
})

/** Worst-case calls one pass costs, so the knobs show their price. */
export const estimateCalls = (c) => {
  const seeds = Number(c.max_candidates)
  const perSeed = Number(c.max_pages_per_seed)
  const linkCalls = Number(c.max_depth) > 0 ? seeds * Number(c.max_depth) : 0
  // 2 planning calls (the plan is written in two waves), 5 searches, 1 ranking,
  // one link-choice per depth level per seed, then the pages themselves, one
  // analyze per seed and one save per seed.
  return 2 + 5 + 1 + linkCalls + seeds * perSeed + seeds + seeds
}

export const shortId = (id) => (id || '').slice(0, 6)

export const runLabel = (run) => {
  const when = run.started_at
    ? new Date(run.started_at).toLocaleString(undefined, {
        month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
      })
    : 'unknown time'
  return `${when} · ${run.model || 'default model'}`
}
