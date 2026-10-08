use serde::Serialize;
use std::{fs, path::PathBuf, sync::Mutex};
use tauri::{
    menu::{Menu, MenuItem},
    tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent},
    AppHandle, Manager,
};
use tauri_plugin_autostart::ManagerExt;

#[derive(Default)]
struct StartupState(Mutex<Option<String>>);

#[derive(Serialize)]
pub struct StartupStatus {
    supported: bool,
    enabled: bool,
    error: Option<String>,
}

fn supported() -> bool {
    cfg!(target_os = "windows") && !cfg!(debug_assertions)
}

fn marker_path(app: &AppHandle) -> Result<PathBuf, String> {
    app.path().app_config_dir().map(|path| path.join("startup-initialized-v1"))
        .map_err(|error| error.to_string())
}

fn mark_initialized(app: &AppHandle) -> Result<(), String> {
    let marker = marker_path(app)?;
    if let Some(parent) = marker.parent() {
        fs::create_dir_all(parent).map_err(|error| error.to_string())?;
    }
    fs::write(marker, b"Startup preference initialized.\n").map_err(|error| error.to_string())
}

// Default on only at the first packaged launch. Never undo a later user disable.
fn initialize_startup(app: &AppHandle) -> Result<(), String> {
    if supported() && !marker_path(app)?.exists() {
        app.autolaunch().enable().map_err(|error| error.to_string())?;
        mark_initialized(app)?;
    }
    Ok(())
}

#[tauri::command]
pub fn startup_status(app: AppHandle) -> StartupStatus {
    let initial_error = app.state::<StartupState>().0.lock().ok().and_then(|value| value.clone());
    if !supported() {
        return StartupStatus { supported: false, enabled: false, error: initial_error };
    }
    match app.autolaunch().is_enabled() {
        Ok(enabled) => StartupStatus { supported: true, enabled, error: initial_error },
        Err(error) => StartupStatus { supported: true, enabled: false, error: Some(error.to_string()) },
    }
}

#[tauri::command]
pub fn set_startup_enabled(app: AppHandle, enabled: bool) -> Result<StartupStatus, String> {
    if !supported() { return Err("Autostart is available in the installed Windows release.".into()); }
    // Persist a user's explicit choice before changing OS registration. If the OS
    // call fails, a subsequent launch will not silently re-enable a disabled option.
    mark_initialized(&app)?;
    let manager = app.autolaunch();
    if enabled { manager.enable() } else { manager.disable() }
        .map_err(|error| error.to_string())?;
    *app.state::<StartupState>().0.lock().map_err(|error| error.to_string())? = None;
    Ok(startup_status(app))
}

pub fn show_main(app: &AppHandle) {
    if let Some(window) = app.get_webview_window("main") {
        let _ = window.unminimize();
        let _ = window.show();
        let _ = window.set_focus();
    }
}

struct TrayLabels {
    open: MenuItem<tauri::Wry>,
    quit: MenuItem<tauri::Wry>,
    locale: Mutex<String>,
}

fn locale_catalog(locale: &str) -> Result<serde_json::Value, String> {
    let source = match locale {
        "en" => include_str!("../../src/locales/en.json"),
        "ru" => include_str!("../../src/locales/ru.json"),
        "es" => include_str!("../../src/locales/es.json"),
        "pt-BR" => include_str!("../../src/locales/pt-BR.json"),
        "zh-CN" => include_str!("../../src/locales/zh-CN.json"),
        "fr" => include_str!("../../src/locales/fr.json"),
        "it" => include_str!("../../src/locales/it.json"),
        "de" => include_str!("../../src/locales/de.json"),
        "ja" => include_str!("../../src/locales/ja.json"),
        "ko" => include_str!("../../src/locales/ko.json"),
        "ar" => include_str!("../../src/locales/ar.json"),
        "hi" => include_str!("../../src/locales/hi.json"),
        _ => return Err("Unsupported locale".into()),
    };
    serde_json::from_str(source).map_err(|error| error.to_string())
}

#[tauri::command]
pub fn set_locale(app: AppHandle, locale: String) -> Result<(), String> {
    let catalog = locale_catalog(&locale)?;
    let labels = app.state::<TrayLabels>();
    let mut current = labels.locale.lock().map_err(|error| error.to_string())?;
    if *current == locale { return Ok(()); }
    labels.open.set_text(catalog["trayOpen"].as_str().ok_or("Missing tray label")?).map_err(|error| error.to_string())?;
    labels.quit.set_text(catalog["trayExit"].as_str().ok_or("Missing tray label")?).map_err(|error| error.to_string())?;
    if let Some(tray) = app.tray_by_id("sherlock-monitor") {
        tray.set_tooltip(catalog["trayTooltip"].as_str()).map_err(|error| error.to_string())?;
    }
    let directory = app.path().app_config_dir().map_err(|error| error.to_string())?;
    fs::create_dir_all(&directory).map_err(|error| error.to_string())?;
    fs::write(directory.join("locale.txt"), locale.as_bytes()).map_err(|error| error.to_string())?;
    *current = locale;
    Ok(())
}

pub fn setup(app: &mut tauri::App) -> Result<(), Box<dyn std::error::Error>> {
    app.manage(StartupState::default());
    let locale = app.path().app_config_dir().ok()
        .and_then(|dir| fs::read_to_string(dir.join("locale.txt")).ok())
        .filter(|value| locale_catalog(value).is_ok()).unwrap_or_else(|| "en".into());
    let catalog = locale_catalog(&locale).map_err(std::io::Error::other)?;
    let open = MenuItem::with_id(app, "open", catalog["trayOpen"].as_str().unwrap_or("Open SherlockPC"), true, None::<&str>)?;
    let quit = MenuItem::with_id(app, "quit", catalog["trayExit"].as_str().unwrap_or("Exit — stop collecting"), true, None::<&str>)?;
    let menu = Menu::with_items(app, &[&open, &quit])?;
    app.manage(TrayLabels { open, quit, locale: Mutex::new(locale) });
    let mut builder = TrayIconBuilder::with_id("sherlock-monitor")
        .menu(&menu)
        .tooltip(catalog["trayTooltip"].as_str().unwrap_or("SherlockPC"))
        .show_menu_on_left_click(false)
        .on_menu_event(|app, event| match event.id.as_ref() {
            "open" => show_main(app),
            "quit" => app.exit(0),
            _ => {}
        })
        .on_tray_icon_event(|tray, event| {
            if let TrayIconEvent::Click { button: MouseButton::Left, button_state: MouseButtonState::Up, .. } = event {
                show_main(tray.app_handle());
            }
        });
    if let Some(icon) = app.default_window_icon() { builder = builder.icon(icon.clone()); }
    builder.build(app)?;
    if let Err(error) = initialize_startup(app.handle()) {
        *app.state::<StartupState>().0.lock().map_err(|e| std::io::Error::other(e.to_string()))? = Some(error);
    }
    if !std::env::args().any(|arg| arg == "--background") {
        show_main(app.handle());
    }
    Ok(())
}
