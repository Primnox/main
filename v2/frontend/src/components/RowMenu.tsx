import { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { Panel } from './ui';

/* The row menu is rendered into <body>, not beside the row.
   The conversation list is `overflow-y-auto`, and an absolutely positioned
   child of a scroll container is clipped by it: measured on a row near the
   bottom, the menu overflowed the list by 124px and everything past
   "Archive" — including "Delete permanently" — was simply cut off. A portal
   escapes the clip; fixed coordinates keep it against its button. */
export const MENU_WIDTH = 208;

export function RowMenu({ anchor, onClose, children }: {
  anchor: DOMRect; onClose: () => void; children: any;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [pos, setPos] = useState({ top: anchor.bottom + 4, left: anchor.right - MENU_WIDTH });

  useEffect(() => {
    // Measured after render rather than guessed: the menu's height changes
    // with how many folders exist, so a constant would be wrong the moment
    // someone adds one.
    const height = ref.current?.offsetHeight ?? 0;
    const room = window.innerHeight - anchor.bottom - 8;
    setPos({
      top: height > room ? Math.max(8, anchor.top - height - 4) : anchor.bottom + 4,
      left: Math.max(8, Math.min(anchor.right - MENU_WIDTH, window.innerWidth - MENU_WIDTH - 8)),
    });
  }, [anchor]);

  useEffect(() => {
    // Fixed to the viewport, so a scroll would leave it stranded mid-air.
    const close = () => onClose();
    window.addEventListener('scroll', close, true);
    window.addEventListener('resize', close);
    return () => {
      window.removeEventListener('scroll', close, true);
      window.removeEventListener('resize', close);
    };
  }, [onClose]);

  return createPortal(
    <>
      <div className="fixed inset-0 z-[60]" onClick={onClose} />
      {/* Glass, because this genuinely floats: it is portalled to <body> and
          sits over the conversation it acts on, so keeping a hint of that
          conversation visible behind it is what says "this belongs to that
          row" rather than "a new opaque panel appeared". */}
      <Panel as="div" variant="glass" ref={ref} role="menu"
        style={{ top: pos.top, left: pos.left, width: MENU_WIDTH }}
        className="fixed z-[61] py-1">
        {children}
      </Panel>
    </>,
    document.body,
  );
}

