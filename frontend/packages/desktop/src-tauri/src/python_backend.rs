use std::process::Stdio;
use std::sync::Arc;
use std::time::Duration;
use tokio::fs::OpenOptions;
use tokio::io::{AsyncBufReadExt, AsyncWriteExt, BufReader};
use tokio::process::{Child, Command};
use tokio::sync::{mpsc, Mutex};
use tokio::time::Instant;

/// Deployment mode for the backend
#[derive(Debug, Clone, Copy)]
enum DeploymentMode {
    /// Development: use Python module directly from chimera repo
    Development,
    /// Production: use PyInstaller bundled executable
    Production,
}

/// Manages the Python backend subprocess lifecycle
pub struct PythonBackend {
    child: Arc<Mutex<Option<Child>>>,
    port: u16,
    mode: DeploymentMode,
}

impl Drop for PythonBackend {
    fn drop(&mut self) {
        // Best-effort synchronous cleanup on drop
        if let Some(child) = self.child.blocking_lock().take() {
            log::warn!("PythonBackend dropped without explicit shutdown, forcing cleanup");

            #[cfg(unix)]
            {
                if let Some(raw_pid) = child.id() {
                    use nix::sys::signal::{killpg, Signal};
                    use nix::unistd::Pid;

                    let pid = Pid::from_raw(raw_pid as i32);

                    #[cfg(target_os = "macos")]
                    {
                        let _ = killpg(pid, Signal::SIGKILL);
                    }

                    #[cfg(not(target_os = "macos"))]
                    {
                        let _ = nix::sys::signal::kill(pid, Signal::SIGKILL);
                    }
                }
            }

            #[cfg(windows)]
            {
                let _ = child.start_kill();
            }

            // Give it a brief moment to die, but don't block for long
            std::thread::sleep(std::time::Duration::from_millis(100));
        }
    }
}

