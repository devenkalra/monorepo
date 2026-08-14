/** Shared Ken Burns math (FolderBrowser-compatible). */

export function clamp01(v) {
  return Math.min(1, Math.max(0, Number(v) || 0));
}

export function parseViewTime(time, duration) {
  if (typeof time === 'string' && time.endsWith('%')) {
    return (parseFloat(time) / 100) * (duration || 0);
  }
  return Number(time) || 0;
}

/**
 * Interpolate between keyframes for visually linear camera motion.
 *
 * Independent lerp of (x,y) and zoom makes screen paths parabolic (image "arcs"
 * then settles). Instead, lerp zoom/scale normally and lerp focus *weighted by
 * zoom* so screen(p) = center + scale*(p-focus) stays linear in t.
 *
 * @param {'linear'|'smoothstep'} easing  time easing only (default linear)
 */
export const DEFAULT_VIEW = {
  zoom: 1,
  zoomX: 1,
  zoomY: 1,
  x: 0.5,
  y: 0.5,
  rotation: 0,
  opacity: 1,
  pitch: 0,
  yaw: 0,
  anchorX: 0.5,
  anchorY: 0.5,
  cropLeft: 0,
  cropRight: 0,
  cropTop: 0,
  cropBottom: 0,
};

export function viewZoomX(v) {
  const n = Number(v?.zoomX ?? v?.zoom);
  return Number.isFinite(n) && n > 0 ? Math.max(0.2, n) : 1;
}

export function viewZoomY(v) {
  const n = Number(v?.zoomY ?? v?.zoom);
  return Number.isFinite(n) && n > 0 ? Math.max(0.2, n) : 1;
}

function parseKeyframe(v, duration) {
  const x = clamp01(v.x ?? 0.5);
  const y = clamp01(v.y ?? 0.5);
  const zoomX = viewZoomX(v);
  const zoomY = viewZoomY(v);
  return {
    ...v,
    time: parseViewTime(v.time, duration),
    zoom: zoomX,
    zoomX,
    zoomY,
    x,
    y,
    rotation: Number(v.rotation) || 0,
    opacity: Number.isFinite(Number(v.opacity)) ? clamp01(v.opacity) : 1,
    pitch: Number(v.pitch) || 0,
    yaw: Number(v.yaw) || 0,
    anchorX: clamp01(v.anchorX ?? x),
    anchorY: clamp01(v.anchorY ?? y),
    cropLeft: clamp01(v.cropLeft),
    cropRight: clamp01(v.cropRight),
    cropTop: clamp01(v.cropTop),
    cropBottom: clamp01(v.cropBottom),
  };
}

export function sampleView(views, elapsedSec, duration = 10, easing = 'linear') {
  if (!views?.length) {
    return { ...DEFAULT_VIEW };
  }
  const parsed = views.map((v) => parseKeyframe(v, duration)).sort((a, b) => a.time - b.time);

  if (elapsedSec <= parsed[0].time) return { ...parsed[0] };
  if (elapsedSec >= parsed[parsed.length - 1].time) return { ...parsed[parsed.length - 1] };

  let i = 0;
  while (i < parsed.length - 1 && parsed[i + 1].time < elapsedSec) i += 1;
  const a = parsed[i];
  const b = parsed[i + 1];
  const span = Math.max(0.0001, b.time - a.time);
  let t = clamp01((elapsedSec - a.time) / span);
  if (easing === 'smoothstep') {
    t = t * t * (3 - 2 * t);
  }
  const lerp = (x, y) => x + (y - x) * t;

  const zoomX = lerp(a.zoomX, b.zoomX);
  const zoomY = lerp(a.zoomY, b.zoomY);
  // Scale-weighted focus: f(t) = lerp(z0*f0, z1*f1) / z(t)
  const x = zoomX > 1e-6 ? lerp(a.zoomX * a.x, b.zoomX * b.x) / zoomX : lerp(a.x, b.x);
  const y = zoomY > 1e-6 ? lerp(a.zoomY * a.y, b.zoomY * b.y) / zoomY : lerp(a.y, b.y);

  return {
    zoom: zoomX,
    zoomX,
    zoomY,
    x: clamp01(x),
    y: clamp01(y),
    rotation: lerp(a.rotation, b.rotation),
    opacity: lerp(a.opacity, b.opacity),
    pitch: lerp(a.pitch, b.pitch),
    yaw: lerp(a.yaw, b.yaw),
    anchorX: clamp01(lerp(a.anchorX, b.anchorX)),
    anchorY: clamp01(lerp(a.anchorY, b.anchorY)),
    cropLeft: clamp01(lerp(a.cropLeft, b.cropLeft)),
    cropRight: clamp01(lerp(a.cropRight, b.cropRight)),
    cropTop: clamp01(lerp(a.cropTop, b.cropTop)),
    cropBottom: clamp01(lerp(a.cropBottom, b.cropBottom)),
    time: elapsedSec,
  };
}

