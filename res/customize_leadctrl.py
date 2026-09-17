"""Apply the LeadCtrl client configuration to the checked-out build sources."""

import base64
import argparse
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
        f'            ("{key}".to_owned(), "{value}".to_owned()),'
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


def customize(root=ROOT, edition="full"):
    if edition not in ("full", "lite"):
        raise ValueError("Unknown client edition")
    SERVER, PUBLIC_KEY = read_build_config()

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
    if edition == "lite":
        builtin.update({key: "Y" for key in (
            "hide-general-settings", "hide-security-settings",
            "hide-network-settings", "hide-remote-printer-settings",
        )})
        config = replace_once(
            config,
            'pub static ref HARD_SETTINGS: RwLock<HashMap<String, String>> = Default::default();',
            settings_initializer("HARD_SETTINGS", {
                "conn-type": "incoming", "disable-account": "Y", "disable-ab": "Y",
            }),
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
    if edition == "lite":
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
    print("LeadCtrl configuration embedded and locked; edition:", edition)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--edition", choices=("full", "lite"), default="full")
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    if args.validate_only:
        read_build_config()
        print("LeadCtrl build configuration validated")
    else:
        customize(edition=args.edition)
