use tauri::Manager;
use tauri_plugin_shell::ShellExt;

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .setup(|app| {
            // Launch the Python backend sidecar
            let _sidecar = app
                .shell()
                .sidecar("sparkbot-backend")
                .expect("sparkbot-backend sidecar not found")
                .spawn()
                .expect("failed to spawn sparkbot-backend");

            #[cfg(debug_assertions)]
            app.get_webview_window("main").unwrap().open_devtools();

            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running sparkbot application")
}
