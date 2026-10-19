"""What each kind of opportunity is, as data the node prompts are filled from.

Nothing here is about one organisation; who is searching and what it wants
comes from the business profile.
"""

from __future__ import annotations

from dataclasses import dataclass, fields


@dataclass(frozen=True)
class Track:
    """One line of enquiry within a type; a type with tracks gives each an equal share of queries."""

    key: str
    label: str
    #: Where in the profile this track's angles come from.
    source: str


@dataclass(frozen=True)
class TypeSpec:
    key: str
    #: What a run of this type looks for, as a noun phrase.
    noun: str
    #: What this type is, for the planner and ranker; empty when the run covers every type.
    brief: str
    #: How queries handle geography.
    market_rule: str
    #: Example queries with the reason each is a good shape; fields deliberately unrelated to any profile.
    query_examples: tuple[str, ...]
    #: A query rule for this type alone; empty when the shared rules suffice.
    query_rule: str
    #: Exa picks passages relevant to each query instead of the fixed entry-detail instruction.
    query_guided_highlights: bool
    #: A result is fetched only if it meets every condition.
    rank_conditions: tuple[str, ...]
    #: How results that pass are ordered; ordering never removes a result.
    rank_order: tuple[str, ...]
    #: What the link picker checks a page for before choosing links.
    link_checklist: str
    #: How extraction fills the conditions, criteria and requirements lists for this type.
    record_guide: str
    #: Lines of enquiry sharing the searches equally; empty for a single line.
    tracks: tuple[Track, ...] = ()

    def __post_init__(self) -> None:
        empty = [
            f.name for f in fields(self)
            if f.name not in ("brief", "tracks", "query_rule") and isinstance(getattr(self, f.name), (str, tuple))
            and not getattr(self, f.name)
        ]
        if empty:
            raise ValueError(f"type spec {self.key!r} has empty fields: {', '.join(empty)}")


