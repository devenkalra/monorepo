export const FLAT_OUTPUT_FIELDS = [
  { id: 'title', label: 'Title' },
  { id: 'type', label: 'Type' },
  { id: 'start', label: 'Start' },
  { id: 'duration', label: 'Duration' },
  { id: 'end', label: 'End' },
  { id: 'visuals', label: 'Visuals & B-Roll' },
  { id: 'voiceover', label: 'Voiceover & Dialogue' },
  { id: 'music', label: 'Music / Sound' },
  { id: 'fx_cues', label: 'FX Cues' },
  { id: 'notes', label: 'Notes' },
  { id: 'assets', label: 'Assets' },
];

export const ALL_FLAT_FIELD_IDS = FLAT_OUTPUT_FIELDS.map((field) => field.id);

export function normalizeFlatFields(ids) {
  const selected = new Set(ids);
  return ALL_FLAT_FIELD_IDS.filter((id) => selected.has(id));
}

export function parseStoredFlatFields(raw) {
  if (!raw) return ALL_FLAT_FIELD_IDS;
  try {
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return ALL_FLAT_FIELD_IDS;
    return normalizeFlatFields(parsed);
  } catch {
    return ALL_FLAT_FIELD_IDS;
  }
}

export function sceneFlatValue(scene, fieldId) {
  if (fieldId === 'type') return (scene.scene_type || '').trim();
  if (fieldId === 'assets') {
    return (scene.assets || []).map((name) => String(name || '').trim()).filter(Boolean).join(', ');
  }
  return String(scene[fieldId] || '').trim();
}

export function buildFlatBlocks(scenes, fieldIds) {
  const selected = new Set(fieldIds);
  const fields = FLAT_OUTPUT_FIELDS.filter((field) => selected.has(field.id));
  return (scenes || []).map((scene, index) => ({
    heading: `Scene ${index + 1}`,
    rows: fields.flatMap((field) => {
      const value = sceneFlatValue(scene, field.id);
      return value ? [{ id: field.id, label: field.label, value }] : [];
    }),
  }));
}

export function buildFlatOutput(scenes, fieldIds) {
  return buildFlatBlocks(scenes, fieldIds).map((block) => {
    const lines = [block.heading, ...block.rows.map((row) => `${row.label}: ${row.value}`)];
    return lines.join('\n');
  }).join('\n\n---\n\n');
}
