"""Apply the LeadCtrl client configuration to the checked-out build sources."""

import base64
import argparse
import json
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(source, old, new):
    if source.count(old) != 1:
        raise RuntimeError("Upstream source changed; refusing to build an unconfigured client")
    return source.replace(old, new, 1)


def settings_initializer(name, values):
    entries = '\n'.join(
        f'            ({json.dumps(key, ensure_ascii=False)}.to_owned(), '
        f'{json.dumps(value, ensure_ascii=False)}.to_owned()),'
        for key, value in values.items()
    )
    return (f'pub static ref {name}: RwLock<HashMap<String, String>> = '
            f'RwLock::new(vec![\n{entries}\n        ].into_iter().collect());')


def read_build_config():
    server = os.environ.get("LEADCTRL_SERVER", "").strip()
    public_key = os.environ.get("LEADCTRL_PUBLIC_KEY", "").strip()
    if not server or not public_key:
        raise ValueError("LEADCTRL_SERVER and LEADCTRL_PUBLIC_KEY are required")
    if len(server) > 253 or not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?", server):
        raise ValueError("LEADCTRL_SERVER must be a hostname or IPv4 address without a port")
    try:
        decoded = base64.b64decode(public_key, validate=True)
    except ValueError:
        raise ValueError("LEADCTRL_PUBLIC_KEY must be valid Base64") from None
    if len(decoded) != 32:
        raise ValueError("LEADCTRL_PUBLIC_KEY must encode 32 bytes")
    return server, public_key


def read_unattended_password():
    password = os.environ.get("LEADCTRL_UNATTENDED_PASSWORD", "")
    if not 10 <= len(password) <= 64 or any(ord(char) < 32 for char in password):
        raise ValueError("LEADCTRL_UNATTENDED_PASSWORD must contain 10-64 printable characters")
    return password


