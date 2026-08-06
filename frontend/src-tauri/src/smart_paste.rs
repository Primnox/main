//! Smart Paste: read the clipboard, ask the backend to rewrite it, write back.
//!
//! Ports `runSmartPaste` / `fetchSmartPaste` from `public/electron.cjs`.

use serde::Serialize;
use std::sync::atomic::{AtomicBool, Ordering};
use std::time::Duration;

use crate::backend::BACKEND_PORT;

/// Guards against concurrent runs racing on the clipboard, matching the
/// `pasteInFlight` flag in the Electron implementation.
static IN_FLIGHT: AtomicBool = AtomicBool::new(false);

/// Payload emitted on the `smart-paste-result` channel.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct PasteResult {
    pub ok: bool,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub changed: Option<bool>,
}

impl PasteResult {
    pub fn changed() -> Self {
        Self {
            ok: true,
            changed: Some(true),
        }
    }
    pub fn unchanged() -> Self {
        Self {
            ok: true,
            changed: Some(false),
        }
    }
    pub fn failed() -> Self {
        Self {
            ok: false,
            changed: None,
        }
    }
}

/// What to do with a backend response, given the original clipboard text.
///
/// Returns `Some(text)` when the clipboard should be overwritten, `None` when
/// the content was already optimal. Whitespace-only rewrites are treated as no
/// change — the backend occasionally returns a blank string on a failed
/// transform, and writing that would silently destroy the user's clipboard.
pub fn resolve_transform(original: &str, transformed: Option<&str>) -> Option<String> {
    let candidate = transformed?;
    if candidate.trim().is_empty() {
        return None;
    }
    if candidate == original {
        return None;
    }
    Some(candidate.to_string())
}

/// Should Smart Paste run at all for this clipboard content?
pub fn is_worth_transforming(content: &str) -> bool {
    !content.trim().is_empty()
}

/// Try to claim the in-flight lock. `false` means a run is already active.
pub fn try_acquire() -> bool {
    IN_FLIGHT
        .compare_exchange(false, true, Ordering::AcqRel, Ordering::Acquire)
        .is_ok()
}

/// Release the in-flight lock.
pub fn release() {
    IN_FLIGHT.store(false, Ordering::Release);
}

/// POST the clipboard content to the backend and return the rewritten text.
pub fn fetch_transform(content: &str) -> Result<Option<String>, String> {
    let url = format!("http://127.0.0.1:{BACKEND_PORT}/api/smart_paste");
    let body = serde_json::json!({ "content": content });

    let resp = ureq::post(&url)
        .timeout(Duration::from_secs(10))
        .set("Content-Type", "application/json")
        .send_string(&body.to_string())
        .map_err(|e| e.to_string())?;

    let raw = resp.into_string().map_err(|e| e.to_string())?;

    // A non-JSON body is not fatal: Electron fell back to the original content,
    // which surfaces as "nothing changed" rather than an error.
    let parsed: serde_json::Value = match serde_json::from_str(&raw) {
        Ok(v) => v,
        Err(_) => return Ok(None),
    };

    Ok(parsed
        .get("transformed")
        .and_then(|v| v.as_str())
        .map(str::to_string))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn rewrites_when_backend_returns_new_text() {
        assert_eq!(
            resolve_transform("hello", Some("Hello, world.")),
            Some("Hello, world.".to_string())
        );
    }

    #[test]
    fn no_rewrite_when_identical() {
        assert_eq!(resolve_transform("hello", Some("hello")), None);
    }

    #[test]
    fn no_rewrite_on_blank_response() {
        // Regression guard: writing these back would wipe the user's clipboard.
        assert_eq!(resolve_transform("hello", Some("")), None);
        assert_eq!(resolve_transform("hello", Some("   ")), None);
        assert_eq!(resolve_transform("hello", Some("\n\t ")), None);
    }

    #[test]
    fn no_rewrite_when_backend_omits_field() {
        assert_eq!(resolve_transform("hello", None), None);
    }

    #[test]
    fn skips_empty_clipboard() {
        assert!(!is_worth_transforming(""));
        assert!(!is_worth_transforming("   \n "));
        assert!(is_worth_transforming("real content"));
    }

    #[test]
    fn in_flight_lock_is_exclusive() {
        release();
        assert!(try_acquire(), "first acquire should succeed");
        assert!(!try_acquire(), "second acquire must be refused");
        release();
        assert!(try_acquire(), "acquire should succeed after release");
        release();
    }

    #[test]
    fn payload_serialises_like_electron() {
        let json = serde_json::to_string(&PasteResult::changed()).unwrap();
        assert_eq!(json, r#"{"ok":true,"changed":true}"#);

        let json = serde_json::to_string(&PasteResult::unchanged()).unwrap();
        assert_eq!(json, r#"{"ok":true,"changed":false}"#);

        // Electron sent bare `{ ok: false }` with no `changed` key.
        let json = serde_json::to_string(&PasteResult::failed()).unwrap();
        assert_eq!(json, r#"{"ok":false}"#);
    }
}