/**
 * Apply Ken Burns transform: focus (x,y) stays at stage center while zooming.
 * zoom=1 fits the entire image (contain); zoom>1 zooms into the focus point.
 * Media element should use natural width/height (not CSS object-fit).
 */
export function applyKenBurnsTransform(mediaEl, stageEl, view, natural) {
  if (!mediaEl || !stageEl || !natural?.width || !natural?.height) return;

  const stageWidth = stageEl.clientWidth || 1;
  const stageHeight = stageEl.clientHeight || 1;
  // Contain: full image visible at zoom 1 (letterboxed as needed).
  const fitScale = Math.min(stageWidth / natural.width, stageHeight / natural.height);
  const scaleX = fitScale * viewZoomX(view);
  const scaleY = fitScale * viewZoomY(view);
  const focusX = natural.width * clamp01(view.x);
  const focusY = natural.height * clamp01(view.y);
  const originX = natural.width * clamp01(view.anchorX ?? view.x);
  const originY = natural.height * clamp01(view.anchorY ?? view.y);
  const rotation = Number.isFinite(Number(view.rotation)) ? Number(view.rotation) : 0;
  const pitch = Number.isFinite(Number(view.pitch)) ? Number(view.pitch) : 0;
  const yaw = Number.isFinite(Number(view.yaw)) ? Number(view.yaw) : 0;
  const opacity = Number.isFinite(Number(view.opacity)) ? clamp01(view.opacity) : 1;
  const cropL = clamp01(view.cropLeft);
  const cropR = clamp01(view.cropRight);
  const cropT = clamp01(view.cropTop);
  const cropB = clamp01(view.cropBottom);

  stageEl.style.perspective = `${Math.max(stageWidth, stageHeight)}px`;
  stageEl.style.perspectiveOrigin = '50% 50%';
  mediaEl.style.position = 'absolute';
  mediaEl.style.left = '0';
  mediaEl.style.top = '0';
  mediaEl.style.width = `${natural.width}px`;
  mediaEl.style.height = `${natural.height}px`;
  mediaEl.style.maxWidth = 'none';
  mediaEl.style.maxHeight = 'none';
  mediaEl.style.objectFit = 'fill';
  mediaEl.style.backfaceVisibility = 'hidden';
  mediaEl.style.clipPath =
    cropL || cropR || cropT || cropB
      ? `inset(${cropT * 100}% ${cropR * 100}% ${cropB * 100}% ${cropL * 100}%)`
      : 'none';
  mediaEl.style.transformOrigin = `${originX}px ${originY}px`;
  mediaEl.style.transform = `translate3d(${stageWidth / 2 - focusX}px, ${stageHeight / 2 - focusY}px, 0) rotateX(${pitch}deg) rotateY(${yaw}deg) rotateZ(${rotation}deg) scale(${scaleX}, ${scaleY})`;
  mediaEl.style.opacity = String(opacity);
}
