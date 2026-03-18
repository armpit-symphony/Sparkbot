#![cfg_attr(all(not(debug_assertions), target_os = "windows"), windows_subsystem = "windows")]

use std::env;
use std::fs;
use std::path::PathBuf;
use std::sync::Mutex;

use tauri::{Manager, RunEvent};
use tauri_plugin_shell::process::{CommandChild, CommandEvent};
use tauri_plugin_shell::ShellExt;

const SIDECAR_NAME: &str = "binaries/sparkbot-backend";
const BACKEND_HOST: &str = "127.0.0.1";
const BACKEND_PORT: &str = "8000";

#[derive(Default)]
struct BackendChild(Mutex<Option<CommandChild>>);

fn sparkbot_data_dir() -> Result<PathBuf, String> {
    if cfg!(target_os = "windows") {
        if let Some(appdata) = env::var_os("APPDATA") {
            return Ok(PathBuf::from(appdata).join("Sparkbot"));
        }
    }

    if cfg!(target_os = "macos") {
        if let Some(home) = env::var_os("HOME") {
            return Ok(PathBuf::from(home).join("Library/Application Support/Sparkbot"));
        }
    }

    if let Some(data_home) = env::var_os("XDG_DATA_HOME") {
        return Ok(PathBuf::from(data_home).join("sparkbot"));
    }

    if let Some(home) = env::var_os("HOME") {
        return Ok(PathBuf::from(home).join(".local/share/sparkbot"));
    }

    Err("Could not resolve a desktop data directory for Sparkbot".to_string())
}

fn stop_backend(app: &tauri::AppHandle) {
    if let Ok(mut guard) = app.state::<BackendChild>().0.lock() {
        if let Some(child) = guard.take() {
            let _ = child.kill();
        }
    }
}

fn start_backend(app: &tauri::AppHandle) -> Result<(), String> {
    let data_dir = sparkbot_data_dir()?;
    let guardian_dir = data_dir.join("guardian");
    fs::create_dir_all(&data_dir).map_err(|err| err.to_string())?;
    fs::create_dir_all(&guardian_dir).map_err(|err| err.to_string())?;

    let data_dir_string = data_dir.to_string_lossy().to_string();
    let guardian_dir_string = guardian_dir.to_string_lossy().to_string();
    let args = vec![
        "--host".to_string(),
        BACKEND_HOST.to_string(),
        "--port".to_string(),
        BACKEND_PORT.to_string(),
        "--data-dir".to_string(),
        data_dir_string.clone(),
    ];

    let command = app
        .shell()
        .sidecar(SIDECAR_NAME)
        .map_err(|err| err.to_string())?
        .args(args)
        .env("SPARKBOT_DATA_DIR", data_dir_string)
        .env("SPARKBOT_GUARDIAN_DATA_DIR", guardian_dir_string)
        .env("V1_LOCAL_MODE", "true")
        .env("DATABASE_TYPE", "sqlite")
        .env("WORKSTATION_LIVE_TERMINAL_ENABLED", "false")
        .env("ENVIRONMENT", "local");

    let (mut rx, child) = command.spawn().map_err(|err| err.to_string())?;

    tauri::async_runtime::spawn(async move {
        while let Some(event) = rx.recv().await {
            match event {
                CommandEvent::Stdout(line) => {
                    println!("[sparkbot-backend] {}", String::from_utf8_lossy(&line));
                }
                CommandEvent::Stderr(line) => {
                    eprintln!("[sparkbot-backend] {}", String::from_utf8_lossy(&line));
                }
                CommandEvent::Error(error) => {
                    eprintln!("[sparkbot-backend] {error}");
                }
                CommandEvent::Terminated(payload) => {
                    println!("[sparkbot-backend] exited: {:?}", payload.code);
                }
                _ => {}
            }
        }
    });

    if let Ok(mut guard) = app.state::<BackendChild>().0.lock() {
        *guard = Some(child);
    }

    Ok(())
}

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .manage(BackendChild::default())
        .setup(|app| {
            if let Err(err) = start_backend(app.handle()) {
                return Err(std::io::Error::new(std::io::ErrorKind::Other, err).into());
            }
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("failed to build Sparkbot Local desktop shell")
        .run(|app, event| match event {
            RunEvent::ExitRequested { .. } | RunEvent::Exit => stop_backend(app),
            _ => {}
        });
}
