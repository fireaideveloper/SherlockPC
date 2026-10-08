use serde_json::{json, Value};
use std::{
    sync::{Arc, Mutex},
    time::{Duration, Instant},
};
use tauri::Manager;
use tauri_plugin_shell::ShellExt;

mod background;

#[derive(Default)]
struct MonitorCache {
    overview: Option<Value>,
    error: Option<String>,
}

#[derive(Clone, Default)]
struct DesktopRuntime {
    gate: Arc<tauri::async_runtime::Mutex<()>>,
    cache: Arc<Mutex<MonitorCache>>,
}

#[tauri::command]
fn monitor_status(state: tauri::State<'_, DesktopRuntime>) -> Result<Value, String> {
    let cache = state.cache.lock().map_err(|e| e.to_string())?;
    Ok(json!({"ok": true, "result": {"overview": cache.overview, "error": cache.error}}))
}

const SIDECAR_NAME: &str = "sherlock-backend";

async fn run_backend_sidecar(app: &tauri::AppHandle, payload: &Value) -> Result<Value, String> {
    let request = serde_json::to_string(payload).map_err(|error| error.to_string())?;
    // tauri-plugin-shell launches Windows sidecars with CREATE_NO_WINDOW.
    // Keep the Python console build: its redirected stdout is our JSON pipe.
    let command = app.shell().sidecar(SIDECAR_NAME)
        .map_err(|error| format!("cannot resolve bundled Sherlock backend: {error}"))?
        .args(["--request-json", request.as_str()]);
    let output = command.output().await
        .map_err(|error| format!("cannot start bundled Sherlock backend: {error}"))?;
    let stdout = std::str::from_utf8(&output.stdout)
        .map_err(|error| format!("backend output is not valid UTF-8 JSON: {error}"))?;
    let stderr = String::from_utf8_lossy(&output.stderr);
    let response: Value = serde_json::from_str(stdout.trim()).map_err(|error| {
        format!("backend returned invalid JSON: {error}; stderr: {}", stderr.trim())
    })?;
    if !output.status.success() && response.get("ok") != Some(&Value::Bool(false)) {
        return Err(format!("backend failed: {}", stderr.trim()));
    }
    Ok(response)
}

// Both the worker and Refresh capture a new state, then publish it while holding
// the same gate. A late worker response cannot replace a newer manual snapshot.
async fn capture_overview(app: &tauri::AppHandle, runtime: &DesktopRuntime) -> Result<Value, String> {
    let _guard = runtime.gate.lock().await;
    let result = match run_backend_sidecar(app, &json!({"action": "overview"})).await {
        Ok(value) if value.get("ok") == Some(&Value::Bool(true)) => value.get("result")
            .filter(|result| result.get("current").is_some())
            .cloned().ok_or_else(|| "Collector returned no snapshot".to_owned()),
        Ok(value) => Err(value.get("error").and_then(Value::as_str)
            .unwrap_or("Collector failed").to_owned()),
        Err(error) => Err(error),
    };
    let mut cache = runtime.cache.lock().map_err(|e| e.to_string())?;
    match &result {
        Ok(overview) => { cache.overview = Some(overview.clone()); cache.error = None; }
        Err(error) => cache.error = Some(error.clone()),
    }
    result
}

#[tauri::command]
async fn refresh_state(app: tauri::AppHandle, state: tauri::State<'_, DesktopRuntime>) -> Result<Value, String> {
    capture_overview(&app, &state).await
}

#[tauri::command]
async fn backend_call(app: tauri::AppHandle, state: tauri::State<'_, DesktopRuntime>, payload: Value) -> Result<Value, String> {
    let _guard = state.gate.lock().await;
    let response = run_backend_sidecar(&app, &payload).await?;
    if payload.get("action").and_then(Value::as_str) == Some("clear_history")
        && response.get("ok") == Some(&Value::Bool(true)) {
        let mut cache = state.cache.lock().map_err(|error| error.to_string())?;
        cache.overview = None;
        cache.error = None;
    }
    Ok(response)
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        // Register first, before starting any worker or changing autostart.
        .plugin(tauri_plugin_single_instance::init(|app, args, _cwd| {
            if !args.iter().any(|arg| arg == "--background") {
                background::show_main(app);
            }
        }))
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_autostart::Builder::new()
            .app_name("SherlockPC")
            .args(["--background"])
            .build())
        .setup(|app| {
            let runtime = DesktopRuntime::default();
            app.manage(runtime.clone());
            background::setup(app)?;
            let handle = app.handle().clone();
            // This native worker keeps running with the window hidden in the tray.
            std::thread::spawn(move || loop {
                let started = Instant::now();
                let _ = tauri::async_runtime::block_on(capture_overview(&handle, &runtime));
                std::thread::sleep(Duration::from_secs(10).saturating_sub(started.elapsed())
                    .max(Duration::from_millis(500)));
            });
            Ok(())
        })
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::CloseRequested { api, .. } = event {
                if window.app_handle().tray_by_id("sherlock-monitor").is_some() {
                    // If hiding fails, leave the normal close action available.
                    if window.hide().is_ok() { api.prevent_close(); }
                }
            }
        })
        .invoke_handler(tauri::generate_handler![
            backend_call, monitor_status, refresh_state,
            background::startup_status, background::set_startup_enabled, background::set_locale
        ])
        .run(tauri::generate_context!())
        .expect("error while running SherlockPC desktop");
}
