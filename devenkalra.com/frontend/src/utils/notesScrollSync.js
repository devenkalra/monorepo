export function parseLineHeight(style) {
  const raw = parseFloat(style.lineHeight);
  if (Number.isFinite(raw) && style.lineHeight !== 'normal') return raw;
  const font = parseFloat(style.fontSize);
  return (Number.isFinite(font) ? font : 14) * 1.5;
}

/** 1-based source line at the top of a non-wrapping textarea. */
export function textareaTopSourceLine(textarea) {
  if (!textarea) return 1;
  const style = window.getComputedStyle(textarea);
  const lineHeight = parseLineHeight(style);
  return Math.max(1, Math.floor(textarea.scrollTop / lineHeight) + 1);
}

export function collectSourceLineMarks(preview) {
  return [...preview.querySelectorAll('[data-source-line]')]
    .map((el) => ({ el, line: Number(el.getAttribute('data-source-line')) || 0 }))
    .filter((m) => m.line > 0)
    .sort((a, b) => a.line - b.line);
}

/** Which marked blocks bracket this source line, and how far between them. */
export function sourceLineProgress(marks, line) {
  if (!marks.length) return null;
  let i = 0;
  while (i + 1 < marks.length && marks[i + 1].line <= line) i += 1;
  const a = marks[i];
  const b = marks[i + 1];
  if (!b || line <= a.line) return { index: i, t: 0 };
  return { index: i, t: (line - a.line) / (b.line - a.line) };
}

/**
 * Scroll preview so the block for `line` is at the top, interpolating between
 * neighboring blocks. A one-line image maps to that image, not a % of the page.
 */
export function scrollPreviewToSourceLine(preview, line) {
  const marks = collectSourceLineMarks(preview);
  const progress = sourceLineProgress(marks, line);
  if (!progress) return false;

  const a = marks[progress.index];
  const b = marks[progress.index + 1];
  const previewTop = preview.getBoundingClientRect().top;
  const topOf = (el) => el.getBoundingClientRect().top - previewTop + preview.scrollTop;
  const aTop = topOf(a.el);
  if (!b || progress.t <= 0) {
    preview.scrollTop = Math.max(0, aTop);
    return true;
  }
  preview.scrollTop = Math.max(0, aTop + (topOf(b.el) - aTop) * progress.t);
  return true;
}

/** For raw HTML previews: assign source lines by tag order in the HTML string. */
export function stampHtmlSourceLines(preview, htmlSource) {
  if (!preview || !htmlSource) return;
  const tags = preview.querySelectorAll(
    'h1,h2,h3,h4,h5,h6,p,img,iframe,pre,blockquote,ul,ol,table,hr,figure'
  );
  const source = String(htmlSource);
  const lower = source.toLowerCase();
  let searchFrom = 0;
  tags.forEach((el) => {
    if (el.hasAttribute('data-source-line')) return;
    const tag = el.tagName.toLowerCase();
    const idx = lower.indexOf(`<${tag}`, searchFrom);
    if (idx < 0) return;
    el.setAttribute('data-source-line', String(source.slice(0, idx).split('\n').length));
    searchFrom = idx + 1;
  });
}
