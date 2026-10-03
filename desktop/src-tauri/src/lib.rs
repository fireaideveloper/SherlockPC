use serde_json::Value;
use tauri_plugin_shell::ShellExt;

const SIDECAR_NAME: &str = "sherlock-backend";

async fn run_backend_sidecar(app: &tauri::AppHandle, payload: &Value) -> Result<Value, String> {
    let request = serde_json::to_string(payload).map_err(|error| error.to_string())?;

    let command = app
        .shell()
        .sidecar(SIDECAR_NAME)
        .map_err(|error| format!("cannot resolve bundled Sherlock backend: {error}"))?
        .args(["--request-json", request.as_str()]);

    let output = command
        .output()
        .await
        .map_err(|error| format!("cannot start bundled Sherlock backend: {error}"))?;

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

    Ok(response)
}

#[tauri::command]
async fn backend_call(app: tauri::AppHandle, payload: Value) -> Result<Value, String> {
    run_backend_sidecar(&app, &payload).await
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .invoke_handler(tauri::generate_handler![backend_call])
        .run(tauri::generate_context!())
        .expect("error while running SherlockPC desktop");
}
