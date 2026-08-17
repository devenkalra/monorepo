export function parseLineHeight(style) {
  const raw = parseFloat(style.lineHeight);
  if (Number.isFinite(raw) && style.lineHeight !== 'normal') return raw;
  const font = parseFloat(style.fontSize);
  return (Number.isFinite(font) ? font : 14) * 1.5;
}

export function sourceLineFromOffset(text, offset) {
  return (String(text).slice(0, Math.max(0, offset)).match(/\n/g) || []).length + 1;
}

let wrapMirror;

function wrappedLineMirror(textarea, style, width) {
  if (!wrapMirror) {
    wrapMirror = document.createElement('div');
    wrapMirror.setAttribute('aria-hidden', 'true');
    wrapMirror.style.cssText =
      'position:absolute;left:-9999px;top:0;visibility:hidden;pointer-events:none;white-space:pre-wrap;overflow-wrap:anywhere;word-wrap:break-word;';
    document.body.appendChild(wrapMirror);
  }
  wrapMirror.style.width = `${width}px`;
  wrapMirror.style.font = style.font;
  wrapMirror.style.fontSize = style.fontSize;
  wrapMirror.style.fontFamily = style.fontFamily;
  wrapMirror.style.lineHeight = style.lineHeight;
  wrapMirror.style.letterSpacing = style.letterSpacing;
  wrapMirror.style.tabSize = style.tabSize;
  return wrapMirror;
}

export function textareaTopSourceLine(textarea) {
  if (!textarea) return 1;
  const style = window.getComputedStyle(textarea);
  const lineHeight = parseLineHeight(style);
  const padX = (parseFloat(style.paddingLeft) || 0) + (parseFloat(style.paddingRight) || 0);
  const width = Math.max(1, textarea.clientWidth - padX);
  const target = textarea.scrollTop;
  const lines = textarea.value.split('\n');
  const mirror = wrappedLineMirror(textarea, style, width);
  let y = 0;
  for (let i = 0; i < lines.length; i += 1) {
    mirror.textContent = lines[i] || ' ';
    const h = Math.max(lineHeight, mirror.offsetHeight);
    if (y + h > target + 0.5) return i + 1;
    y += h;
  }
  return Math.max(1, lines.length);
}

export function collectSourceLineMarks(preview) {
  return [...preview.querySelectorAll('[data-source-line]')]
    .map((el) => ({ el, line: Number(el.getAttribute('data-source-line')) || 0 }))
    .filter((m) => m.line > 0)
    .sort((a, b) => a.line - b.line);
}

export function sourceLineProgress(marks, line) {
  if (!marks.length) return null;
  let i = 0;
  while (i + 1 < marks.length && marks[i + 1].line <= line) i += 1;
  const a = marks[i];
  const b = marks[i + 1];
  if (!b || line <= a.line) return { index: i, t: 0 };
  return { index: i, t: (line - a.line) / (b.line - a.line) };
}

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

export function rehypeSourceLines() {
  const tags = new Set([
    'p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'li', 'pre', 'blockquote',
    'table', 'hr', 'img', 'ul', 'ol',
  ]);
  return (tree) => {
    const walk = (node) => {
      const line = node.position?.start?.line;
      if (node.type === 'element' && tags.has(node.tagName) && line) {
        node.properties = node.properties || {};
        if (node.properties['data-source-line'] == null) {
          node.properties['data-source-line'] = line;
        }
      }
      (node.children || []).forEach(walk);
    };
    walk(tree);
  };
}
