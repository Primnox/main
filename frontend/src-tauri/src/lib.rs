//! Primnox V2 desktop shell (Tauri).
//!
//! Deliberately much smaller than V1's `src-tauri`: this crate's whole job is
//! "show the window, run the backend behind it, kill the backend when the
//! window closes." V1's shell additionally reproduces an Electron IPC surface
//! (`window.electron.ipcRenderer`), a "Dynamic Island" overlay window,
//! clipboard-rewriting smart-paste on a global shortcut, and a system tray —
//! none of which frontend's React code calls into (confirmed by grep
//! before writing this: no `window.electron`, no Tauri `invoke`, no
//! `@tauri-apps/*` import anywhere in frontend/src). It talks to the
//! backend over plain HTTP and WebSocket, the same as it would in a browser
//! tab — the window is a shell around that, not a bridge to it.
//!
//! Closing the window quits the app and kills the backend, rather than
//! folding to a tray — the simplest, most predictable behaviour, and the
//! right default for a first release with no tray UI of its own yet.

pub mod backend;

use tauri::{Manager, RunEvent, WindowEvent};

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let app = tauri::Builder::default()
        .setup(|app| {
            let handle = app.handle();
            let resource_dir = handle.path().resource_dir().unwrap_or_default();
            backend::start(&resource_dir, cfg!(debug_assertions));
            Ok(())
        })
        .on_window_event(|window, event| {
            if let WindowEvent::CloseRequested { .. } = event {
                backend::stop();
            }
        })
        .build(tauri::generate_context!())
        .expect("error while building Primnox");

    app.run(|_app, event| {
        if let RunEvent::ExitRequested { .. } | RunEvent::Exit = event {
            backend::stop();
        }
    });
}
