//! Python backend lifecycle.
//!
//! Ports `startBackend` / `freeBackendPort` from `public/electron.cjs`. The
//! backend is a PyInstaller bundle shipped as a resource; in dev it is already
//! running (started by `start.sh` / `start.bat`) and must not be spawned twice.

use std::path::{Path, PathBuf};
use std::process::{Child, Command};
use std::sync::Mutex;

/// Port the Python backend binds. Kept in sync with `src/config.ts`.
pub const BACKEND_PORT: u16 = 4009;

/// Handle to the spawned backend, so it can be killed on quit.
pub static BACKEND_CHILD: Mutex<Option<Child>> = Mutex::new(None);

/// Executable name for the current platform.
pub fn backend_exe_name() -> &'static str {
    if cfg!(target_os = "windows") {
        "primnox_backend.exe"
    } else {
        "primnox_backend"
    }
}

/// Path to the bundled backend inside the app's resource directory.
pub fn backend_path(resource_dir: &Path) -> PathBuf {
    resource_dir
        .join("primnox_backend")
        .join(backend_exe_name())
}

/// Would we kill this process to reclaim the backend port?
///
/// Mirrors the Electron guard: only reclaim the port from our own backend or a
/// bare Python interpreter (dev mode), never from an unrelated process that
/// happens to hold 4009.
pub fn is_our_backend_process(image_name: &str) -> bool {
    let name = image_name.trim().to_ascii_lowercase();
    name.contains("primnox_backend") || name.starts_with("python")
}

/// Extract listening PIDs for `port` from Windows `netstat -ano -p tcp` output.
///
/// Split out from the syscall so the parsing can be tested on every platform.
pub fn parse_netstat_pids(output: &str, port: u16) -> Vec<u32> {
    let needle = format!(":{port}");
    let mut pids = Vec::new();
    for line in output.lines() {
        if !line.contains(&needle) || !line.contains("LISTENING") {
            continue;
        }
        // The PID is the last whitespace-separated column.
        if let Some(pid) = line.split_whitespace().next_back() {
            if let Ok(pid) = pid.parse::<u32>() {
                // PID 0 is the system idle process — never a target.
                if pid != 0 && !pids.contains(&pid) {
                    pids.push(pid);
                }
            }
        }
    }
    pids
}

/// Kill any orphaned backend still holding the port from a previous run.
pub fn free_port(port: u16) {
    #[cfg(target_os = "windows")]
    {
        let Ok(out) = Command::new("netstat").args(["-ano", "-p", "tcp"]).output() else {
            return;
        };
        let stdout = String::from_utf8_lossy(&out.stdout);
        for pid in parse_netstat_pids(&stdout, port) {
            let Ok(info) = Command::new("tasklist")
                .args(["/FI", &format!("PID eq {pid}"), "/FO", "CSV", "/NH"])
                .output()
            else {
                continue;
            };
            let info = String::from_utf8_lossy(&info.stdout);
            let name = info.split(',').next().unwrap_or("").replace('"', "");
            if is_our_backend_process(&name) {
                let _ = Command::new("taskkill")
                    .args(["/PID", &pid.to_string(), "/T", "/F"])
                    .output();
            }
        }
    }

    #[cfg(not(target_os = "windows"))]
    {
        // `lsof -ti tcp:PORT` prints one PID per line; kill each.
        let Ok(out) = Command::new("lsof")
            .args(["-ti", &format!("tcp:{port}")])
            .output()
        else {
            return;
        };
        for line in String::from_utf8_lossy(&out.stdout).lines() {
            if let Ok(pid) = line.trim().parse::<u32>() {
                let _ = Command::new("kill").args(["-9", &pid.to_string()]).output();
            }
        }
    }
}

/// Spawn the bundled backend. No-op in dev, where it is already running.
pub fn start(resource_dir: &Path, is_dev: bool) {
    if is_dev {
        println!("Dev mode: using already-running backend on http://127.0.0.1:{BACKEND_PORT}");
        return;
    }

    free_port(BACKEND_PORT);

    let exe = backend_path(resource_dir);
    if !exe.exists() {
        eprintln!("Backend binary not found at {}", exe.display());
        return;
    }

    let cwd = exe.parent().map(Path::to_path_buf).unwrap_or_default();
    match Command::new(&exe).current_dir(cwd).spawn() {
        Ok(child) => {
            if let Ok(mut slot) = BACKEND_CHILD.lock() {
                *slot = Some(child);
            }
        }
        Err(e) => eprintln!("Backend spawn error: {e}"),
    }
}

/// Kill the backend on app quit.
pub fn stop() {
    let Ok(mut slot) = BACKEND_CHILD.lock() else {
        return;
    };
    if let Some(mut child) = slot.take() {
        #[cfg(target_os = "windows")]
        {
            // kill() only signals the direct child; PyInstaller leaves
            // grandchildren behind, so kill the whole tree.
            let _ = Command::new("taskkill")
                .args(["/PID", &child.id().to_string(), "/T", "/F"])
                .output();
        }
        let _ = child.kill();
        let _ = child.wait();
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn recognises_our_own_backend() {
        assert!(is_our_backend_process("primnox_backend.exe"));
        assert!(is_our_backend_process("PRIMNOX_BACKEND.EXE"));
        assert!(is_our_backend_process("python.exe"));
        assert!(is_our_backend_process("python3.11"));
    }

    #[test]
    fn refuses_to_kill_unrelated_processes() {
        assert!(!is_our_backend_process("node.exe"));
        assert!(!is_our_backend_process("postgres.exe"));
        assert!(!is_our_backend_process(""));
        // A process merely *containing* "python" late in the name is still ours
        // only if it starts with it — matches the Electron guard.
        assert!(!is_our_backend_process("mypython.exe"));
    }

    #[test]
    fn parses_listening_pids() {
        let out = "\
  Proto  Local Address          Foreign Address        State           PID
  TCP    0.0.0.0:4009           0.0.0.0:0              LISTENING       1234
  TCP    127.0.0.1:4009         127.0.0.1:5555         ESTABLISHED     9999
  TCP    0.0.0.0:80             0.0.0.0:0              LISTENING       4321
";
        assert_eq!(parse_netstat_pids(out, 4009), vec![1234]);
        assert_eq!(parse_netstat_pids(out, 80), vec![4321]);
        assert!(parse_netstat_pids(out, 9999).is_empty());
    }

    #[test]
    fn skips_pid_zero_and_dedupes() {
        let out = "\
  TCP    0.0.0.0:4009    0.0.0.0:0    LISTENING       0
  TCP    [::]:4009       [::]:0       LISTENING       777
  TCP    0.0.0.0:4009    0.0.0.0:0    LISTENING       777
";
        assert_eq!(parse_netstat_pids(out, 4009), vec![777]);
    }

    #[test]
    fn backend_path_is_nested_under_resources() {
        let p = backend_path(Path::new("/opt/app/resources"));
        assert!(p.ends_with(backend_exe_name()));
        assert!(p.to_string_lossy().contains("primnox_backend"));
    }
}
