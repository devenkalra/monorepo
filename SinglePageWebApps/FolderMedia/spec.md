Updated todo list

You want a clean, partitioned product-like gallery UX with distinct Load and Edit modes centered around thumbnails, so I’m drafting a concrete design spec you can approve before any implementation changes. I’ll keep it focused on layout, interaction model, information architecture, and phased delivery criteria.

**Design Spec: Partitioned Media Gallery UX (Pre-Implementation)**

## 1. Product Vision
Build a local-first media gallery that feels like a dedicated photo product:
1. Thumbnail gallery is always the visual center and primary interaction surface.
2. Work is partitioned into explicit modes so users are never overloaded.
3. Load, Organize, and Edit actions are contextual and separated.
4. The UI remains calm and minimal while still powerful for config management.

## 2. Core UX Principles
1. One primary job per mode.
2. Keep the center column stable across all modes.
3. Controls appear progressively, not all at once.
4. Editing is explicit with draft state and save/export actions.
5. Fast keyboard flow for power users, obvious buttons for casual users.

## 3. Information Architecture
1. App Shell
2. Header Bar
3. Left Utility Rail (mode switch + context tools)
4. Center Gallery Stage (thumbnail grid, always present)
5. Right Context Panel (mode-specific details)
6. Overlay Layer (lightbox/fullscreen and modal dialogs)

## 4. Mode Model
1. Browse Mode
2. Load Mode
3. Edit Mode
4. Review/Export Mode

### 4.1 Browse Mode
1. Purpose: discover and preview media.
2. Center: thumbnail grid and search/filter strip.
3. Left rail: mode switch, album/tag quick filters.
4. Right panel: selected item metadata read-only.
5. Primary actions: open preview, multi-select, quick filter.

### 4.2 Load Mode
1. Purpose: ingest config and folders.
2. Right panel becomes Load Workspace:
3. Config source:
4. Choose JSON file.
5. Optional path loader.
6. Folder import:
7. Add one or multiple folders.
8. Validation:
9. Missing path warnings.
10. Unsupported extension summary.
11. Center gallery remains visible to confirm incoming items.

### 4.3 Edit Mode
1. Purpose: curate ordering, album assignment, tags, and labels.
2. Right panel becomes Edit Inspector:
3. Selection summary (single or multi-select).
4. Item order controls.
5. Album assignment.
6. Tag editor.
7. Name/title editor.
8. Changes are staged in memory with visible unsaved status.
9. Center supports selection and order visualization.

### 4.4 Review/Export Mode
1. Purpose: finalize and write updated config.
2. Right panel shows diff-like summary:
3. Reordered count.
4. Tag changes count.
5. Album changes count.
6. Export actions:
7. Download JSON.
8. Save As.
9. Filename input and schema validation pass/fail.
10. Clear messaging on browser overwrite limitations.

## 5. Layout Spec
1. Desktop grid:
2. Left rail: fixed narrow column for mode switch and global filters.
3. Center stage: largest area, min 60% width for thumbnails.
4. Right panel: fixed inspector width for mode tools.
5. Mobile/tablet behavior:
6. Center remains dominant.
7. Left and right panels collapse into bottom sheets/tabs.
8. Mode switch becomes segmented control at top.
9. Keep one-tap access to lightbox and edit save actions.

## 6. Visual Hierarchy
1. Primary emphasis: thumbnails.
2. Secondary: top utility strip (search, sort, view options).
3. Tertiary: side panels with mode-specific controls.
4. Avoid dense control clusters in the gallery area.
5. Use section cards with clear headings and short helper text.
6. Show only relevant controls for active mode.

## 7. Component Inventory
1. Mode Switcher
2. Gallery Grid
3. Thumbnail Card
4. Selection Toolbar
5. Filter Bar (album, tags, search)
6. Load Panel
7. Edit Inspector
8. Change Summary Panel
9. Save/Export Panel
10. Lightbox Viewer
11. Toast/Status System
12. Validation Banner

## 8. Interaction Flows

### 8.1 First-Time Load Flow
1. Enter Load Mode.
2. Select config and/or import folders.
3. Validate and show ingestion summary.
4. Return to Browse automatically with loaded gallery.

### 8.2 Curation Flow
1. Enter Edit Mode.
2. Select one or many items from center.
3. Apply album and tags.
4. Reorder selected or focused item.
5. See unsaved draft badge in header.

### 8.3 Save Flow
1. Enter Review/Export Mode.
2. Inspect change summary.
3. Export via Download or Save As.
4. Show success state and last export timestamp.

## 9. Selection and Ordering Model
1. Single click: select item.
2. Shift click: range select.
3. Ctrl/Cmd click: add/remove from selection.
4. Reorder methods:
5. Move Up/Down/Top/Bottom.
6. Optional drag-and-drop in a later phase.
7. Ordering is config-only and deterministic in exported JSON.

## 10. Tag and Album Editing Rules
1. Tags are normalized:
2. Trim whitespace.
3. De-duplicate case-insensitively.
4. Preserve display casing from first entry.
5. Album assignment:
6. Assign existing album.
7. Create new album inline.
8. Album metadata can include album-level tags.
9. Multi-select edits apply bulk operations safely.

## 11. State and Persistence
1. Runtime state:
2. Loaded items.
3. Mode.
4. Selection.
5. Draft edits.
6. Persistence options:
7. Session-only by default.
8. Optional local preference persistence for panel state, view type, last mode.
9. Unsaved changes indicator must be global and persistent in header.

## 12. Error and Empty States
1. Empty gallery state with clear next action to Load Mode.
2. Invalid JSON state with targeted error message.
3. Missing media path state with non-blocking warnings.
4. Save blocked state with fallback action.
5. Partial import state with success-plus-warning summary.

## 13. Accessibility and Keyboard
1. Full keyboard navigation through gallery and inspector.
2. Visible focus rings.
3. ARIA labels for mode switch and critical actions.
4. Keyboard shortcuts:
5. B for Browse mode.
6. L for Load mode.
7. E for Edit mode.
8. R for Review mode.
9. F for fullscreen in lightbox.
10. Esc to close overlays and exit fullscreen.

## 14. Performance Targets
1. Smooth grid interactions at 1,000+ items.
2. Lazy thumbnail rendering and media loading.
3. Debounced search/filter.
4. Non-blocking update of change summaries.

## 15. Proposed Implementation Phases
1. Phase 1: Layout partitioning and mode shell.
2. Phase 2: Load Mode panel integration.
3. Phase 3: Edit Mode inspector and draft state.
4. Phase 4: Review/Export mode and change summary.
5. Phase 5: polish, accessibility, keyboard, and performance tuning.

## 16. Acceptance Criteria (Design Sign-Off)
1. Center gallery remains the dominant area in all modes.
2. User can switch modes without losing context or selection unintentionally.
3. Only mode-relevant controls are visible.
4. Editing and export actions are clearly separated.
5. Save/export flow is understandable and reliable under file protocol constraints.

If this direction looks right, next step is to convert this into a clickable wireframe map (screen-by-screen with component placements) and then implement in phased PR-sized chunks.