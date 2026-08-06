//! IPC channel allowlists.
//!
//! These mirror the `validChannels` arrays in `public/preload.js` exactly. The
//! Electron preload filters channels in the renderer; under Tauri the renderer
//! can invoke any command, so the filtering has to happen here in Rust instead.
//! Keeping the two lists identical is what lets the same React code run on both
//! runtimes without behavioural drift.

/// Channels the renderer is allowed to `send` to the app (renderer → main).
pub const RENDERER_TO_MAIN: &[&str] = &[
    // Window controls
    "minimize-app",
    "maximize-app",
    "close-app",
    "restart-app",
    // Island / tray
    "show-full-window",
    // Legacy
    "set-window-mode",
    // App IPC
    "friday:proactive",
    "friday:reply",
    "friday:clear-clipboard",
    "friday:mic-state",
    "friday:state",
    "friday:mic-toggle",
    "friday:open-notes",
    "island:set-ignore-mouse",
    "island:set-enabled",
    // Tauri-only. Electron keeps a fixed 900x220 overlay and relies on
    // click-through for the transparent margin; Tauri has no equivalent of
    // Electron's `forward: true`, so the overlay is resized to hug the pill
    // instead. Absent from `preload.js` by design — under Electron the send is
    // simply refused, which is the correct no-op.
    "island:set-size",
    "run-smart-paste",
    "window-minimize",
    "window-maximize",
    "window-close",
];

/// Channels the app is allowed to emit to the renderer (main → renderer).
pub const MAIN_TO_RENDERER: &[&str] = &[
    "primnox:island-mode",
    "friday:proactive",
    "friday:open-notes",
    "friday:mic-state",
    "friday:state",
    "morph-island",
    "render-token-binary",
    "update-available",
    "update-downloaded",
    "smart-paste-result",
];

/// Is this a channel the renderer may send on?
pub fn is_renderer_to_main(channel: &str) -> bool {
    RENDERER_TO_MAIN.contains(&channel)
}

/// Is this a channel the app may emit on?
pub fn is_main_to_renderer(channel: &str) -> bool {
    MAIN_TO_RENDERER.contains(&channel)
}

/// Window label for the primary application window.
pub const MAIN_WINDOW: &str = "main";
/// Window label for the always-on-top Dynamic Island overlay.
pub const ISLAND_WINDOW: &str = "island";

/// Horizontal position that centres the island overlay on a screen.
///
/// Mirrors `Math.floor(width / 2 - 450)` from `electron.cjs`, but clamped at 0
/// so the overlay never lands off-screen to the left. The Electron original
/// produces a negative x on displays narrower than the 900px pill (e.g. a
/// 800×600 projector), which pushes the pill partly off the monitor.
pub fn island_x(screen_width: u32, island_width: u32) -> i32 {
    let centered = (screen_width as i64 / 2) - (island_width as i64 / 2);
    centered.max(0) as i32
}

/// Smallest sane size for the island overlay, in logical pixels.
pub const ISLAND_MIN_W: u32 = 120;
pub const ISLAND_MIN_H: u32 = 40;
/// Largest the overlay may grow, so a runaway layout can never blanket the screen.
pub const ISLAND_MAX_W: u32 = 1600;
pub const ISLAND_MAX_H: u32 = 900;

/// Clamp a renderer-reported pill size into a size the overlay may take.
///
/// The renderer measures the pill with a `ResizeObserver`, and a mid-animation
/// or pre-layout measurement can report 0 or an absurd value. Clamping here
/// keeps a bad frame from resizing the window to something unusable.
pub fn clamp_island_size(width: f64, height: f64) -> (u32, u32) {
    let w = if width.is_finite() {
        width.round().max(0.0) as u32
    } else {
        0
    };
    let h = if height.is_finite() {
        height.round().max(0.0) as u32
    } else {
        0
    };
    (
        w.clamp(ISLAND_MIN_W, ISLAND_MAX_W),
        h.clamp(ISLAND_MIN_H, ISLAND_MAX_H),
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn renderer_allowlist_accepts_known_channels() {
        assert!(is_renderer_to_main("minimize-app"));
        assert!(is_renderer_to_main("run-smart-paste"));
        assert!(is_renderer_to_main("island:set-ignore-mouse"));
    }

    #[test]
    fn renderer_allowlist_rejects_unknown_channels() {
        assert!(!is_renderer_to_main("rm -rf"));
        assert!(!is_renderer_to_main(""));
        // An emit-only channel must not be sendable from the renderer.
        assert!(!is_renderer_to_main("update-downloaded"));
    }

    #[test]
    fn emit_allowlist_matches_preload() {
        assert!(is_main_to_renderer("smart-paste-result"));
        assert!(is_main_to_renderer("update-available"));
        assert!(!is_main_to_renderer("minimize-app"));
    }

    #[test]
    fn island_is_centered_on_common_widths() {
        // 1920 / 2 - 450 == 510, matching the Electron original.
        assert_eq!(island_x(1920, 900), 510);
        assert_eq!(island_x(2560, 900), 830);
        assert_eq!(island_x(1366, 900), 233);
    }

    #[test]
    fn clamps_a_normal_pill_measurement_through_unchanged() {
        assert_eq!(clamp_island_size(520.0, 52.0), (520, 52));
        assert_eq!(clamp_island_size(899.6, 219.4), (900, 219));
    }

    #[test]
    fn clamps_degenerate_measurements_to_the_minimum() {
        // ResizeObserver can report 0 before first layout, and motion/react
        // reports sub-pixel sizes mid-animation. Neither may shrink the window
        // to something the user cannot see or grab.
        assert_eq!(clamp_island_size(0.0, 0.0), (ISLAND_MIN_W, ISLAND_MIN_H));
        assert_eq!(
            clamp_island_size(-500.0, -20.0),
            (ISLAND_MIN_W, ISLAND_MIN_H)
        );
        assert_eq!(clamp_island_size(3.0, 1.0), (ISLAND_MIN_W, ISLAND_MIN_H));
    }

    #[test]
    fn clamps_runaway_measurements_to_the_maximum() {
        assert_eq!(
            clamp_island_size(99_999.0, 99_999.0),
            (ISLAND_MAX_W, ISLAND_MAX_H)
        );
    }

    #[test]
    fn rejects_non_finite_measurements() {
        // A NaN width would otherwise cast to 0 and silently blank the overlay.
        assert_eq!(clamp_island_size(f64::NAN, 52.0), (ISLAND_MIN_W, 52));
        assert_eq!(
            clamp_island_size(f64::INFINITY, f64::NEG_INFINITY),
            (ISLAND_MIN_W, ISLAND_MIN_H)
        );
    }

    #[test]
    fn island_never_goes_off_screen_left() {
        // Electron's formula yields -50 here, putting the pill off-screen.
        assert_eq!(island_x(800, 900), 0);
        assert_eq!(island_x(0, 900), 0);
    }
}
