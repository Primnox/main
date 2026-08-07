//! Main-window / island-overlay mode transitions.
//!
//! Ports `enterIslandMode` / `exitIslandMode` and the window lifecycle rules
//! from `public/electron.cjs`.

use std::sync::atomic::{AtomicBool, AtomicU32, Ordering};
use tauri::{AppHandle, Manager, PhysicalPosition, WebviewWindow};

use crate::channels::{island_x, ISLAND_WINDOW, MAIN_WINDOW};

/// Width of the island overlay window. Must match `tauri.conf.json`.
pub const ISLAND_WIDTH: u32 = 900;

/// Runtime flags shared across commands and tray handlers.
#[derive(Debug, Default)]
pub struct AppState {
    /// True while the app is folded down to the island pill.
    pub island_mode: AtomicBool,
    /// User setting: whether the Dynamic Island is enabled at all.
    pub island_enabled: AtomicBool,
    /// Last pill width the renderer measured, in logical pixels; 0 = never measured.
    ///
    /// The single authority for centring the overlay. Both `position_island`
    /// and `resize_island` used to derive the width themselves — one from
    /// `outer_size()`, the other from the incoming measurement — and mid-
    /// animation those disagree, so whichever ran last won. Observed live: a
    /// 206px pill centred as if it were 510px, landing 150px left of centre.
    pub island_width: AtomicU32,
}

impl AppState {
    pub fn new() -> Self {
        Self {
            island_mode: AtomicBool::new(false),
            // Renderer pushes the real value from settings on boot; default ON
            // to match `islandEnabled = true` in electron.cjs.
            island_enabled: AtomicBool::new(true),
            island_width: AtomicU32::new(0),
        }
    }

    /// Logical width to centre the overlay on, or `None` before the renderer
    /// has measured the pill.
    pub fn measured_island_width(&self) -> Option<u32> {
        match self.island_width.load(Ordering::Acquire) {
            0 => None,
            w => Some(w),
        }
    }
    pub fn set_measured_island_width(&self, w: u32) {
        self.island_width.store(w, Ordering::Release);
    }

    pub fn is_island_mode(&self) -> bool {
        self.island_mode.load(Ordering::Acquire)
    }
    pub fn set_island_mode(&self, v: bool) {
        self.island_mode.store(v, Ordering::Release);
    }
    pub fn is_island_enabled(&self) -> bool {
        self.island_enabled.load(Ordering::Acquire)
    }
    pub fn set_island_enabled(&self, v: bool) {
        self.island_enabled.store(v, Ordering::Release);
    }
}

pub fn main_window(app: &AppHandle) -> Option<WebviewWindow> {
    app.get_webview_window(MAIN_WINDOW)
}

pub fn island_window(app: &AppHandle) -> Option<WebviewWindow> {
    app.get_webview_window(ISLAND_WINDOW)
}

/// Re-centre the island overlay on the current monitor's top edge.
///
/// `Monitor::size()` is physical while the window's configured width is
/// logical, so centring has to happen in one space or the other. Doing the
/// arithmetic in physical pixels keeps it correct under fractional scaling,
/// where converting to logical and back rounds the pill off-centre.
pub fn position_island(app: &AppHandle, win: &WebviewWindow) {
    let scale = win.scale_factor().unwrap_or(1.0);
    let screen_w = win
        .current_monitor()
        .ok()
        .flatten()
        .map(|m| m.size().width)
        .unwrap_or(1920);

    // The measured pill width is authoritative. `outer_size()` is only a
    // fallback for the first show, before the renderer has reported anything:
    // reading it mid-resize returns whatever GTK has applied so far, which is
    // how the overlay ended up centred for a width it no longer had.
    let win_w = match app.state::<AppState>().measured_island_width() {
        Some(logical) => (logical as f64 * scale).round() as u32,
        None => win
            .outer_size()
            .map(|s| s.width)
            .unwrap_or((ISLAND_WIDTH as f64 * scale).round() as u32),
    };

    let _ = win.set_position(PhysicalPosition::new(island_x(screen_w, win_w), 0));
}

/// Resize the island overlay to hug the pill the renderer just measured.
///
/// Electron kept a fixed 900×220 overlay and made the transparent margin
/// click-through via `setIgnoreMouseEvents(true, { forward: true })`, which
/// still delivers mouse events to the page so the pill's `mouseenter` can turn
/// capture back on. Tauri's `set_ignore_cursor_events` has no `forward`
/// equivalent — an ignoring window receives no events at all, so that handshake
/// deadlocks: the pill can never learn the cursor arrived. Sizing the window to
/// the pill removes the transparent margin, and with it the need to ignore
/// anything.
pub fn resize_island(app: &AppHandle, width: f64, height: f64) {
    let Some(island) = island_window(app) else {
        return;
    };
    let (w, h) = crate::channels::clamp_island_size(width, height);

    // Record before moving anything: this is the value every centring path
    // reads, so it must be current even if the resize below is still settling.
    app.state::<AppState>().set_measured_island_width(w);

    let _ = island.set_size(tauri::LogicalSize::new(w as f64, h as f64));
    position_island(app, &island);
}

