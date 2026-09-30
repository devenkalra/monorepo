import assert from 'node:assert/strict';
import test from 'node:test';
import {
  ALL_FLAT_FIELD_IDS,
  buildFlatOutput,
  normalizeFlatFields,
  parseStoredFlatFields,
} from './flatOutput.js';

const scenes = [
  {
    title: 'Open',
    scene_type: 'Hook',
    start: '0:00',
    duration: '8',
    end: '8',
    visuals: 'Face on the ridge',
    voiceover: 'I did not pack enough water.',
    music: 'thin drone',
    fx_cues: '',
    notes: '  ',
    assets: ['Drone shot', 'Map'],
  },
  {
    title: '',
    scene_type: 'Segment',
    start: '8',
    duration: '6',
    end: '14',
    visuals: '',
    voiceover: '',
    music: '',
    fx_cues: '',
    notes: '',
    assets: [],
  },
];

test('includes only populated selected fields', () => {
  assert.equal(
    buildFlatOutput(scenes, ALL_FLAT_FIELD_IDS),
    [
      'Scene 1',
      'Title: Open',
      'Type: Hook',
      'Start: 0:00',
      'Duration: 8',
      'End: 8',
      'Visuals & B-Roll: Face on the ridge',
      'Voiceover & Dialogue: I did not pack enough water.',
      'Music / Sound: thin drone',
      'Assets: Drone shot, Map',
      '',
      '---',
      '',
      'Scene 2',
      'Type: Segment',
      'Start: 8',
      'Duration: 6',
      'End: 14',
    ].join('\n'),
  );
});

test('omits deselected fields', () => {
  assert.equal(
    buildFlatOutput(scenes, ['title', 'voiceover']),
    'Scene 1\nTitle: Open\nVoiceover & Dialogue: I did not pack enough water.\n\n---\n\nScene 2',
  );
});

test('parses stored selection and ignores unknown ids', () => {
  assert.deepEqual(parseStoredFlatFields(null), ALL_FLAT_FIELD_IDS);
  assert.deepEqual(parseStoredFlatFields('["voiceover","nope","title"]'), ['title', 'voiceover']);
  assert.deepEqual(parseStoredFlatFields('[]'), []);
  assert.deepEqual(parseStoredFlatFields('{'), ALL_FLAT_FIELD_IDS);
  assert.deepEqual(normalizeFlatFields(['end', 'title', 'end']), ['title', 'end']);
});
