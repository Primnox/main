//! Main-window / island-overlay mode transitions.
//!
//! Ports `enterIslandMode` / `exitIslandMode` and the window lifecycle rules
//! from `public/electron.cjs`.

use std::sync::atomic::{AtomicBool, Ordering};
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
}

impl AppState {
    pub fn new() -> Self {
        Self {
            island_mode: AtomicBool::new(false),
            // Renderer pushes the real value from settings on boot; default ON
            // to match `islandEnabled = true` in electron.cjs.
            island_enabled: AtomicBool::new(true),
        }
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
pub fn position_island(win: &WebviewWindow) {
    let scale = win.scale_factor().unwrap_or(1.0);
    let screen_w = win
        .current_monitor()
        .ok()
        .flatten()
        .map(|m| m.size().width)
        .unwrap_or(1920);

    // Prefer the window's real size over the configured constant: after
    // `resize_island` the overlay no longer measures ISLAND_WIDTH.
    let win_w = win
        .outer_size()
        .map(|s| s.width)
        .unwrap_or((ISLAND_WIDTH as f64 * scale).round() as u32);

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
    let Some(island) = island_window(app) else { return };
    let (w, h) = crate::channels::clamp_island_size(width, height);

    let _ = island.set_size(tauri::LogicalSize::new(w as f64, h as f64));

    // Re-centre using the new width, in the same logical space as the size
    // above — mixing logical size with physical position drifts the overlay
    // off-centre on any display with fractional scaling.
    let scale = island.scale_factor().unwrap_or(1.0);
    let screen_w = island
        .current_monitor()
        .ok()
        .flatten()
        .map(|m| m.size().width)
        .unwrap_or(1920);
    let logical_screen_w = (screen_w as f64 / scale).round() as u32;
    let _ = island.set_position(tauri::LogicalPosition::new(
        island_x(logical_screen_w, w) as f64,
        0.0,
    ));
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
        position_island(&island);
        // Transparent regions must not swallow clicks until the pill is hovered.
        let _ = island.set_ignore_cursor_events(true);
        let _ = island.show();
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
        // Reset click-through so the next show starts from a clean state.
        let _ = island.set_ignore_cursor_events(true);
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
        let _ = island.set_ignore_cursor_events(true);
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
        assert!(s.is_island_enabled(), "island defaults ON like electron.cjs");
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
    fn island_width_matches_position_math() {
        // Guards the constant against drifting from tauri.conf.json.
        assert_eq!(ISLAND_WIDTH, 900);
        assert_eq!(island_x(1920, ISLAND_WIDTH), 510);
    }
}
