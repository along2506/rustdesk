# LeadCtrl R3 privacy changes

Windows Privacy Mode 2 snapshots the active physical display dimensions and
desktop positions before hotplugging. The Amyuni path registers these dimensions
in the driver's documented registry mode list, creates one virtual display per
physical display (up to four), and applies the original desktop layout. It checks
every requested mode before disabling physical displays, then checks the active
display count, dimensions, positions and physical-display deactivation before
reporting success. Failure invokes the existing display restoration guard.

The privacy path no longer runs either the immediate or delayed 1920x1080 reset.
Headless/manual virtual displays and the alternative RustDesk IDD path retain
their existing behavior. Existing virtual monitors must be turned off before
entering this mode; they are not silently removed to make room. Amyuni supports
ten registered resolutions: current physical dimensions take priority, with
remaining slots retaining previous driver modes. The signed INF is not changed.
If the running driver has cached its previous mode list, the attempt reports an
unsupported-mode error rather than substituting 1080p. A driver restart may be
needed before retrying. The client does not automatically restart the driver.

This preserves pixel dimensions and desktop positions, not display device IDs,
DPI scaling, refresh rates, HDR state or application window placement. Windows
enumerates replacement displays as different devices. Hardware acceptance is
still required, including exit, reconnect and failure recovery.

Privacy Mode 1 initializes STARTUPINFOW correctly, explicitly selects the
interactive desktop, passes an unambiguous executable path and writable command
line, allows more time for broker startup, and includes its process status in a
startup failure. All physical-monitor coverage checks remain in place. These
changes address startup defects but do not establish the root cause of every
zero-window error; endpoint validation is required.

## Hardware acceptance

- Capture the Windows display layout before entering privacy mode. The reported
  four-screen case is 2880x1920 (primary), 2560x1600, 2560x1600 and 3400x1440;
  the implementation reads the actual current values instead of hardcoding them.
- Mode 2: all four physical screens must be private and the remote desktop must
  retain all four pixel dimensions and positions, including negative coordinates.
- Exit and disconnect: original physical layout must return. Repeat entry/exit
  and reconnect, checking for delayed 1080p changes and leaked virtual monitors.
- Unsupported modes, an existing virtual monitor and failed hotplug must fail
  without a success indication or silently reduced resolution.
- Mode 1: test all four monitors, mixed DPI, lock/unlock and repeated entry/exit.
  No success is allowed until every physical screen has a visible privacy window.

## Regression surface

- `src/privacy_mode/win_virtual_display.rs`: Amyuni privacy entry, verification
  and rollback; required for one-to-one physical/virtual layout preservation.
- `src/virtual_display_manager.rs`: privacy-only mode registration and hotplug;
  existing callers explicitly retain their delayed 1080p reset.
- `src/privacy_mode/win_topmost_window.rs`: privacy broker startup and diagnostics.
- `.github/workflows/leadctrl-windows.yml`: trigger privacy source changes and
  publish distinct R3 installers; secrets injection remains unchanged.
- `flutter/lib/desktop/pages/desktop_setting_page.dart`: display R3 to distinguish
  the test build from previously installed R2 clients.

Source parsing/formatting and synthetic server-configuration tests are local
checks. The Windows CI build checks compilation; neither replaces the hardware
acceptance above. Do not label this prerelease as endpoint-validated until tested.
