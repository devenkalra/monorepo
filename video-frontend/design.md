# Productions

Script and video-development app (same shape as Trips: JWT, owner-only, SPA + Django API).

Used to plan and track **multiple video productions** (YouTube, Instagram, etc.) from rundown through later launch and performance. Not a video editor.

Suggested names in code: product **Productions**, frontend `productions-frontend` (this folder can be renamed), API `/api/productions/`, UI `/app/productions/`.

---

## Production (one video)

A user has many productions. Each production is one video’s development record.

| Field | Notes |
| --- | --- |
| Title | Required |
| Subtitle | Optional |
| Type | Preset list for now: **Short Form Documentary**, **Long Form Documentary**, **Reel**. More types can be added later. |
| Description | Free text |
| Tags | Many labels for search/filter |
| Status | Active (default) or archived |
| Other meta | Add as needed later (target length, platform, aspect ratio, publish URL, …) |

Actions on a production: **archive**, **delete**, **duplicate** (copy header, tags, scenes, and scene assets; new title like “Copy of …”).

---

## Script (scenes)

The script is an ordered list of scenes. The first scene starts at **0:00**. User can **add**, **delete**, and **reorder** scenes.

### Scene fields

| Field | Notes |
| --- | --- |
| Title | Short scene name |
| Type | Presets to start (Hook, Intro, Preparation, Anticipation, …) plus **free type**. Vocabulary can differ per production. |
| Start | Timecode (see Time) |
| Duration | Timecode |
| End | Timecode |
| Visuals & B-Roll | Text cue (v1) |
| Voiceover & Dialogue | Text cue (v1) |
| Music / Sound | Text cue (v1) |
| Assets | Names needed **for this scene** (not a shared catalog) |
| FX Cues | Text cue (v1) |
| Notes | Free text |

Media files / gallery links are out of scope for v1.

### Time

- Display/edit as timecode. **`hh` and `mm` are optional**. Seconds may have a decimal (`3.5`, `1:03.5`, `02:01:3.5`).
- Normalize internally to fractional seconds.
- First scene **Start** is always **0:00**. Later **Start** values are the previous scene’s **End**.
- **Duration** edited: set this scene’s **End** = Start + Duration. Then for every following scene, set Start = previous End and End = Start + Duration (durations of later scenes stay the same).
- **End** edited: set this scene’s **Duration** = End − Start. Then recompute Start/End of every following scene the same way.
- Reorder, insert, or delete: keep each scene’s Duration; recompute all Start/End from the top (first Start = 0).
- If End would be before Start (negative duration), reject or flag that edit; do not cascade bad times.

---

## UI

- List of productions (search by title/tags, filter by type, show archived).
- **Create with AI**: prompt → LLM JSON rundown (scenes, voiceover, visuals/b-roll, durations). Uses `OPENAI_API_KEY` or `LOCALAI_URL`.
- Production detail: header + **vertical timeline** of scenes (not a spreadsheet).
- Scene cards/rows in time order; drag to reorder; inline edit of cues and times.
- Script view modes: **Compact** (title, start, duration), **Dialogue** (full-width read-only visuals and voiceover), **Expanded** (all fields, editable).

---

## Actions

### 1. Teleprompter script

Concatenate Voiceover & Dialogue in scene order. Prefix each scene’s VO with meta in brackets from scene type, e.g.

```
[HOOK]
line…

[INTRO]
line…
```

Skip scenes with empty VO. Offer copy / download as text.

### 2. Asset todo list

Flatten every scene asset name into a **todo list for this production**: has this asset been **created** for the video?

Status per asset row: **todo** → **in-progress** → **done**.

Same name in two scenes can be one row (dedupe by name, case-insensitive) or two rows — **dedupe by name** so the list is “what still needs to be made,” with a note of which scenes use it.

---

## Later: launch and performance

Not v1, but the production record should be able to grow:

- Launch: publish date, platforms, URLs, checklist (thumbnail, description, premiere).
- Analytics: views, watch time, CTR, or pasted snapshots over time.

Keep the model open; do not build dashboards yet.

---

## Auth and stack (Trips-like)

- Owner-only; JWT / existing bldrdojo login.
- Django app `productions` under `/api/productions/`.
- Vite SPA `/app/productions/`.
- Always on, like Trips (no extra enable flag).

---

## v1 out of scope

- Uploading video/audio files
- Shared asset catalog across productions
- Collaboration / sharing
- Auto-captions, edit decision lists, export to NLE
- Live YouTube/Instagram API analytics
