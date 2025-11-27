use portable_pty::{native_pty_system, CommandBuilder, MasterPty, PtySize};
use std::collections::HashMap;
use std::io::{Read, Write};
use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::Arc;
use tauri::{AppHandle, Emitter};
use tokio::sync::Mutex;

/// Deployment mode for the terminal backend
#[derive(Debug, Clone, Copy)]
enum DeploymentMode {
    /// Development: run ink CLI from local npm installation
    Development,
    /// Production: use bundled executable
    Production,
}

/// Represents a single terminal instance
struct TerminalInstance {
    id: String,
    pty_master: Box<dyn MasterPty + Send>,
    cols: u16,
    rows: u16,
}

/// Manages multiple terminal instances
pub struct TerminalBackend {
    terminals: Arc<Mutex<HashMap<String, TerminalInstance>>>,
    next_id: AtomicUsize,
    mode: DeploymentMode,
    app_handle: AppHandle,
}

/// Terminal output event payload
#[derive(Clone, serde::Serialize)]
struct TerminalOutputEvent {
    terminal_id: String,
    data: String,
}

/// Terminal status event payload
#[derive(Clone, serde::Serialize)]
struct TerminalStatusEvent {
    terminal_id: String,
    status: String,
}

impl TerminalBackend {
    /// Create a new terminal backend
    pub fn new(app_handle: AppHandle) -> Self {
        let mode = if std::env::var("CHIMERA_DESKTOP_PRODUCTION").is_ok() {
            log::info!("Terminal backend: Production mode");
            DeploymentMode::Production
        } else {
            log::info!("Terminal backend: Development mode");
            DeploymentMode::Development
        };

        Self {
            terminals: Arc::new(Mutex::new(HashMap::new())),
            next_id: AtomicUsize::new(1),
            mode,
            app_handle,
        }
    }

    /// Spawn a new terminal instance
    pub async fn spawn_terminal(
        &self,
        terminal_type: String,
        cwd: Option<String>,
    ) -> Result<String, String> {
        let terminal_id = format!("terminal_{}", self.next_id.fetch_add(1, Ordering::SeqCst));
        log::info!("Spawning terminal {}: type={}", terminal_id, terminal_type);

        // Determine working directory
        let working_dir = if let Some(cwd) = cwd {
            std::path::PathBuf::from(cwd)
        } else {
            std::env::current_dir()
                .map_err(|e| format!("Failed to get current directory: {}", e))?
        };

        // Default terminal size
        let cols = 80;
        let rows = 24;

        // Create PTY
        let pty_system = native_pty_system();
        let pty_pair = pty_system
            .openpty(PtySize {
                rows,
                cols,
                pixel_width: 0,
                pixel_height: 0,
            })
            .map_err(|e| format!("Failed to create PTY: {}", e))?;

        // Build command based on terminal type and deployment mode
        let mut cmd = match terminal_type.as_str() {
            "ink-cli" => self.build_ink_cli_command(&working_dir)?,
            "bash" => {
                let mut cmd = CommandBuilder::new("bash");
                cmd.cwd(&working_dir);
                cmd
            }
            _ => return Err(format!("Unknown terminal type: {}", terminal_type)),
        };

        // Set up environment variables for proper terminal emulation
        cmd.env("TERM", "xterm-256color");
        cmd.env("COLORTERM", "truecolor");

        // Spawn the child process in the PTY
        let child = pty_pair
            .slave
            .spawn_command(cmd)
            .map_err(|e| format!("Failed to spawn command: {}", e))?;

        log::info!("Terminal {} spawned successfully (PID: {:?})", terminal_id, child.process_id());

        // Store the terminal instance
        let instance = TerminalInstance {
            id: terminal_id.clone(),
            pty_master: pty_pair.master,
            cols,
            rows,
        };

        {
            let mut terminals = self.terminals.lock().await;
            terminals.insert(terminal_id.clone(), instance);
        }

        // Emit ready status
        let _ = self.app_handle.emit(
            "terminal_status",
            TerminalStatusEvent {
                terminal_id: terminal_id.clone(),
                status: "ready".to_string(),
            },
        );

        // Start I/O monitoring task
        self.start_io_task(terminal_id.clone()).await;

        Ok(terminal_id)
    }

    /// Build command for ink CLI
    fn build_ink_cli_command(&self, working_dir: &std::path::Path) -> Result<CommandBuilder, String> {
        match self.mode {
            DeploymentMode::Development => {
                // Development: use local npm installation or custom path
                let ink_cli_path = std::env::var("CHIMERA_INK_CLI_PATH")
                    .unwrap_or_else(|_| {
                        // Default to node_modules/.bin/ink-cli
                        working_dir
                            .join("node_modules")
                            .join(".bin")
                            .join("ink-cli")
                            .to_string_lossy()
                            .to_string()
                    });

                log::info!("Using ink CLI from: {}", ink_cli_path);

                let mut cmd = CommandBuilder::new("node");
                cmd.arg(&ink_cli_path);
                cmd.cwd(working_dir);
                Ok(cmd)
            }
            DeploymentMode::Production => {
                // Production: use bundled executable
                let bundled_exe = working_dir
                    .join("resources")
                    .join("ink-cli");

                if !bundled_exe.exists() {
                    return Err(format!("Bundled ink CLI not found: {:?}", bundled_exe));
                }

                log::info!("Using bundled ink CLI: {:?}", bundled_exe);
                let mut cmd = CommandBuilder::new(bundled_exe);
                cmd.cwd(working_dir);
                Ok(cmd)
            }
        }
    }