def customize(root=ROOT, edition="full"):
    if edition not in ("full", "lite", "android"):
        raise ValueError("Unknown client edition")
    SERVER, PUBLIC_KEY = read_build_config()
    unattended_password = read_unattended_password() if edition == "android" else ""

    config_path = root / "libs/hbb_common/src/config.rs"
    config = config_path.read_text(encoding="utf-8")
    config = replace_once(
        config,
        'pub const RENDEZVOUS_SERVERS: &[&str] = &["rs-ny.rustdesk.com"];',
        f'pub const RENDEZVOUS_SERVERS: &[&str] = &["{SERVER}"];',
    )

    builtin = {
        "hide-server-settings": "Y",
        "allow-deep-link-server-settings": "N",
    }
    if edition in ("lite", "android"):
        builtin.update({key: "Y" for key in (
            "hide-general-settings", "hide-security-settings",
            "hide-network-settings", "hide-remote-printer-settings",
        )})
        if edition == "android":
            builtin.update({
                "disable-change-permanent-password": "Y",
                "remove-preset-password-warning": "Y",
            })
        hard_settings = {
            "conn-type": "incoming", "disable-account": "Y", "disable-ab": "Y",
        }
        if edition == "android":
            hard_settings.update({
                "approve-mode": "password",
                "verification-method": "use-permanent-password",
                "password": unattended_password,
            })
        config = replace_once(
            config,
            'pub static ref HARD_SETTINGS: RwLock<HashMap<String, String>> = Default::default();',
            settings_initializer("HARD_SETTINGS", hard_settings),
        )
    config = replace_once(
        config,
        'pub static ref BUILTIN_SETTINGS: RwLock<HashMap<String, String>> = Default::default();',
        settings_initializer("BUILTIN_SETTINGS", builtin),
    )
    config = replace_once(
        config,
        'pub const RS_PUB_KEY: &str = "OeVuKk5nlHiXp+APNn0Y3pC1Iwpwn44JGqrQCsWqmBw=";',
        f'pub const RS_PUB_KEY: &str = "{PUBLIC_KEY}";',
    )
    config = replace_once(
        config,
        'pub static ref OVERWRITE_SETTINGS: RwLock<HashMap<String, String>> = Default::default();',
        '''pub static ref OVERWRITE_SETTINGS: RwLock<HashMap<String, String>> = RwLock::new(
        vec![
            ("custom-rendezvous-server".to_owned(), "%s".to_owned()),
            ("relay-server".to_owned(), "%s".to_owned()),
            ("key".to_owned(), "%s".to_owned()),
        ].into_iter().collect()
    );''' % (SERVER, SERVER, PUBLIC_KEY),
    )

    # Windows also accepts server parameters from the executable filename.
    windows_path = root / "src/platform/windows.rs"
    windows = windows_path.read_text(encoding="utf-8")
    old = '''pub fn get_license_from_exe_name() -> ResultType<CustomServer> {
    let mut exe = std::env::current_exe()?.to_str().unwrap_or("").to_owned();
    // if defined portable appname entry, replace original executable name with it.
    if let Ok(portable_exe) = std::env::var(PORTABLE_APPNAME_RUNTIME_ENV_KEY) {
        exe = portable_exe;
    }
    get_custom_server_from_string(&exe)
}'''
    windows = replace_once(windows, old, '''pub fn get_license_from_exe_name() -> ResultType<CustomServer> {
    Ok(CustomServer {
        host: "%s".to_owned(),
        relay: "%s".to_owned(),
        key: "%s".to_owned(),
        api: String::new(),
    })
}''' % (SERVER, SERVER, PUBLIC_KEY))

    client_path = root / "src/client.rs"
    client = None
    if edition in ("lite", "android"):
        client = replace_once(
            client_path.read_text(encoding="utf-8"),
            'if config::is_incoming_only() && !is_switch_sides_back(conn_type, &interface).await {',
            'if config::is_incoming_only() {',
        )

    # Write only after every source match has passed.
    config_path.write_text(config, encoding="utf-8")
    windows_path.write_text(windows, encoding="utf-8")
    if client is not None:
        client_path.write_text(client, encoding="utf-8")

    if edition == "android":
        android_root = root / "flutter/android/app"

        gradle_path = android_root / "build.gradle"
        gradle = replace_once(
            gradle_path.read_text(encoding="utf-8"),
            'applicationId "com.carriez.flutter_hbb"',
            'applicationId "cn.leadctrl.remoteassist"',
        )

        manifest_path = android_root / "src/main/AndroidManifest.xml"
        manifest = manifest_path.read_text(encoding="utf-8")
        manifest = replace_once(manifest, 'android:label="RustDesk"', 'android:label="@string/app_name"')
        manifest = replace_once(
            manifest,
            'android:label="RustDesk Input"',
            'android:label="LeadCtrl 远程控制"',
        )

        strings_path = android_root / "src/main/res/values/strings.xml"
        strings = strings_path.read_text(encoding="utf-8")
        strings = replace_once(strings, '<string name="app_name">RustDesk</string>',
                               '<string name="app_name">LeadCtrl 远程协助</string>')
        strings = strings.replace("RustDesk", "LeadCtrl")

        kotlin_root = android_root / "src/main/kotlin/com/carriez/flutter_hbb"
        boot_path = kotlin_root / "BootReceiver.kt"
        boot = boot_path.read_text(encoding="utf-8")
        boot = replace_once(boot, 'getBoolean(KEY_START_ON_BOOT_OPT, false)',
                            'getBoolean(KEY_START_ON_BOOT_OPT, true)')
        boot = replace_once(boot, '"RustDesk is Open"', '"LeadCtrl 远程协助已启动"')

        activity_path = kotlin_root / "MainActivity.kt"
        activity = replace_once(
            activity_path.read_text(encoding="utf-8"),
            'getBoolean(KEY_START_ON_BOOT_OPT, false)',
            'getBoolean(KEY_START_ON_BOOT_OPT, true)',
        )

        service_path = kotlin_root / "MainService.kt"
        service = service_path.read_text(encoding="utf-8")
        service = replace_once(service, 'const val DEFAULT_NOTIFY_TITLE = "RustDesk"',
                               'const val DEFAULT_NOTIFY_TITLE = "LeadCtrl 远程协助"')
        service = replace_once(service, 'val channelId = "RustDesk"',
                               'val channelId = "LeadCtrlRemoteAssist"')
        service = replace_once(service, 'val channelName = "RustDesk Service"',
                               'val channelName = "LeadCtrl 远程协助服务"')

        gradle_path.write_text(gradle, encoding="utf-8")
        manifest_path.write_text(manifest, encoding="utf-8")
        strings_path.write_text(strings, encoding="utf-8")
        boot_path.write_text(boot, encoding="utf-8")
        activity_path.write_text(activity, encoding="utf-8")
        service_path.write_text(service, encoding="utf-8")
    print("LeadCtrl configuration embedded and locked; edition:", edition)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--edition", choices=("full", "lite", "android"), default="full")
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    if args.validate_only:
        read_build_config()
        print("LeadCtrl build configuration validated")
    else:
        customize(edition=args.edition)
