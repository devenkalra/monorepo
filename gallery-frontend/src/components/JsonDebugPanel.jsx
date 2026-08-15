import React, { useRef, useState } from 'react';

export default function JsonDebugPanel({ title = 'Show JSON', data, onClose }) {
  const [pos, setPos] = useState({ x: 48, y: 72 });
  const dragRef = useRef(null);
  const text = JSON.stringify(data ?? {}, null, 2);

  const onPointerDown = (e) => {
    if (e.button !== 0) return;
    dragRef.current = { id: e.pointerId, dx: e.clientX - pos.x, dy: e.clientY - pos.y };
    e.currentTarget.setPointerCapture(e.pointerId);
  };

  const onPointerMove = (e) => {
    const drag = dragRef.current;
    if (!drag || drag.id !== e.pointerId) return;
    setPos({
      x: Math.max(0, e.clientX - drag.dx),
      y: Math.max(0, e.clientY - drag.dy),
    });
  };

  const onPointerUp = (e) => {
    if (dragRef.current?.id === e.pointerId) dragRef.current = null;
  };

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      /* ignore */
    }
  };

  return (
    <div
      className="fixed z-50 flex w-[min(420px,calc(100vw-24px))] flex-col overflow-hidden rounded-lg border border-stone-300 bg-white"
      style={{ left: pos.x, top: pos.y, maxHeight: '70vh' }}
    >
      <div
        className="flex cursor-grab items-center gap-2 border-b bg-stone-50 px-2 py-1.5 active:cursor-grabbing"
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={onPointerUp}
      >
        <span className="flex-1 text-xs font-medium uppercase tracking-wide text-stone-600">{title}</span>
        <button
          type="button"
          className="rounded border px-1.5 py-0.5 text-[11px]"
          onPointerDown={(e) => e.stopPropagation()}
          onClick={copy}
        >
          Copy
        </button>
        <button
          type="button"
          className="rounded border px-1.5 py-0.5 text-[11px]"
          onPointerDown={(e) => e.stopPropagation()}
          onClick={onClose}
        >
          Close
        </button>
      </div>
      <pre className="min-h-0 flex-1 overflow-auto p-2 text-[11px] leading-snug text-stone-800">{text}</pre>
    </div>
  );
}
