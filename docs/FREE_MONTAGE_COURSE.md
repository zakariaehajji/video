# Free Montage Course Notes (AutoLab)

**Original synthesis** for our wedding editor. Sources are free/public educational
pages and open course outlines — **not** paid CapCut/Skillshare/MasterClass content,
and **not** copied transcripts.

## Sources studied (free / open)

| Source | Type | What we took |
|--------|------|--------------|
| [OSU Open Textbook — Editing](https://open.library.okstate.edu/introfilmtv/part/editing/) | Open educational resource | Continuity system; Kuleshov / meaning between shots |
| [UWG Film Terms Glossary](https://www.westga.edu/academics/university-college/writing/glossary_of_film_terms.php) | Public glossary | Continuity vs montage vocabulary |
| [Moorpark FTMA M170 COR](https://www.moorparkcollege.edu/sites/moorparkcollege/files/faculty-staff/committees/curriculum/CORs/ftma_m170_digital_editing.pdf) | Public course outline | Shot duration, juxtaposition, transitions, pacing |
| Coursera course *syllabus listings* (Foundation of Video Editing / Sequence & Editing) | Free-to-audit outlines | Montage vs continuity; rhythm at shot + sequence level |
| Public wedding editing pedagogy articles (timeline / style-guide essays) | Free web craft | Story-first highlight arcs; hold emotion; montage only in prep/party |

## Module 1 — Why we cut

From open film pedagogy:

1. **Continuity editing** — keep space/time clear; cuts should feel invisible when telling a wedding day chronologically.
2. **Montage** — meaning comes from **shot A next to shot B** (Kuleshov). A calm face after a kiss reads as love; after tears, as empathy.
3. **Duration + juxtaposition + transition** are the three levers (college digital-editing objectives).

Machine rule for us:

- Prefer **reaction / portrait after intimacy** on or just after peak.
- Prefer hard cuts on peak; soft dissolves on intro/outro/build.

## Module 2 — Continuity grammar (Hollywood baseline)

Rules we approximate offline (no full 180° tracker yet):

| Rule | Wedding proxy in AutoLab |
|------|---------------------------|
| Screen direction / axis | Color continuity + avoid harsh palette jumps |
| Match on action | Prefer motion→motion in chorus; don’t hard-cut static↔wild shake |
| Establishing → detail | Intro: wide/detail before couple peak |
| Shot / reverse | Peak: couple ↔ portrait / reaction |

## Module 3 — Montage grammar (Soviet insight, modern use)

Use montage **selectively**:

- **Prep / details**: rings → flowers → hands (intellectual montage of “getting ready”).
- **Celebration**: guests / dance / motion (rhythmic montage).
- **Do not** montage-spray the kiss / vows / tears — those need continuity holds.

## Module 4 — Rhythm and pacing

From sequence/editing pedagogy + wedding craft essays:

1. Shot length creates tempo; shorter ≠ better.
2. **Accelerate through the day**: soft open → held ceremony → denser reception.
3. Cut on **phrases / bars / section changes**, not every beat (wedding ≠ TikTok).
4. Emotional holds often **6–10s** in long highlights; our short films use **2.5–4.5s** floors.

## Sprint 20min — Phrase pacing

Studied (free only):

- [OSU Editing — continuity / cut meaning](https://open.library.okstate.edu/introfilmtv/part/editing/)
- [Coursera: Sequence and Editing — Rhythm, Pacing, Trajectory Phrasing syllabus](https://www.coursera.org/learn/sequence-and-editing)
- Wedding style-guide craft already cited above (hold emotion; montage only prep/party)

Five original rules for AutoLab:

1. **Shot length is tempo** — if every cut is ~1s, the audience feels anxiety, not romance.
2. **Phrase > beat** — land cuts on musical phrases / section changes; reserve denser cuts for celebration only.
3. **Peak must breathe** — intimacy (kiss/hug/tears) needs a hold floor (~3s+ in our short films), not a flash frame.
4. **Trajectory phrasing** — each stretch of the film should feel like one continuous emotional move (soft open → crest → resolve), not a random clip pile.
5. **Test muted** — if the story still reads without hearing every beat hit, the phrase structure is working.

Machine encode: template `course_phrase_hold` + critic flag when mean hold &lt; 1.3s **and** peak holds &lt; 2.0s.

## Module 5 — Wedding story products

### Social teaser (~30–60s)

Hook → details → build → emotional peak → celebration → resolve.

### Highlight (~3–7 min classically; our Autolab ~38–90s)

Prep → ceremony tension → peak intimacy → couple → party → quiet ending.

### Music relationship

- Pick tracks with clear intro / build / crest / resolve.
- Land kiss/hug/tears on the crest, not the first bar.
- Music supports story; story must still read muted.

## Module 6 — Finishing (post)

From free post-production curricula outlines:

1. Consistent color / exposure across cuts (we already score color distance).
2. Titles as bookends, not clutter mid-peak.
3. Export for intended platform (social vertical later; current Autolab is cinematic 16:9).

## How this feeds code

| Lesson | Code / craft surface |
|--------|----------------------|
| Phrase cuts | `WEDDING_V3_PHRASE_SYNC` + `plan_story` |
| Reaction after peak | ranking craft heuristics + template `course_kuleshov_peak` |
| Accelerate density | template `course_accelerate_day` |
| Story-first checklist | `docs/MONTAGE_CRAFT.md` + critic craft flags |
| Social 60s spine | preset/template `course_social_60` |

## Human quiz (honest critic)

1. Does shot B change how shot A feels? (Kuleshov)
2. Would a continuity editor accept this jump?
3. Is the peak held, or sprayed?
4. Does the ending resolve, or crash on dance chaos?
5. Would you keep this cut if CapCut effects were removed?

## Non-goals

- No downloading paid course videos
- No claiming we completed Coursera certificates unless we actually enroll/finish UI courses
- No copying proprietary CapCut template packs
