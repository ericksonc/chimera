mod python_backend;
mod filesystem;
mod terminal_backend;

use std::sync::Arc;
use tauri::{Emitter, Manager};
use python_backend::PythonBackend;
use terminal_backend::TerminalBackend;
use filesystem::{BlueprintMetadata, ThreadMetadata};

// Learn more about Tauri commands at https://tauri.app/develop/calling-rust/
#[tauri::command]
fn greet(name: &str) -> String {
    format!("Hello, {}! You've been greeted from Rust!", name)
}

// Filesystem commands
#[tauri::command]
async fn init_filesystem() -> Result<(), String> {
    filesystem::init_filesystem().await
}

#[tauri::command]
async fn list_blueprints() -> Result<Vec<BlueprintMetadata>, String> {
    filesystem::list_blueprints().await
}

#[tauri::command]
async fn create_thread(blueprint_json: String) -> Result<String, String> {
    filesystem::create_thread(blueprint_json).await
}

#[tauri::command]
async fn load_thread(thread_id: String) -> Result<Vec<serde_json::Value>, String> {
    filesystem::load_thread(thread_id).await
}

#[tauri::command]
async fn append_thread_events(thread_id: String, events: Vec<serde_json::Value>) -> Result<(), String> {
    filesystem::append_thread_events(thread_id, events).await
}

#[tauri::command]
async fn list_threads() -> Result<Vec<ThreadMetadata>, String> {
    filesystem::list_threads().await
}

#[tauri::command]
async fn update_thread_title(thread_id: String, title: String) -> Result<(), String> {
    filesystem::update_thread_title(thread_id, title).await
}

#[tauri::command]
fn get_backend_url() -> String {
    "http://localhost:33003".to_string()
}

#[tauri::command]
async fn read_blueprint(file_path: String) -> Result<String, String> {
    filesystem::read_blueprint(file_path).await
}

// Terminal commands
#[tauri::command]
async fn spawn_terminal(
    terminal_type: String,
    cwd: Option<String>,
    state: tauri::State<'_, Arc<TerminalBackend>>,
) -> Result<String, String> {
    state.spawn_terminal(terminal_type, cwd).await
}

#[tauri::command]
async fn write_to_terminal(
    terminal_id: String,
    data: String,
    state: tauri::State<'_, Arc<TerminalBackend>>,
) -> Result<(), String> {
    state.write_to_terminal(&terminal_id, &data).await
}

#[tauri::command]
async fn resize_terminal(
    terminal_id: String,
    cols: u16,
    rows: u16,
    state: tauri::State<'_, Arc<TerminalBackend>>,
) -> Result<(), String> {
    state.resize_terminal(&terminal_id, cols, rows).await
}

#[tauri::command]
async fn close_terminal(
    terminal_id: String,
    state: tauri::State<'_, Arc<TerminalBackend>>,
) -> Result<(), String> {
    state.close_terminal(&terminal_id).await
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    // Clean up any stale Python backend from a previous crash
    python_backend::cleanup_stale_backend();

    let app = tauri::Builder::default()
        .plugin(tauri_plugin_log::Builder::default().build())
        .plugin(tauri_plugin_opener::init())
        .setup(|app| {
            // Initialize filesystem
            tauri::async_runtime::spawn(async move {
                if let Err(e) = init_filesystem().await {
                    log::error!("Failed to initialize filesystem: {}", e);
                }
            });

            // Initialize terminal backend
            let terminal_backend = Arc::new(TerminalBackend::new(app.handle().clone()));
            app.manage(terminal_backend);
            log::info!("Terminal backend initialized");

            // Start Python backend on app startup
            let app_handle_backend = app.handle().clone();
            tauri::async_runtime::spawn(async move {
                match PythonBackend::start().await {
                    Ok(backend) => {
                        let backend_url = backend.base_url();
                        log::info!("Python backend started successfully at {}", backend_url);

                        // Store backend in managed state
                        app_handle_backend.manage(Arc::new(backend));
                    }
                    Err(e) => {
                        log::error!("Failed to start Python backend: {}", e);
                        // Note: We don't exit the app - it can run without backend
                    }
                }
            });

            Ok(())
        })
        .on_window_event(|window, event| {
            // Listen for OS theme changes
            if let tauri::WindowEvent::ThemeChanged(theme) = event {
                let theme_str = match theme {
                    tauri::Theme::Dark => "dark",
                    tauri::Theme::Light => "light",
                    _ => "unknown",
                };
                log::info!("OS theme changed to: {}", theme_str);

                // Emit event to frontend
                if let Err(e) = window.emit("theme-changed", theme_str) {
                    log::error!("Failed to emit theme-changed event: {}", e);
                }
            }
        })
        .invoke_handler(tauri::generate_handler![
            greet,
            init_filesystem,
            list_blueprints,
            create_thread,
            load_thread,
            append_thread_events,
            list_threads,
            update_thread_title,
            get_backend_url,
            read_blueprint,
            spawn_terminal,
            write_to_terminal,
            resize_terminal,
            close_terminal
        ])
        .build(tauri::generate_context!())
        .expect("error while building tauri application");

    // Run with event handler for synchronous cleanup on exit
    app.run(|app_handle, event| {
        match event {
            tauri::RunEvent::ExitRequested { api, .. } => {
                // User clicked close - prevent exit until cleanup completes
                api.prevent_exit();

                log::info!("Exit requested, performing synchronous cleanup...");

                // Perform synchronous shutdown using block_on
                let handle = app_handle.clone();
                tauri::async_runtime::block_on(async move {
                    // Shutdown terminal backend
                    if let Some(terminal_backend) = handle.try_state::<Arc<TerminalBackend>>() {
                        log::info!("Shutting down terminal backend...");
                        terminal_backend.shutdown_all().await;
                    }

                    // Shutdown Python backend
                    if let Some(python_backend) = handle.try_state::<Arc<PythonBackend>>() {
                        log::info!("Shutting down Python backend...");
                        python_backend.shutdown().await;
                    }

                    log::info!("Cleanup complete, exiting...");
                });

                // Now actually exit
                app_handle.exit(0);
            }
            tauri::RunEvent::Exit => {
                // Final cleanup on any exit path (including SIGTERM)
                log::info!("App exiting, final cleanup...");

                // Perform synchronous shutdown using block_on
                let handle = app_handle.clone();
                tauri::async_runtime::block_on(async move {
                    // Shutdown terminal backend
                    if let Some(terminal_backend) = handle.try_state::<Arc<TerminalBackend>>() {
                        log::info!("Shutting down terminal backend...");
                        terminal_backend.shutdown_all().await;
                    }

                    // Shutdown Python backend
                    if let Some(python_backend) = handle.try_state::<Arc<PythonBackend>>() {
                        log::info!("Shutting down Python backend...");
                        python_backend.shutdown().await;
                    }

                    log::info!("Final cleanup complete");
                });
            }
            _ => {}
        }
    });
}
