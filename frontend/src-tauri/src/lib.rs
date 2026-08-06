//! Primnox desktop shell (Tauri).
//!
//! This is a port of `public/electron.cjs`. The React frontend is unchanged: it
//! still talks over the `window.electron.ipcRenderer` surface, which
//! `src/bridge/electronBridge.ts` re-implements on top of Tauri's
//! `invoke`/`listen`. Every channel here has a counterpart in the Electron
//! preload allowlist.

pub mod backend;
pub mod channels;
pub mod smart_paste;
pub mod windows;

use tauri::menu::{MenuBuilder, MenuItemBuilder};
use tauri::tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent};
use tauri::{AppHandle, Emitter, Manager, RunEvent, WindowEvent};
use tauri_plugin_clipboard_manager::ClipboardExt;

use channels::{is_renderer_to_main, ISLAND_WINDOW, MAIN_WINDOW};
use smart_paste::PasteResult;
use windows::{
    enter_island_mode, exit_island_mode, hide_to_tray, island_window, main_window, toggle_maximize,
    AppState,
};

/// Emit an event to whichever window is currently the user-facing one.
fn notify_active(app: &AppHandle, event: &str, payload: PasteResult) {
    let state = app.state::<AppState>();
    let target = if state.is_island_mode() && island_window(app).is_some() {
        ISLAND_WINDOW
    } else {
        MAIN_WINDOW
    };
    let _ = app.emit_to(target, event, payload);
}

/// Read the clipboard, ask the backend to rewrite it, write the result back.
fn run_smart_paste(app: &AppHandle) {
    if !smart_paste::try_acquire() {
        return; // a run is already in flight
    }

    let content = match app.clipboard().read_text() {
        Ok(text) => text,
        Err(_) => {
            smart_paste::release();
            return;
        }
    };

    if !smart_paste::is_worth_transforming(&content) {
        smart_paste::release();
        return;
    }

    let app = app.clone();
    std::thread::spawn(move || {
        let outcome = match smart_paste::fetch_transform(&content) {
            Ok(transformed) => {
                match smart_paste::resolve_transform(&content, transformed.as_deref()) {
                    Some(new_text) => match app.clipboard().write_text(new_text) {
                        Ok(()) => PasteResult::changed(),
                        Err(_) => PasteResult::failed(),
                    },
                    // Content was already optimal — not a failure.
                    None => PasteResult::unchanged(),
                }
            }
            Err(_) => PasteResult::failed(),
        };

        notify_active(&app, "smart-paste-result", outcome);
        smart_paste::release();
    });
}

/// The single entry point the renderer uses, mirroring `ipcRenderer.send`.
#[tauri::command]
fn electron_send(app: AppHandle, channel: String, payload: Option<serde_json::Value>) {
    // The Electron preload filtered channels renderer-side. Under Tauri the
    // renderer can invoke any command, so the allowlist is enforced here.
    if !is_renderer_to_main(&channel) {
        eprintln!("Blocked IPC on unregistered channel: {channel}");
        return;
    }

    let state = app.state::<AppState>();

    match channel.as_str() {
        "minimize-app" | "window-minimize" => {
            if !state.is_island_mode() {
                enter_island_mode(&app);
            }
        }

        "maximize-app" | "window-maximize" => {
            if state.is_island_mode() {
                exit_island_mode(&app);
            } else {
                toggle_maximize(&app);
            }
        }

        "close-app" | "window-close" => {
            if state.is_island_enabled() {
                enter_island_mode(&app);
            } else {
                hide_to_tray(&app);
            }
        }

        "show-full-window" => exit_island_mode(&app),

        "set-window-mode" => {
            let is_island = payload
                .as_ref()
                .and_then(|v| v.as_str())
                .map(|s| s == "island")
                .unwrap_or(false);
            if is_island {
                enter_island_mode(&app);
            } else {
                exit_island_mode(&app);
            }
        }

        "restart-app" => {
            // The Electron build called autoUpdater.quitAndInstall(). Until the
            // Tauri updater is wired up (see src-tauri/README.md) this is a
            // plain relaunch, which is the correct no-update behaviour.
            tauri::process::restart(&app.env());
        }

        "run-smart-paste" => run_smart_paste(&app),

        "island:set-enabled" => {
            let enabled = payload
                .as_ref()
                .and_then(|v| v.as_bool())
                .unwrap_or(true);
            state.set_island_enabled(enabled);
        }

        "island:set-size" => {
            let (w, h) = payload
                .as_ref()
                .map(|v| {
                    (
                        v.get("width").and_then(serde_json::Value::as_f64).unwrap_or(0.0),
                        v.get("height").and_then(serde_json::Value::as_f64).unwrap_or(0.0),
                    )
                })
                .unwrap_or((0.0, 0.0));
            windows::resize_island(&app, w, h);
        }

        "island:set-ignore-mouse" => {
            let ignore = payload
                .as_ref()
                .and_then(|v| v.as_bool())
                .unwrap_or(true);
            if let Some(island) = island_window(&app) {
                let _ = island.set_ignore_cursor_events(ignore);
            }
        }

        // Main window → island overlay.
        "friday:proactive" => {
            if state.is_island_mode() {
                let _ = app.emit_to(ISLAND_WINDOW, "friday:proactive", payload);
            }
        }

        // Island overlay → main window. Electron registered these channels in
        // the preload but had no `ipcMain` handler, so they were silently
        // dropped; forwarding them is what makes the pill's buttons work.
        "friday:reply"
        | "friday:clear-clipboard"
        | "friday:mic-toggle"
        | "friday:open-notes"
        | "friday:mic-state"
        | "friday:state" => {
            let _ = app.emit_to(MAIN_WINDOW, &channel, payload);
        }

        other => eprintln!("Unhandled IPC channel: {other}"),
    }
}