_MARKET = (
    "Name the primary market from CONSTRAINTS, or ask for programmes open to "
    "entrants based there."
)
_NO_COUNTRY = (
    "Do not name a country: peer-reviewed venues are international, and the "
    "subfield decides fit."
)
_EXAMPLE_AWARD = (
    '"nominations page for a national award recognising fintech startups in '
    'Brazil" names the page, the field, the entrant and the market.'
)
_EXAMPLE_EVENT = (
    '"exhibitor registration page for an agritech trade show in Indonesia" '
    "names the page, the field, how a company takes part, and where."
)
_EXAMPLE_RESEARCH = (
    '"2027 main-track call for papers of a major computational biology conference" '
    "names the page, the subfield and the year.",
    '"workshop call for papers on protein structure prediction at a major machine '
    'learning conference in 2027" names the page, the subfield and the year.',
)
_AWARD_QUERY_RULE = (
    "Ask for awards a company enters or is named to; never grants, CSR awards, "
    "or awards for individuals, students or NGOs."
)
_RESEARCH_QUERY_RULE = (
    "Describe the call by its subfield and kind of page (main-track call for papers, "
    "workshop call, challenge, journal special issue); never name a specific "
    "conference or journal. Never write \"international conference on\": it "
    "matches series that run many unrelated events."
)
_OPEN = (
    "Open — fails when this edition is over: its entry deadline or event date has "
    "passed, winners are announced, entries are stated closed, or it is an earlier "
    "edition (its title names a past year and no date on it is still ahead). A "
    "result with no date and no past-year title passes."
)
_DISTINCT = (
    "Distinct — not a second category or page of a programme already picked: "
    "categories sharing one organiser and entry process are one programme, so "
    "keep its best-fitting page. A workshop with its own call is its own programme."
)
_RANK_CONDITIONS = (
    "Programme page — one programme, published by the body that runs it. Not a "
    "news article, press release, directory or list of many programmes.",
    "Enterable — nothing in the extract excludes this business under "
    "CONSTRAINTS: entrant type, market, or what is not sought. Judge the entrant "
    "the programme wants, not the topic it covers.",
    _OPEN,
    _DISTINCT,
)
_RANK_ORDER = (
    "Fit — how closely it matches what this business seeks and does.",
    "Standing — how established the body that runs it is.",
    "Only between results equal on fit and standing: the sooner deadline first.",
)
_AWARD_CONDITIONS = (
    "Programme page — one programme, published by the body that runs it. Not a "
    "news article, press release, directory or list of many programmes.",
    "Company award — an award, ranking or honour a company is entered for or "
    "named to, which nothing in CONSTRAINTS excludes (entrant type, market, what "
    "is not sought). Not grants, funding, accelerators or cohorts, CSR "
    "programmes, or awards for individuals, students or NGOs.",
    _OPEN,
    _DISTINCT,
)
_AWARD_ORDER = (
    "Fit — how closely it recognises what this business does: its fields, "
    "technology, impact or stage.",
    "Standing — how established the body that runs it is: industry bodies, "
    "government programmes and major publications above commercial award companies.",
    "Only between results equal on fit and standing: the sooner deadline first.",
)
_RESEARCH_CONDITIONS = (
    "Paper call — the venue's own call for papers, workshop papers or challenge "
    "entries at a conference, workshop or journal, published by the venue itself. "
    "Not a page for proposing a workshop, a news item, or a listing or tracker "
    "site, even one that copies a venue's call.",
    "Established — run or published by an established body; judge from the "
    "organiser, the sponsor and what you know of the venue. Series that run many "
    "unrelated conferences or accept anything for a fee fail.",
    "Takes part — not limited to students or individuals, nor excluded by "
    "CONSTRAINTS.",
    _OPEN,
    _DISTINCT,
)
_RESEARCH_ORDER = (
    "Relevance — how closely the work the call asks for matches the methods, "
    "problems and systems in one of the TRACKS. Judge the work it wants "
    "submitted, not words it shares with the profile.",
    "Standing — how established and selective the venue is.",
    "Only between results equal on relevance and standing: the sooner deadline first.",
)
_EVENT_CONDITIONS = (
    "Event page — one event, published by its organiser. Not a news article, "
    "directory or list of many events.",
    "Company route — the page offers this business a way to take part: "
    "exhibiting, speaking, demonstrating or applying. Visitor-only or attendee-only "
    "registration fails, as does anything CONSTRAINTS exclude.",
    _OPEN,
    _DISTINCT,
)
_EVENT_ORDER = (
    "Relevance — how closely the event's sector and audience match what this "
    "business sells and who buys it.",
    "Standing — how established the organiser is.",
    "Only between results equal on relevance and standing: the sooner deadline first.",
)
_LINK_CHECKLIST = (
    "its dates or deadline, who can take part, how to apply or submit, and its "
    "scope or categories"
)
_AWARD_CHECKLIST = (
    "its entry deadline, who can enter, its categories, any entry fee, and how to apply"
)
_RESEARCH_CHECKLIST = (
    "its important dates, topics of interest, submission guidelines and format, "
    "and its tracks or workshops"
)
_EVENT_CHECKLIST = (
    "its dates and venue, how to exhibit or speak, the booking or application "
    "deadline, the cost, and who attends"
)
_RECORD_EVENT = """## Ways to take part — the heart of this
This is an event; use category "event". Fill the lists this way, each item on its
own, in the page's own words:
- `entry_eligibility`: each way a company can take part (exhibit, speak,
  demonstrate, apply), with any condition the page attaches to it ("Exhibitors:
  manufacturers and suppliers of recycling equipment"). Never the audience or
  attendee profile. Empty when the page offers no way to take part.
- `application_requirements`: how to take part — booking or application steps,
  stand or package options, costs, and what to submit.
- `judging_criteria`: how speaker or demo applications are selected; empty when none.
`submission_deadline` is the last date to book or apply; `event_date` is the first
day of the event."""
_RECORD_CONDITIONS = """## Entry eligibility — the heart of this
List every stated condition an entrant must satisfy, each as its own item, in
the words the page uses. If the page states no conditions, return an empty list
— never a sentence saying there are none, and never the event's audience or
attendee description. Form fields ("Registration Number*") and lists of who
attends ("CXOs & founders") are not conditions, and nor are submission rules
(how many entries are allowed, which forms to fill, fees, codes of conduct): those
are application requirements. Do not summarise them into one line and do not invent
conditions the page does not state. Keep judging criteria (what the entry is
scored on) and application requirements (what must be submitted) in their own
separate lists.

Use category "research" for a venue that accepts submitted work — a call for
papers, a workshop, an industry track, a technical competition. These state no
conditions on who may enter, because anyone may; what decides whether it is
worth entering is whether the work fits. So for a research venue, entry
eligibility is the SCOPE: the topics, tracks and problem areas the venue says it
wants, each as its own item, in the page's own words. Submission format, page
limits and anonymity rules are application requirements, not eligibility."""
_RECORD_RESEARCH = """## Topics, requirements and dates — the heart of this
This is a call for submitted work; use category "research". Fill the three lists
this way, each item on its own, in the page's own words:
- `entry_eligibility`: the SCOPE — every topic, track and problem area the call
  asks for. Empty when the page lists none.
- `application_requirements`: how to submit — paper format, page limits,
  anonymity, and where accepted papers are published (proceedings or journal).
- `judging_criteria`: the review criteria the page states; empty when none.
`submission_deadline` is the last date full papers are accepted; abstract
registration and every other dated step go in `deadline_note`."""

