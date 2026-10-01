use serde_json::Value;
use std::io::Write;
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};

fn repository_root() -> Result<PathBuf, String> {
    let manifest = Path::new(env!("CARGO_MANIFEST_DIR"));
    manifest
        .parent()
        .and_then(Path::parent)
        .map(Path::to_path_buf)
        .ok_or_else(|| "cannot resolve SherlockPC repository root".to_string())
}

fn run_python_bridge(payload: &Value) -> Result<Value, String> {
    let root = repository_root()?;
    let request = serde_json::to_vec(payload).map_err(|error| error.to_string())?;

    let candidates: [(&str, &[&str]); 3] = [
        ("python", &[]),
        ("python3", &[]),
        ("py", &["-3"]),
    ];
    let mut launch_errors = Vec::new();

    for (program, prefix) in candidates {
        let mut command = Command::new(program);
        command
            .args(prefix)
            .args(["-m", "sherlock.desktop_bridge"])
            .current_dir(&root)
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped());

        let mut child = match command.spawn() {
            Ok(child) => child,
            Err(error) => {
                launch_errors.push(format!("{program}: {error}"));
                continue;
            }
        };

        if let Some(stdin) = child.stdin.as_mut() {
            stdin.write_all(&request).map_err(|error| error.to_string())?;
        }

        let output = child.wait_with_output().map_err(|error| error.to_string())?;
        let stdout = String::from_utf8_lossy(&output.stdout);
        let stderr = String::from_utf8_lossy(&output.stderr);

        let response: Value = serde_json::from_str(stdout.trim()).map_err(|error| {
            format!(
                "backend returned invalid JSON: {error}; stderr: {}",
                stderr.trim()
            )
        })?;

        if !output.status.success() && response.get("ok") != Some(&Value::Bool(false)) {
            return Err(format!("backend failed: {}", stderr.trim()));
        }

        return Ok(response);
    }

    Err(format!(
        "Python 3 was not found. Tried python, python3 and py -3. {}",
        launch_errors.join(" | ")
    ))
}

#[tauri::command]
fn backend_call(payload: Value) -> Result<Value, String> {
    run_python_bridge(&payload)
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![backend_call])
        .run(tauri::generate_context!())
        .expect("error while running SherlockPC desktop");
}
