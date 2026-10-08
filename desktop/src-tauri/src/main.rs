// The desktop app must never own a terminal. Closing a console would kill the
// native monitoring worker, bypassing the window's close-to-tray handler.
#![cfg_attr(target_os = "windows", windows_subsystem = "windows")]

fn main() {
    sherlockpc_desktop_lib::run();
}
