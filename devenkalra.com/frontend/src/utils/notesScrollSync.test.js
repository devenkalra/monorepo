import assert from 'node:assert/strict';
import { test } from 'node:test';
import { sourceLineProgress } from './notesScrollSync.js';

test('sourceLineProgress stays on an image line until the next block', () => {
  const marks = [{ line: 2 }, { line: 3 }, { line: 20 }];
  assert.deepEqual(sourceLineProgress(marks, 2), { index: 0, t: 0 });
  assert.deepEqual(sourceLineProgress(marks, 3), { index: 1, t: 0 });
  const mid = sourceLineProgress(marks, 11);
  assert.equal(mid.index, 1);
  assert.ok(mid.t > 0.4 && mid.t < 0.6);
});

test('sourceLineProgress does not use page-percent when images dominate height', () => {
  const marks = [{ line: 1 }, { line: 2 }, { line: 3 }];
  assert.equal(sourceLineProgress(marks, 2).index, 1);
  assert.equal(sourceLineProgress(marks, 2).t, 0);
});