impl PythonBackend {
    /// Start the Python backend subprocess
    pub async fn start() -> Result<Self, String> {
        log::info!("Starting Chimera backend...");

        // Get the package root (for log files: go up from src-tauri -> desktop)
        let package_root = std::env::current_dir()
            .map_err(|e| format!("Failed to get current directory: {}", e))?
            .parent()  // -> packages/desktop
            .ok_or("Failed to get package directory")?
            .to_path_buf();

        // Get the workspace root (for finding chimera backend)
        let project_root = package_root
            .parent()  // -> packages
            .ok_or("Failed to get packages directory")?
            .parent()  // -> workspace root
            .ok_or("Failed to get workspace root")?
            .to_path_buf();

        // Port for Chimera backend
        let port = 33003;

        // Detect deployment mode
        let mode = if std::env::var("CHIMERA_DESKTOP_PRODUCTION").is_ok() {
            log::info!("Production mode: looking for bundled executable");
            DeploymentMode::Production
        } else {
            log::info!("Development mode: using Python module");
            DeploymentMode::Development
        };

        // Build command based on deployment mode
        let mut command = match mode {
            DeploymentMode::Development => {
                // Development: use uv run from monorepo root
                // The monorepo root is frontend/../.. (go up from frontend/packages/desktop)
                let monorepo_root = project_root
                    .parent()  // -> frontend
                    .and_then(|p| p.parent())  // -> monorepo root
                    .map(|p| p.to_path_buf())
                    .unwrap_or_else(|| project_root.clone());

                log::info!("Using monorepo root: {:?}", monorepo_root);

                // Use uv run to start the backend
                let mut cmd = Command::new("uv");
                cmd.arg("run");
                cmd.arg("uvicorn");
                cmd.arg("chimera_api.main:app");
                cmd.arg("--host");
                cmd.arg("0.0.0.0");
                cmd.arg("--port");
                cmd.arg(port.to_string());
                cmd.current_dir(&monorepo_root);
                cmd
            }
            DeploymentMode::Production => {
                // Production: ./chimera-backend --port 33003
                let bundled_exe = project_root.join("resources").join("chimera-backend");
                if !bundled_exe.exists() {
                    return Err(format!("Bundled backend not found: {:?}", bundled_exe));
                }
                log::info!("Using bundled backend: {:?}", bundled_exe);

                let mut cmd = Command::new(bundled_exe);
                cmd.arg("--port");
                cmd.arg(port.to_string());
                cmd
            }
        };

        command.stdout(Stdio::piped());
        command.stderr(Stdio::piped());

        // Configure process to be killed when parent dies
        #[cfg(target_os = "linux")]
        unsafe {
            command.pre_exec(|| {
                // Use prctl to set parent death signal on Linux
                // PR_SET_PDEATHSIG = 1, SIGKILL = 9
                libc::prctl(libc::PR_SET_PDEATHSIG, libc::SIGKILL);
                Ok(())
            });
        }

        #[cfg(target_os = "macos")]
        unsafe {
            command.pre_exec(|| {
                // Create new process group so we can kill the whole group
                // but don't create a new session (which would prevent parent death signals)
                let _ = nix::libc::setpgid(0, 0);
                Ok(())
            });
        }

        let mut child = command
            .spawn()
            .map_err(|e| format!("Failed to spawn Python backend: {}", e))?;

        let stdout = child.stdout.take().expect("stdout was piped");
        let stderr = child.stderr.take().expect("stderr was piped");

        // Create log file for Python output
        let log_path = package_root.join("python-backend.log");
        let log_file = Arc::new(Mutex::new(
            OpenOptions::new()
                .create(true)
                .append(true)
                .open(&log_path)
                .await
                .map_err(|e| format!("Failed to create log file: {}", e))?
        ));
        log::info!("Python logs will be written to: {:?}", log_path);

        // Create channels for communication
        let (ready_tx, mut ready_rx) = mpsc::channel::<bool>(1);
        let ready_tx_clone = ready_tx.clone();

        // Monitor stdout for readiness signal
        let log_file_stdout = log_file.clone();
        let _stdout_task = tokio::spawn(async move {
            let mut reader = BufReader::new(stdout);
            let mut line = String::new();

            loop {
                line.clear();
                match reader.read_line(&mut line).await {
                    Ok(0) => break, // EOF
                    Ok(_) => {
                        let trimmed = line.trim();
                        if !trimmed.is_empty() {
                            // Write to log file
                            let mut file = log_file_stdout.lock().await;
                            let _ = file.write_all(format!("[stdout] {}\n", trimmed).as_bytes()).await;

                            log::info!("[Python stdout] {}", trimmed);

                            // Look for Uvicorn's ready message
                            if trimmed.contains("Uvicorn running on") || trimmed.contains("Application startup complete") {
                                log::info!("Python backend is ready!");
                                let _ = ready_tx.send(true).await;
                            }
                        }
                    }
                    Err(e) => {
                        log::error!("Error reading stdout: {}", e);
                        break;
                    }
                }
            }
        });

        // Monitor stderr for errors
        let log_file_stderr = log_file.clone();
        let _stderr_task = tokio::spawn(async move {
            let mut reader = BufReader::new(stderr);
            let mut line = String::new();

            loop {
                line.clear();
                match reader.read_line(&mut line).await {
                    Ok(0) => break, // EOF
                    Ok(_) => {
                        let trimmed = line.trim();
                        if !trimmed.is_empty() {
                            // Write to log file
                            let mut file = log_file_stderr.lock().await;
                            let _ = file.write_all(format!("[stderr] {}\n", trimmed).as_bytes()).await;

                            log::info!("[Python stderr] {}", trimmed);

                            // Uvicorn also logs to stderr
                            if trimmed.contains("Uvicorn running on") || trimmed.contains("Application startup complete") {
                                log::info!("Python backend is ready (from stderr)!");
                                let _ = ready_tx_clone.send(true).await;
                            }
                        }
                    }
                    Err(e) => {
                        log::error!("Error reading stderr: {}", e);
                        break;
                    }
                }
            }
        });

        // Check if process exited early
        if let Ok(Some(status)) = child.try_wait() {
            if !status.success() {
                return Err(format!("Python backend exited early with code {:?}", status));
            }
        }

        // Wait for backend to be ready with timeout
        let timeout_duration = Duration::from_secs(30); // 30 second timeout
        let start_time = Instant::now();

        log::info!("Waiting for Python backend to be ready...");
        loop {
            tokio::select! {
                // Backend is ready
                Some(true) = ready_rx.recv() => {
                    log::info!("Python backend ready to accept requests!");
                    break;
                }
                // Check for process exit
                _ = tokio::time::sleep(Duration::from_millis(100)) => {
                    if let Ok(Some(status)) = child.try_wait() {
                        return Err(format!("Python backend exited with code {:?}", status));
                    }

                    // Timeout check
                    if start_time.elapsed() > timeout_duration {
                        let _ = child.kill().await;
                        return Err(format!("Python backend failed to start within {}s", timeout_duration.as_secs()));
                    }
                }
            }
        }

        Ok(Self {
            child: Arc::new(Mutex::new(Some(child))),
            port,
            mode,
        })
    }

