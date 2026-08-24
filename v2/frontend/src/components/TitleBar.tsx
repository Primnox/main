import { useEffect, useState } from 'react';
import { Minus, Square, Copy, X } from 'lucide-react';

/* The window chrome, because `tauri.conf.json` sets `decorations: false`.
 *
 * That flag removes the operating system's title bar — the strip carrying the
 * window title and the minimise, maximise and close buttons — and Tauri does
 * not replace it. Built as it stands today, Primnox opens a 1280x800 window
 * that cannot be moved, cannot be minimised, cannot be maximised, and cannot
 * be closed except through Task Manager. The frameless look is a deliberate
 * choice; the missing controls are the bill that comes with it.
 *
 * Three decisions worth writing down:
 *
 *   The bar renders EVERYWHERE, the controls only under Tauri. Development
 *   runs in a browser at :5273, and a bar that appeared only in the packaged
 *   app would mean never seeing your own layout while building it — every
 *   vertical measurement would be 36px out until release day. The buttons are
 *   the part that has no meaning in a tab, so the buttons are the part that
 *   goes away.
 *
 *   Drag is an attribute on the elements the pointer actually lands on, not
 *   on the bar alone. `data-tauri-drag-region` is checked against the event
 *   target, so a title span without it is a dead patch in the middle of the
 *   drag surface — the user grabs the window by its name and nothing happens.
 *
 *   The API is imported dynamically, inside the handlers. A static import
 *   evaluates in the browser too, and `getCurrentWindow()` outside Tauri
 *   throws; keeping it lazy means a browser never touches it and a missing
 *   package costs the buttons rather than the whole app.
 */

/* Tauri v2 exposes this on the window object of a real webview and nowhere
 * else. Checked once at module scope: it cannot change during a session, and
 * re-checking per render would suggest it might. */
const IN_TAURI = typeof window !== 'undefined'
  && '__TAURI_INTERNALS__' in window;

async function appWindow() {
  const { getCurrentWindow } = await import('@tauri-apps/api/window');
  return getCurrentWindow();
}

export function TitleBar() {
  const [maximized, setMaximized] = useState(false);

  useEffect(() => {
    if (!IN_TAURI) return;
    let stop: (() => void) | undefined;
    let cancelled = false;

    (async () => {
      const win = await appWindow();
      const sync = async () => setMaximized(await win.isMaximized());
      await sync();
      // The window can be maximised without this component asking — a double
      // click on the drag region, the Windows snap gesture, Win+Up. Without
      // listening, the button keeps showing "maximise" on a maximised window.
      const unlisten = await win.onResized(sync);
      if (cancelled) unlisten();
      else stop = unlisten;
    })();

    return () => { cancelled = true; stop?.(); };
  }, []);

  return (
    <header
      data-tauri-drag-region
      className="flex h-9 shrink-0 select-none items-center justify-between
                 border-b border-surface-brd bg-surface pl-4"
    >
      {/* `decorations: false` also removes the OS window title, so the app has
          to say its own name somewhere. This is that somewhere — deliberately
          quiet, because the rail's mark sits directly beneath it and two loud
          logos stacked would read as a mistake. */}
      <span
        data-tauri-drag-region
        className="text-[11px] font-medium tracking-wide text-muted"
      >
        Primnox
      </span>

      {IN_TAURI && (
        <div className="flex items-center">
          <Control
            label="Minimise"
            onClick={async () => (await appWindow()).minimize()}
          >
            <Minus size={14} strokeWidth={2} aria-hidden />
          </Control>

          <Control
            label={maximized ? 'Restore' : 'Maximise'}
            onClick={async () => (await appWindow()).toggleMaximize()}
          >
            {/* Two glyphs, because one is a lie half the time: a maximised
                window's button restores it, and showing the same square for
                both states hides which way it will go. */}
            {maximized
              ? <Copy size={12} strokeWidth={2} aria-hidden />
              : <Square size={12} strokeWidth={2} aria-hidden />}
          </Control>

          <Control
            label="Close"
            danger
            onClick={async () => (await appWindow()).close()}
          >
            <X size={15} strokeWidth={2} aria-hidden />
          </Control>
        </div>
      )}
    </header>
  );
}

/* One control. 46px wide because that is what Windows uses, and a titlebar
 * button narrower than the system's reads as cramped next to every other app
 * on the same desktop.
 *
 * Deliberately NOT carrying `data-tauri-drag-region`: an element inside the
 * drag surface that keeps the attribute is dragged rather than clicked, so
 * the close button would move the window instead of closing it. */
function Control({
  label, onClick, danger, children,
}: {
  label: string;
  onClick: () => void;
  danger?: boolean;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={label}
      title={label}
      className={`grid h-9 w-[46px] place-items-center text-muted
                  transition-colors focus-visible:outline-none
                  focus-visible:ring-1 focus-visible:ring-inset
                  focus-visible:ring-accent
                  ${danger
                    ? 'hover:bg-red-600 hover:text-white'
                    : 'hover:bg-surface-brd hover:text-on-surface'}`}
    >
      {children}
    </button>
  );
}