    /// Start I/O monitoring task for a terminal
    async fn start_io_task(&self, terminal_id: String) {
        let terminals = self.terminals.clone();
        let app_handle = self.app_handle.clone();
        let id = terminal_id.clone();

        tokio::spawn(async move {
            // Get the PTY reader
            let mut reader = {
                let mut terms = terminals.lock().await;
                let instance = match terms.get_mut(&id) {
                    Some(inst) => inst,
                    None => {
                        log::error!("Terminal {} not found for I/O task", id);
                        return;
                    }
                };

                instance.pty_master.try_clone_reader()
                    .expect("Failed to clone PTY reader")
            };

            // Read from PTY and emit events
            let mut buffer = [0u8; 8192];
            loop {
                match reader.read(&mut buffer) {
                    Ok(0) => {
                        // EOF - terminal closed
                        log::info!("Terminal {} closed (EOF)", id);
                        let _ = app_handle.emit(
                            "terminal_status",
                            TerminalStatusEvent {
                                terminal_id: id.clone(),
                                status: "closed".to_string(),
                            },
                        );
                        break;
                    }
                    Ok(n) => {
                        // Convert to string (lossy for safety)
                        let data = String::from_utf8_lossy(&buffer[..n]).to_string();

                        // Emit output event
                        if let Err(e) = app_handle.emit(
                            "terminal_output",
                            TerminalOutputEvent {
                                terminal_id: id.clone(),
                                data,
                            },
                        ) {
                            log::error!("Failed to emit terminal output: {}", e);
                        }
                    }
                    Err(e) => {
                        log::error!("Error reading from terminal {}: {}", id, e);
                        let _ = app_handle.emit(
                            "terminal_status",
                            TerminalStatusEvent {
                                terminal_id: id.clone(),
                                status: "error".to_string(),
                            },
                        );
                        break;
                    }
                }
            }

            // Clean up terminal instance
            let mut terms = terminals.lock().await;
            terms.remove(&id);
            log::info!("Terminal {} cleaned up", id);
        });
    }

    /// Write data to a terminal
    pub async fn write_to_terminal(&self, terminal_id: &str, data: &str) -> Result<(), String> {
        let mut terminals = self.terminals.lock().await;
        let instance = terminals
            .get_mut(terminal_id)
            .ok_or_else(|| format!("Terminal not found: {}", terminal_id))?;

        let mut writer = instance.pty_master.take_writer()
            .map_err(|e| format!("Failed to get PTY writer: {}", e))?;

        writer
            .write_all(data.as_bytes())
            .map_err(|e| format!("Failed to write to terminal: {}", e))?;

        writer
            .flush()
            .map_err(|e| format!("Failed to flush terminal: {}", e))?;

        Ok(())
    }

    /// Resize a terminal
    pub async fn resize_terminal(
        &self,
        terminal_id: &str,
        cols: u16,
        rows: u16,
    ) -> Result<(), String> {
        let mut terminals = self.terminals.lock().await;
        let instance = terminals
            .get_mut(terminal_id)
            .ok_or_else(|| format!("Terminal not found: {}", terminal_id))?;

        instance
            .pty_master
            .resize(PtySize {
                rows,
                cols,
                pixel_width: 0,
                pixel_height: 0,
            })
            .map_err(|e| format!("Failed to resize terminal: {}", e))?;

        instance.cols = cols;
        instance.rows = rows;

        log::info!("Terminal {} resized to {}x{}", terminal_id, cols, rows);
        Ok(())
    }

    /// Close a terminal
    pub async fn close_terminal(&self, terminal_id: &str) -> Result<(), String> {
        let mut terminals = self.terminals.lock().await;

        if let Some(instance) = terminals.remove(terminal_id) {
            log::info!("Terminal {} closed by request", instance.id);

            // The PTY will be dropped here, which should signal the child process
            // The I/O task will detect EOF and clean up

            Ok(())
        } else {
            Err(format!("Terminal not found: {}", terminal_id))
        }
    }

    /// Shutdown all terminals
    pub async fn shutdown_all(&self) {
        log::info!("Shutting down all terminals...");

        let mut terminals = self.terminals.lock().await;
        let terminal_ids: Vec<String> = terminals.keys().cloned().collect();

        for id in terminal_ids {
            if let Some(instance) = terminals.remove(&id) {
                log::info!("Closing terminal {}", instance.id);
            }
        }

        log::info!("All terminals shutdown complete");
    }
}
