use serde::{Deserialize, Serialize};
use std::fs;
use std::path::PathBuf;
use tokio::fs::OpenOptions;
use tokio::io::{AsyncBufReadExt, AsyncWriteExt, BufReader};

/// Metadata for a blueprint
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BlueprintMetadata {
    pub id: String,
    pub name: String,
    pub description: Option<String>,
    pub file_path: String,
}

/// Metadata for a thread
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ThreadMetadata {
    pub thread_id: String,
    pub title: Option<String>,
    pub created_at: String,
    pub updated_at: String,
    pub file_path: String,
}

/// Get the Chimera desktop data directory (~/chimera-desktop)
fn get_data_dir() -> Result<PathBuf, String> {
    let home = dirs::home_dir().ok_or("Failed to get home directory")?;
    Ok(home.join("chimera-desktop"))
}

/// Get the blueprints directory
fn get_blueprints_dir() -> Result<PathBuf, String> {
    Ok(get_data_dir()?.join("blueprints"))
}

/// Get the threads directory
fn get_threads_dir() -> Result<PathBuf, String> {
    Ok(get_data_dir()?.join("threads"))
}

/// Initialize the filesystem structure
pub async fn init_filesystem() -> Result<(), String> {
    let data_dir = get_data_dir()?;
    let blueprints_dir = get_blueprints_dir()?;
    let threads_dir = get_threads_dir()?;

    // Create directories if they don't exist
    fs::create_dir_all(&blueprints_dir)
        .map_err(|e| format!("Failed to create blueprints directory: {}", e))?;
    fs::create_dir_all(&threads_dir)
        .map_err(|e| format!("Failed to create threads directory: {}", e))?;

    log::info!("Initialized filesystem at {:?}", data_dir);
    log::info!("Blueprints: {:?}", blueprints_dir);
    log::info!("Threads: {:?}", threads_dir);

    Ok(())
}

/// List all available blueprints
pub async fn list_blueprints() -> Result<Vec<BlueprintMetadata>, String> {
    let blueprints_dir = get_blueprints_dir()?;

    if !blueprints_dir.exists() {
        return Ok(Vec::new());
    }

    let mut blueprints = Vec::new();

    let entries = fs::read_dir(&blueprints_dir)
        .map_err(|e| format!("Failed to read blueprints directory: {}", e))?;

    for entry in entries {
        let entry = entry.map_err(|e| format!("Failed to read directory entry: {}", e))?;
        let path = entry.path();

        if path.extension().and_then(|s| s.to_str()) == Some("json") {
            // Read the blueprint file to extract metadata
            match fs::read_to_string(&path) {
                Ok(content) => {
                    match serde_json::from_str::<serde_json::Value>(&content) {
                        Ok(json) => {
                            // Extract metadata from blueprint
                            let blueprint = json.get("blueprint").and_then(|b| b.as_object());
                            let space = blueprint.and_then(|b| b.get("space")).and_then(|s| s.as_object());
                            let agents = space.and_then(|s| s.get("agents")).and_then(|a| a.as_array());

                            // Get first agent's name and description
                            let first_agent = agents.and_then(|a| a.first()).and_then(|a| a.as_object());
                            let name = first_agent
                                .and_then(|a| a.get("name"))
                                .and_then(|n| n.as_str())
                                .unwrap_or("Unknown Agent")
                                .to_string();

                            let description = first_agent
                                .and_then(|a| a.get("description"))
                                .and_then(|d| d.as_str())
                                .map(|s| s.to_string());

                            // Use filename (without extension) as blueprint id
                            let id = path.file_stem()
                                .and_then(|s| s.to_str())
                                .unwrap_or("unknown")
                                .to_string();

                            blueprints.push(BlueprintMetadata {
                                id,
                                name,
                                description,
                                file_path: path.to_string_lossy().to_string(),
                            });
                        }
                        Err(e) => {
                            log::warn!("Failed to parse blueprint {}: {}", path.display(), e);
                        }
                    }
                }
                Err(e) => {
                    log::warn!("Failed to read blueprint {}: {}", path.display(), e);
                }
            }
        }
    }

    Ok(blueprints)
}

/// Create a new thread with the given blueprint
pub async fn create_thread(blueprint_json: String) -> Result<String, String> {
    let threads_dir = get_threads_dir()?;

    // Parse blueprint JSON
    let mut blueprint: serde_json::Value = serde_json::from_str(&blueprint_json)
        .map_err(|e| format!("Failed to parse blueprint JSON: {}", e))?;

    // Generate a new UUID for this thread
    let thread_id = uuid::Uuid::new_v4().to_string();

    // Add thread_id to the blueprint
    if let Some(obj) = blueprint.as_object_mut() {
        obj.insert("thread_id".to_string(), serde_json::Value::String(thread_id.clone()));
    } else {
        return Err("Blueprint JSON is not an object".to_string());
    }

    let file_path = threads_dir.join(format!("{}.jsonl", thread_id));

    // Write the blueprint as the first line (minified, single-line JSON for JSONL format)
    let mut file = OpenOptions::new()
        .create(true)
        .write(true)
        .truncate(true)
        .open(&file_path)
        .await
        .map_err(|e| format!("Failed to create thread file: {}", e))?;

    // Serialize as minified JSON (no pretty-printing) for JSONL format
    let minified_json = serde_json::to_string(&blueprint)
        .map_err(|e| format!("Failed to serialize blueprint: {}", e))?;

    file.write_all(minified_json.as_bytes())
        .await
        .map_err(|e| format!("Failed to write blueprint: {}", e))?;
    file.write_all(b"\n")
        .await
        .map_err(|e| format!("Failed to write newline: {}", e))?;
    file.flush()
        .await
        .map_err(|e| format!("Failed to flush file: {}", e))?;

    log::info!("Created thread {} at {:?}", thread_id, file_path);

    Ok(thread_id)
}