/// Set click-through on a window, but only once it is actually on screen.
///
/// On Linux this call reaches `window.window().unwrap()` in tao's GTK event
/// loop. A GTK window that has never been shown has no realized `GdkWindow`, so
/// that unwrap panics — and it runs inside a callback declared `extern "C"`,
/// which cannot unwind, so the panic aborts the whole process rather than
/// surfacing as an error. `WebviewWindow::set_ignore_cursor_events` returns a
/// `Result`, which makes it look safe to call unconditionally; it is not.
///
/// The visibility check is the guard. Windows and macOS tolerate the call on a
/// hidden window, so this costs nothing there.
pub fn set_click_through(win: &WebviewWindow, ignore: bool) {
    if win.is_visible().unwrap_or(false) {
        let _ = win.set_ignore_cursor_events(ignore);
    }
}

/// Fold the app down to the island pill.
pub fn enter_island_mode(app: &AppHandle) {
    let state = app.state::<AppState>();

    // Island disabled in settings → behave like a plain minimize instead.
    if !state.is_island_enabled() {
        if let Some(main) = main_window(app) {
            let _ = main.minimize();
        }
        return;
    }

    state.set_island_mode(true);

    if let Some(island) = island_window(app) {
        position_island(app, &island);
        // Show before touching click-through: the window must be realized first
        // (see set_click_through). Under Tauri the overlay is sized to the pill
        // by useIslandAutoSize, so there is no transparent margin left to pass
        // clicks through — this only resets state the renderer may have set.
        let _ = island.show();
        set_click_through(&island, false);
    }

    if let Some(main) = main_window(app) {
        // Remove from the taskbar before hiding — the pill is the UI now.
        let _ = main.set_skip_taskbar(true);
        let _ = main.hide();
    }
}

/// Restore the full application window.
pub fn exit_island_mode(app: &AppHandle) {
    let state = app.state::<AppState>();
    state.set_island_mode(false);

    if let Some(island) = island_window(app) {
        // Reset click-through while the window is still realized, then hide.
        set_click_through(&island, false);
        let _ = island.hide();
    }

    if let Some(main) = main_window(app) {
        let _ = main.set_skip_taskbar(false);
        let _ = main.show();
        let _ = main.unminimize();
        let _ = main.set_focus();
    }
}

/// Hide everything to the tray (island disabled path of `close-app`).
pub fn hide_to_tray(app: &AppHandle) {
    if let Some(main) = main_window(app) {
        let _ = main.set_skip_taskbar(true);
        let _ = main.hide();
    }
    if let Some(island) = island_window(app) {
        set_click_through(&island, false);
        let _ = island.hide();
    }
    app.state::<AppState>().set_island_mode(false);
}

/// Toggle maximize on the main window.
pub fn toggle_maximize(app: &AppHandle) {
    let Some(main) = main_window(app) else { return };
    match main.is_maximized() {
        Ok(true) => {
            let _ = main.unmaximize();
        }
        _ => {
            let _ = main.maximize();
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn defaults_match_electron() {
        let s = AppState::new();
        assert!(!s.is_island_mode(), "app starts in full-window mode");
        assert!(
            s.is_island_enabled(),
            "island defaults ON like electron.cjs"
        );
    }

    #[test]
    fn flags_round_trip() {
        let s = AppState::new();
        s.set_island_mode(true);
        assert!(s.is_island_mode());
        s.set_island_mode(false);
        assert!(!s.is_island_mode());

        s.set_island_enabled(false);
        assert!(!s.is_island_enabled());
    }

    #[test]
    fn measured_width_starts_unset_and_round_trips() {
        let s = AppState::new();
        assert_eq!(
            s.measured_island_width(),
            None,
            "before the renderer measures, centring must fall back to the window size"
        );

        s.set_measured_island_width(206);
        assert_eq!(s.measured_island_width(), Some(206));
    }

    #[test]
    fn measured_width_is_the_single_centring_authority() {
        // Regression guard for the observed off-centre overlay: a 206px pill
        // was centred as if it were 510px because `position_island` read a
        // stale `outer_size()` instead of the measurement. Both paths now read
        // this one value, so centring is a pure function of it.
        let s = AppState::new();
        s.set_measured_island_width(510);
        assert_eq!(island_x(1600, s.measured_island_width().unwrap()), 545);

        s.set_measured_island_width(206);
        assert_eq!(island_x(1600, s.measured_island_width().unwrap()), 697);
    }

    #[test]
    fn island_width_matches_position_math() {
        // Guards the constant against drifting from tauri.conf.json.
        assert_eq!(ISLAND_WIDTH, 900);
        assert_eq!(island_x(1920, ISLAND_WIDTH), 510);
    }
}