ANY = TypeSpec(
    key="any",
    noun="programmes this business could enter or submit work to",
    brief="",
    market_rule="Follow the market rule of the query's track, given under TRACKS.",
    query_examples=(_EXAMPLE_AWARD, _EXAMPLE_EVENT, _EXAMPLE_RESEARCH[0]),
    query_rule="",
    query_guided_highlights=False,
    rank_conditions=_RANK_CONDITIONS,
    rank_order=_RANK_ORDER,
    link_checklist=_LINK_CHECKLIST,
    record_guide=_RECORD_CONDITIONS,
    # Each key names a type spec, whose rules apply to that track's queries and results.
    tracks=(
        Track("award", "awards", "the profile's Seeking (awards) line"),
        Track("event", "events", "the profile's Seeking (events) line"),
        Track(
            "research", "research venues",
            "the profile's Seeking (research) line and its Technology section",
        ),
    ),
)

AWARD = TypeSpec(
    key="award",
    noun="awards, prizes and rankings this business could be entered for",
    brief=(
        "THIS RUN WANTS AWARDS. Prizes, rankings and honours this business "
        "could be entered for or named to."
    ),
    market_rule=_MARKET,
    query_examples=(_EXAMPLE_AWARD,),
    query_rule=_AWARD_QUERY_RULE,
    query_guided_highlights=False,
    rank_conditions=_AWARD_CONDITIONS,
    rank_order=_AWARD_ORDER,
    link_checklist=_AWARD_CHECKLIST,
    record_guide=_RECORD_CONDITIONS,
)

EVENT = TypeSpec(
    key="event",
    noun="events this business could speak at, exhibit at or take part in",
    brief=(
        "THIS RUN WANTS EVENTS. Conferences, summits, forums and expos this "
        "business could participate at, exhibit at or take part in to demonstrate it's products and/or technology."
    ),
    market_rule=_MARKET,
    query_examples=(_EXAMPLE_EVENT,),
    query_rule="",
    query_guided_highlights=False,
    rank_conditions=_EVENT_CONDITIONS,
    rank_order=_EVENT_ORDER,
    link_checklist=_EVENT_CHECKLIST,
    record_guide=_RECORD_EVENT,
)

RESEARCH = TypeSpec(
    key="research",
    noun=(
        "peer-reviewed technical venues — main-track paper calls, workshops and "
        "challenge tracks at established conferences and journals"
    ),
    brief=(
        "THIS RUN WANTS PEER-REVIEWED TECHNICAL VENUES WHERE THIS BUSINESS'S "
        "ENGINEERING TEAM CAN PUBLISH, PRESENT OR COMPETE — main-track paper "
        "calls, workshops and challenge tracks at established international "
        "conferences and journals, run or published by recognised scholarly "
        "bodies. Venues are organised by technical subfield, so search the "
        "technique or problem, never this business's industry or product. Not "
        "wanted: student, college or individual competitions and presentation "
        "events, standalone hackathons, developer challenges, and conference "
        "series that run many unrelated events."
    ),
    market_rule=_NO_COUNTRY,
    query_examples=_EXAMPLE_RESEARCH,
    query_rule=_RESEARCH_QUERY_RULE,
    query_guided_highlights=True,
    rank_conditions=_RESEARCH_CONDITIONS,
    rank_order=_RESEARCH_ORDER,
    link_checklist=_RESEARCH_CHECKLIST,
    record_guide=_RECORD_RESEARCH,
    tracks=(
        Track(
            "core", "core technology",
            "the methods, models, sensing, datasets and deployment in the profile's Technology section",
        ),
        Track(
            "topics", "research topics and current work",
            "the Research topics and Current research in house lines in the profile's "
            "Technology section, each searched by the technique or problem it names, never its product",
        ),
    ),
)

SPECS = {spec.key: spec for spec in (ANY, AWARD, EVENT, RESEARCH)}


def spec_for(focus: str) -> TypeSpec:
    """The spec for a run's type; an unknown type stops the run."""
    try:
        return SPECS[focus or "any"]
    except KeyError:
        raise ValueError(f"unknown opportunity type {focus!r}; known: {', '.join(SPECS)}") from None