/// Load a thread's events
pub async fn load_thread(thread_id: String) -> Result<Vec<serde_json::Value>, String> {
    let threads_dir = get_threads_dir()?;
    let file_path = threads_dir.join(format!("{}.jsonl", thread_id));

    if !file_path.exists() {
        return Err(format!("Thread {} not found", thread_id));
    }

    let file = tokio::fs::File::open(&file_path)
        .await
        .map_err(|e| format!("Failed to open thread file: {}", e))?;

    let reader = BufReader::new(file);
    let mut lines = reader.lines();
    let mut events = Vec::new();

    while let Some(line) = lines.next_line().await
        .map_err(|e| format!("Failed to read line: {}", e))? {

        if !line.trim().is_empty() {
            match serde_json::from_str::<serde_json::Value>(&line) {
                Ok(event) => events.push(event),
                Err(e) => {
                    log::warn!("Failed to parse event line: {}", e);
                    // Continue reading - don't fail on single bad line
                }
            }
        }
    }

    log::info!("Loaded {} events from thread {}", events.len(), thread_id);

    Ok(events)
}

/// Append events to a thread's JSONL file
pub async fn append_thread_events(
    thread_id: String,
    events: Vec<serde_json::Value>,
) -> Result<(), String> {
    let threads_dir = get_threads_dir()?;
    let file_path = threads_dir.join(format!("{}.jsonl", thread_id));

    let mut file = OpenOptions::new()
        .create(true)
        .append(true)
        .open(&file_path)
        .await
        .map_err(|e| format!("Failed to open thread file for append: {}", e))?;

    let event_count = events.len();

    for event in &events {
        let line = serde_json::to_string(event)
            .map_err(|e| format!("Failed to serialize event: {}", e))?;

        file.write_all(line.as_bytes())
            .await
            .map_err(|e| format!("Failed to write event: {}", e))?;
        file.write_all(b"\n")
            .await
            .map_err(|e| format!("Failed to write newline: {}", e))?;
    }

    file.flush()
        .await
        .map_err(|e| format!("Failed to flush file: {}", e))?;

    log::info!("Appended {} events to thread {}", event_count, thread_id);

    Ok(())
}

/// List all threads with metadata
pub async fn list_threads() -> Result<Vec<ThreadMetadata>, String> {
    let threads_dir = get_threads_dir()?;

    if !threads_dir.exists() {
        return Ok(Vec::new());
    }

    let mut threads = Vec::new();

    let entries = fs::read_dir(&threads_dir)
        .map_err(|e| format!("Failed to read threads directory: {}", e))?;

    for entry in entries {
        let entry = entry.map_err(|e| format!("Failed to read directory entry: {}", e))?;
        let path = entry.path();

        if path.extension().and_then(|s| s.to_str()) == Some("jsonl") {
            let thread_id = path
                .file_stem()
                .and_then(|s| s.to_str())
                .unwrap_or("unknown")
                .to_string();

            // Get file metadata for timestamps
            let metadata = fs::metadata(&path)
                .map_err(|e| format!("Failed to get file metadata: {}", e))?;

            let created_at = metadata.created()
                .ok()
                .and_then(|t| chrono::DateTime::<chrono::Utc>::from(t).to_rfc3339().parse().ok())
                .unwrap_or_else(|| chrono::Utc::now().to_rfc3339());

            let updated_at = metadata.modified()
                .ok()
                .and_then(|t| chrono::DateTime::<chrono::Utc>::from(t).to_rfc3339().parse().ok())
                .unwrap_or_else(|| chrono::Utc::now().to_rfc3339());

            // Extract title from first user message (if available)
            let title = extract_thread_title(&path).await;

            threads.push(ThreadMetadata {
                thread_id,
                title,
                created_at,
                updated_at,
                file_path: path.to_string_lossy().to_string(),
            });
        }
    }

    // Sort by updated_at (most recent first)
    threads.sort_by(|a, b| b.updated_at.cmp(&a.updated_at));

    Ok(threads)
}

/// Read a blueprint file and return its JSON content
pub async fn read_blueprint(file_path: String) -> Result<String, String> {
    let content = fs::read_to_string(&file_path)
        .map_err(|e| format!("Failed to read blueprint file: {}", e))?;
    Ok(content)
}

/// Extract title from first user message in thread
async fn extract_thread_title(path: &PathBuf) -> Option<String> {
    let file = tokio::fs::File::open(path).await.ok()?;
    let reader = BufReader::new(file);
    let mut lines = reader.lines();

    while let Some(line) = lines.next_line().await.ok()? {
        if let Ok(event) = serde_json::from_str::<serde_json::Value>(&line) {
            if event.get("type").and_then(|t| t.as_str()) == Some("user_message") {
                if let Some(content) = event.get("content").and_then(|c| c.as_str()) {
                    // Truncate to first 50 chars for title
                    let title = if content.len() > 50 {
                        format!("{}...", &content[..50])
                    } else {
                        content.to_string()
                    };
                    return Some(title);
                }
            }
        }
    }

    None
}
