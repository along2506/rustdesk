# LeadCtrl client builds

Build the `leadctrl-client` branch using `.github/workflows/leadctrl-windows.yml`.
It produces Windows x64 EXE/MSI installers for `full` and `lite` editions.

Configure these repository Actions secrets before running it:

- `LEADCTRL_SERVER`: ID/relay hostname (or IPv4 address), without scheme or port.
- `LEADCTRL_PUBLIC_KEY`: Base64-encoded 32-byte server public key, never the private key.

There are no deployment-specific defaults. Missing or malformed configuration
stops the build before compilation. The workflow passes secrets through step-local
environment variables, validates them early and injects them just before compiling.
The script does not print their values. A cleanup step restores injected source
files even after failure. Client Rust build caches are disabled; caches for
unconfigured bridge generation and third-party dependencies remain enabled.
Only finished installers are uploaded by the client build job.

The values still exist temporarily in the runner's modified source and compiled
files, and are embedded in the distributed installers. They are not secrets from
someone who can inspect a client binary. Existing Git history, earlier branches,
old caches, previous workflow runs and previously distributed installers are not
erased by this change.

For a local build, supply the two environment variables through your own secret
manager, then run `python res/customize_leadctrl.py --edition full` (or `lite`)
before the usual RustDesk Windows build. Do not commit the resulting source changes.
Tests use synthetic configuration: `python res/test_leadctrl_config.py` with the
repository submodules checked out, before applying deployment configuration.

Regression scope: `customize_leadctrl.py` changes only where build configuration
comes from and adds input validation. The dedicated workflow changes secret
injection, tests, caching and cleanup. The legacy `flutter-build.yml` no longer
contains the previous hard-coded Windows customization; use the dedicated
LeadCtrl workflow for company builds. Connection behavior, branding, the About
notice and the full/lite restrictions are preserved.
