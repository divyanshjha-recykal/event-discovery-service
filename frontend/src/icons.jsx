/* Inline stroke icons — no icon dependency, and they inherit currentColor. */

const Svg = ({ children, size = 15 }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none"
       stroke="currentColor" strokeWidth="1.9" strokeLinecap="round"
       strokeLinejoin="round" aria-hidden="true">
    {children}
  </svg>
)

export const IconTarget = () => (
  <Svg><circle cx="12" cy="12" r="9" /><circle cx="12" cy="12" r="5" /><circle cx="12" cy="12" r="1.5" /></Svg>
)
export const IconSearch = () => (
  <Svg><circle cx="11" cy="11" r="7" /><path d="m20 20-3.6-3.6" /></Svg>
)
export const IconFilter = () => (
  <Svg><path d="M3 6h18M7 12h10M10 18h4" /></Svg>
)
export const IconLink = () => (
  <Svg><path d="M10 13a5 5 0 0 0 7 0l2-2a5 5 0 0 0-7-7l-1 1" /><path d="M14 11a5 5 0 0 0-7 0l-2 2a5 5 0 0 0 7 7l1-1" /></Svg>
)
export const IconPage = () => (
  <Svg><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" /><path d="M14 3v5h5M9 13h6M9 17h4" /></Svg>
)
export const IconAnalyze = () => (
  <Svg><path d="M4 20V10M10 20V4M16 20v-7M22 20H2" /></Svg>
)
export const IconPackage = () => (
  <Svg><path d="m12 2 9 5v10l-9 5-9-5V7z" /><path d="M12 12 3 7M12 12l9-5M12 12v10" /></Svg>
)
export const IconCalendar = () => (
  <Svg><rect x="3" y="5" width="18" height="16" rx="2" /><path d="M8 3v4M16 3v4M3 10h18" /></Svg>
)
export const IconSkip = () => (
  <Svg><path d="M6 6h12v12H6z" opacity=".25" /><path d="m7 7 6 5-6 5zM17 7v10" /></Svg>
)
export const IconSave = () => (
  <Svg><ellipse cx="12" cy="6" rx="8" ry="3" /><path d="M4 6v6c0 1.7 3.6 3 8 3s8-1.3 8-3V6" /><path d="M4 12v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6" /></Svg>
)
export const IconDot = () => (
  <Svg><circle cx="12" cy="12" r="4" /></Svg>
)
export const IconChevron = ({ open }) => (
  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor"
       strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"
       style={{ transform: open ? 'rotate(90deg)' : 'none', transition: 'transform .15s' }}>
    <path d="m9 6 6 6-6 6" />
  </svg>
)
export const IconPlay = () => (
  <Svg size={13}><path d="M7 4v16l13-8z" fill="currentColor" stroke="none" /></Svg>
)
export const IconStop = () => (
  <Svg size={13}><rect x="6" y="6" width="12" height="12" rx="1.5" fill="currentColor" stroke="none" /></Svg>
)
export const IconSun = () => (
  <Svg><circle cx="12" cy="12" r="4.5" /><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" /></Svg>
)
export const IconMoon = () => (
  <Svg><path d="M20 14.5A8.5 8.5 0 0 1 9.5 4a8.5 8.5 0 1 0 10.5 10.5" /></Svg>
)
export const IconTrash = () => (
  <Svg size={13}><path d="M4 7h16M10 11v6M14 11v6" /><path d="M6 7l1 12a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-12" /><path d="M9 7V5a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2" /></Svg>
)
export const IconExternal = () => (
  <Svg size={12}><path d="M14 4h6v6" /><path d="M20 4 11 13" /><path d="M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5" /></Svg>
)

export const TOOL_ICON = {
  plan: IconTarget,
  search: IconSearch,
  shortlist: IconFilter,
  select_links: IconLink,
  scrape: IconPage,
  analyze: IconAnalyze,
  extract: IconPackage,
  actionability: IconCalendar,
  skip: IconSkip,
  save_opportunity: IconSave,
}