/// Build the tray icon and its context menu.
fn setup_tray(app: &AppHandle) -> tauri::Result<()> {
    let open = MenuItemBuilder::with_id("open", "Open Primnox").build(app)?;
    let island = MenuItemBuilder::with_id("island", "Island Mode").build(app)?;
    let quit = MenuItemBuilder::with_id("quit", "Quit Primnox").build(app)?;

    let menu = MenuBuilder::new(app)
        .items(&[&open, &island])
        .separator()
        .items(&[&quit])
        .build()?;

    TrayIconBuilder::with_id("primnox-tray")
        .icon(app.default_window_icon().cloned().ok_or_else(|| {
            tauri::Error::AssetNotFound("default window icon".into())
        })?)
        .tooltip("Primnox — running in background")
        .menu(&menu)
        .show_menu_on_left_click(false)
        .on_menu_event(|app, event| match event.id().as_ref() {
            "open" => exit_island_mode(app),
            "island" => {
                if app.state::<AppState>().is_island_mode() {
                    exit_island_mode(app);
                } else {
                    enter_island_mode(app);
                }
            }
            "quit" => {
                backend::stop();
                app.exit(0);
            }
            _ => {}
        })
        .on_tray_icon_event(|tray, event| {
            // Left click restores the full window, matching the Electron tray.
            if let TrayIconEvent::Click {
                button: MouseButton::Left,
                button_state: MouseButtonState::Up,
                ..
            } = event
            {
                let app = tray.app_handle();
                let visible = main_window(app)
                    .and_then(|w| w.is_visible().ok())
                    .unwrap_or(false);
                if !visible || app.state::<AppState>().is_island_mode() {
                    exit_island_mode(app);
                } else if let Some(w) = main_window(app) {
                    let _ = w.set_focus();
                }
            }
        })
        .build(app)?;

    Ok(())
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let mut builder = tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_clipboard_manager::init())
        .plugin(tauri_plugin_process::init());

    // Global shortcuts are desktop-only.
    #[cfg(desktop)]
    {
        use tauri_plugin_global_shortcut::{Code, Modifiers, Shortcut, ShortcutState};

        let smart_paste_shortcut =
            Shortcut::new(Some(Modifiers::CONTROL | Modifiers::SHIFT), Code::KeyP);

        builder = builder.plugin(
            tauri_plugin_global_shortcut::Builder::new()
                .with_shortcut(smart_paste_shortcut)
                .expect("failed to register Ctrl+Shift+P")
                .with_handler(move |app, shortcut, event| {
                    // Fire on key-down only; the handler also receives Released.
                    if event.state() == ShortcutState::Pressed
                        && shortcut == &smart_paste_shortcut
                    {
                        run_smart_paste(app);
                    }
                })
                .build(),
        );
    }

    let app = builder
        .manage(AppState::new())
        .invoke_handler(tauri::generate_handler![electron_send])
        .setup(|app| {
            let handle = app.handle();

            let resource_dir = handle.path().resource_dir().unwrap_or_default();
            backend::start(&resource_dir, cfg!(debug_assertions));

            setup_tray(handle)?;

            // The island overlay is declared `visible: false` in the config and
            // pre-loaded here, so the first minimize shows a ready pill rather
            // than a blank window while React boots.
            if let Some(island) = island_window(handle) {
                windows::position_island(&island);
                let _ = island.set_ignore_cursor_events(true);
            }

            Ok(())
        })
        .on_window_event(|window, event| {
            // Closing the main window folds to the island / tray instead of
            // quitting — the app lives in the tray until explicitly quit.
            if let WindowEvent::CloseRequested { api, .. } = event {
                let app = window.app_handle();
                if window.label() == MAIN_WINDOW {
                    api.prevent_close();
                    if app.state::<AppState>().is_island_enabled() {
                        enter_island_mode(app);
                    } else {
                        hide_to_tray(app);
                    }
                } else if window.label() == ISLAND_WINDOW {
                    // Never destroy the overlay — just hide it.
                    api.prevent_close();
                    let _ = window.hide();
                }
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