    /// Get the base URL for the Python backend
    pub fn base_url(&self) -> String {
        format!("http://localhost:{}", self.port)
    }

    /// Get the port
    #[allow(dead_code)]
    pub fn port(&self) -> u16 {
        self.port
    }

    /// Gracefully shutdown the Python backend
    pub async fn shutdown(&self) {
        let mut child_guard = self.child.lock().await;

        if let Some(mut child) = child_guard.take() {
            log::info!("Shutting down Python backend...");

            #[cfg(unix)]
            {
                graceful_terminate_unix(&mut child).await;
            }

            #[cfg(windows)]
            {
                force_terminate_windows(&mut child).await;
            }

            log::info!("Python backend shutdown complete");
        }
    }
}

/// Gracefully terminate a process on Unix (SIGTERM → SIGKILL)
#[cfg(unix)]
async fn graceful_terminate_unix(child: &mut Child) {
    use nix::sys::signal::{killpg, Signal};
    use nix::unistd::Pid;

    if let Some(raw_pid) = child.id() {
        let pid = Pid::from_raw(raw_pid as i32);

        // On macOS, kill the entire process group to ensure child processes are terminated
        #[cfg(target_os = "macos")]
        {
            log::info!("Sending SIGTERM to process group {}", raw_pid);
            let _ = killpg(pid, Signal::SIGTERM);
        }

        // On Linux and other Unix, just kill the process
        #[cfg(not(target_os = "macos"))]
        {
            log::info!("Sending SIGTERM to PID {}", raw_pid);
            let _ = nix::sys::signal::kill(pid, Signal::SIGTERM);
        }

        // Wait up to 5 seconds for graceful shutdown
        match tokio::time::timeout(Duration::from_secs(5), child.wait()).await {
            Ok(Ok(status)) => {
                log::info!("Process exited gracefully: {}", status);
            }
            Ok(Err(e)) => {
                log::error!("Error waiting after SIGTERM: {}", e);
            }
            Err(_) => {
                // Timeout - force kill the process group
                #[cfg(target_os = "macos")]
                {
                    log::warn!("SIGTERM timed out, sending SIGKILL to process group {}", raw_pid);
                    let _ = killpg(pid, Signal::SIGKILL);
                }

                #[cfg(not(target_os = "macos"))]
                {
                    log::warn!("SIGTERM timed out, sending SIGKILL to PID {}", raw_pid);
                    let _ = nix::sys::signal::kill(pid, Signal::SIGKILL);
                }

                match child.wait().await {
                    Ok(status) => log::info!("Force-killed process exited: {}", status),
                    Err(e) => log::error!("Error waiting after SIGKILL: {}", e),
                }
            }
        }
    }
}

/// Force terminate a process on Windows
#[cfg(windows)]
async fn force_terminate_windows(child: &mut Child) {
    if let Some(raw_pid) = child.id() {
        log::warn!("Force-killing PID {} (Windows doesn't support graceful shutdown)", raw_pid);

        if let Err(e) = child.kill().await {
            log::error!("Failed to kill PID {}: {}", raw_pid, e);
        }

        match child.wait().await {
            Ok(status) => log::info!("Process {} terminated: {}", raw_pid, status),
            Err(e) => log::error!("Error waiting on process {}: {}", raw_pid, e),
        }
    }
}
