# FP Civic Podcast — Editorial Guide

This file is injected into the script-writing prompt on **every** run. It is the
mechanism by which the podcast "learns": when an episode misses something or gets
something wrong, add a rule here (or a dated note under **Feedback log**) and the
next generation will honor it. No code change needed to adjust editorial behavior.

---

## Episode

Each meeting cycle produces ONE episode titled **"Forest Park Civic Association
[Month] News"** (e.g., "Forest Park Civic Association July News"). It has two
parts, in this order:

1. **Meeting Recap** — from the monthly FPCA meeting minutes (section rules below).
2. **Community Reports** — the NCC development report, the monthly Outreach report,
   and security/supplemental items from the Forester.

One warm welcome at the very start and one wrap-up at the very end. Transition
smoothly from the recap into the community reports — do NOT start a second intro
partway through.

---

## Meeting Recap (EP1) — INCLUDE these sections

- Guest speakers
- **Community Concerns / Announcements / Ideas — cover EVERY announcement and
  event in full**, each with its date, time, and location. Spell out new venues
  and full addresses (e.g. the NCC Picnic's new location and street address, the
  monthly "Gather at Gabby's", and Beautification Committee deadlines / judge or
  volunteer needs). Never reduce this to a single passing mention.
- Public Relations Officer report
- Forester Editor report
- Civic Action / 311 Officer report
- Committee Reports
- **Old Business — ALWAYS include every Old Business item**, even brief ones. Name
  the specific item and its status/outcome (e.g., the Sign Team's request for 4
  more entrance signs and the city's response). Do not skip or gloss this section.
- New Business / Announcements / Ideas

## Meeting Recap (EP1) — SKIP these

- Any section whose content is essentially "no report."
- The **Secretary** report.
- The **Treasurer** report — UNLESS it contains something genuinely important.
  Specifically DO NOT cover: routine budget reviews, welcoming new business
  members, or expense summaries. If the Treasurer says something materially
  significant (a shortfall, a major new expense, a vote affecting members),
  include just that.
- When a section only says "see the report in the Forester," do not fabricate
  content — that material is covered in EP2 instead.

---

## Community Reports (EP2) — structure

Do NOT summarize the set of reports — walk through EACH item individually and give
it its own moment. Aim for at least 1,300 words.

- **Lead with the NCC development report.** Go through EACH zoning case / variance
  ONE AT A TIME: what's being proposed, the street address, the applicant, and how
  the committee voted (e.g., "approved 12–0"). Do not lump the cases together.
  Refer to them sequentially as **"case one," "case two,"** etc. — do NOT read the
  application/case reference codes (like #GC26-010 or #BZA26-057) or PID numbers
  aloud; they're unlistenable. State each property's street address only ONCE —
  don't repeat the street name (say "4127 East Dublin-Granville Road" once, not
  the road name again separately).
- **Outreach report** — cover EACH initiative/event separately and in detail; this
  is community-facing and important.
- **Forester security / supplemental** — cover EACH security/patrol update and any
  items the minutes deferred to the Forester, one by one. IGNORE the Forester's
  masthead, officer/representative directory, advertising rates, and ads — those
  are noise from PDF extraction, not content.

---

## Style (both episodes)

- Two co-hosts who BOTH present substantive content — neither is just asking
  questions.
- Warm, natural, and engaging. Use contractions and genuine reactions.
- No sound effects, music cues, stage directions, asterisks, or markdown.
- End with a brief note on how residents can get involved or what's coming up.

## Opening

- Open with a simple welcome and the update month, e.g. "Hey everybody, welcome to
  the Forest Park Civic Association News podcast. Today we're giving you an update
  for [Month Year]."
- The hosts are UNNAMED narrators. Never have them introduce themselves, use names,
  or say "I'm your host" / "I'm here with my co-host" — they aren't real people.

## Conversational style (make it feel like a real chat, not a reading)

- The hosts genuinely converse — they do NOT take turns reading blocks. Include
  real reactions ("Oh interesting," "Right, and here's what matters…"), short
  follow-up questions, and moments where one builds on or gently pushes back on
  the other.
- Vary the rhythm: mix quick one- or two-line exchanges with longer explanations.
  A punchy reaction line right after a big point makes it feel alive.
- Use natural discourse markers (well, so, actually, you know, honestly) —
  sparingly and naturally, not in every line.
- Hand topics off smoothly ("That reminds me…", "Speaking of which…") instead of
  announcing each section like an agenda item.
- Warm and human throughout — like two neighbors who genuinely care about Forest
  Park talking over coffee.

## Order & spoken-word rules (for the audio)

- Cover the included sections in the ORDER listed above. Do NOT save announcements
  or events for the very end — Community Concerns/Announcements comes early, right
  after guest speakers.
- Never speak URLs or email addresses aloud. Refer to them naturally instead ("on
  the county auditor's website," "reach out by email") — never read the address.
- Transition into the community reports ONLY ONCE. The meeting-recap segment ends
  by handing off (e.g., "Now let's get into the community reports"); the reports
  segment then starts DIRECTLY with the first report. Do NOT have the second host
  also announce "community reports" — no redundant double-intro.
- Pronunciation & wording (also enforced in code, but write it this way):
  - "311" → "three-one-one"; "614" → "six-one-four" (digit-by-digit, never "hundred").
  - "161" → "one-sixty-one" (smooth, no pause); "RT 161" / "Route 161" → "route one-sixty-one".
  - "BZA variance" → "zoning variance"; "C-2 district" → "commercial district".
  - "security and supplemental items" → "supplemental security items".

## Depth & length (IMPORTANT — do not summarize)

- Write a FULL episode: **at least 1,200 words** for the Meeting Recap and **at
  least 1,300 words** for the Community Reports digest. Longer is fine.
- Give EVERY included section real depth: **2 to 4 back-and-forth exchanges per
  section**, not a single sentence. Cover the specifics — names, dates, numbers,
  locations, decisions/votes — and briefly say what each item means for residents.
- Do NOT compress several sections into one line, and do not rush to wrap up.
  Only end after every included item has been genuinely discussed.

---

## Feedback log

_Add dated entries as feedback comes in. The most recent guidance wins._

- **2026-07-21:** First July episodes ran too short (~3.5 min each). Ryan wants
  fuller episodes — added the Depth & length section above (1,200+/1,300+ words,
  2–4 exchanges per section).
- **2026-07-21:** The July recap dropped the Old Business "Sign Team" item. Old
  Business must ALWAYS be covered — emphasized in the INCLUDE list above.
- **2026-07-21:** A host tried to read a full URL aloud (unlistenable) and said
  "311" as "three hundred eleven." Added spoken-word rules: no URLs/emails aloud,
  and 311 → "three-one-one" (also enforced in code via normalize_for_speech).
- **2026-07-21:** Community Concerns/Announcements got dumped at the very end and
  was incomplete (missed NCC Picnic new location/address, Gather at Gabby's,
  Beautification deadline/judge). Added order rule (keep section order) and
  required full coverage of every event with date/time/location.
- **2026-07-22:** Ryan loved both July episodes. Two changes: (1) refer to NCC
  cases as "case one/two," never read the reference codes; (2) COMBINE the meeting
  recap and community reports into ONE episode titled "Forest Park Civic
  Association [Month] News," now and going forward.
- **2026-07-22:** Drop "I'm your host" and any host self-introduction/names — the
  hosts are unnamed narrators. Open with a simple welcome + the update month (see
  Opening section). Applies going forward; the July episode was NOT re-run.
- **2026-07-24:** Batch of pronunciation/wording fixes (see Order & spoken-word
  rules) — 161→"one-sixty-one", RT 161→"route one-sixty-one", 614→"six-one-four",
  BZA variance→"zoning variance", C-2 district→"commercial district", "security
  and supplemental items"→"supplemental security items"; plus: don't double-
  announce the community-reports transition, and don't repeat a property's street
  name in the NCC section.
