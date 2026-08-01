# devenkalra.com — Product brief

Personal website for Deven Kalra (not a multi-user SaaS). Share professional background, interests, writing, and small tools.

**Architecture and implementation details:** see [`DESIGN.md`](./DESIGN.md).

---

## Who Am I?

Early-retired engineering executive; work at Hewlett-Packard, Adaptive Media/Vuent, Langoo, VeriSign, Stratify/Iron Mountain, AtHoc, and Google. Interests include photography, writing, woodworking, travel, and more.

---

## Content areas (intent)

1. Professional life  
2. Personal life  
   - Content — video transcripts, technical papers, book summaries/reviews, Indian music, cooking  
   - Workflow — ideas, ongoing projects (e.g. photography, video AI)  
   - Custom apps — timers, exercise planner, Notes, ClickUp-backed projects/contacts, etc.  
3. Voyages / articles (blog)  
4. Notebook — including **Notes** (multi-level folders of selected pages)

The live menu is data-driven (`MenuItem` tree) and may diverge from this outline as content evolves.

---

## Product requirements

| Requirement | Status |
|-------------|--------|
| Hierarchical dropdown menu | Done (`MenuItem`) |
| Breadcrumbs | Done |
| Same page under multiple menu branches | Done |
| Protected pages | Done via `roles_with_access` + optional `allowed_emails` (not a separate password-per-page flow) |
| Markdown / HTML pages | Done (`render_as_html`) |
| Admin live preview | Done |
| Notes folder UI with preview + URL state | Done (slug `notes`) |

---

## Ideas / backlog

- Category: Video  
- Status: _(open)_  
