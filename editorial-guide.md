# FP Civic Podcast — Editorial Guide

This file is injected into the script-writing prompt on **every** run. It is the
mechanism by which the podcast "learns": when an episode misses something or gets
something wrong, add a rule here (or a dated note under **Feedback log**) and the
next generation will honor it. No code change needed to adjust editorial behavior.

---

## Episode types

Each meeting cycle produces exactly two episodes:

1. **Meeting Recap (EP1)** — built from the monthly FPCA meeting minutes.
2. **Community Reports (EP2)** — a consolidated digest of the NCC development
   report, the monthly Outreach report, and security/supplemental items from the
   Forester. This replaces the old standalone outreach/NCC episodes.

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

- **Lead with the NCC development report** — zoning cases, variances, and votes.
  State each case plainly (what's proposed, where, and how the committee voted).
- **Outreach report** — cover in detail; this is community-facing and important.
- **Forester security / supplemental** — pull the security patrol updates and any
  items the minutes deferred to the Forester. IGNORE the Forester's masthead,
  officer/representative directory, advertising rates, and ads — those are noise
  from PDF extraction, not content.

---

## Style (both episodes)

- Two co-hosts who BOTH present substantive content — neither is just asking
  questions.
- Warm, natural, and engaging. Use contractions and genuine reactions.
- No sound effects, music cues, stage directions, asterisks, or markdown.
- End with a brief note on how residents can get involved or what's coming up.

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
- Write civic service numbers to be read digit-by-digit: 311 → "three-one-one".
  Phone numbers and street addresses can be written normally.

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
