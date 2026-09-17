import base64
import contextlib
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import customize_leadctrl as customize


class BuildConfigTests(unittest.TestCase):
    def setUp(self):
        self.values = {
            "LEADCTRL_SERVER": "relay.example.invalid",
            "LEADCTRL_PUBLIC_KEY": base64.b64encode(bytes(range(32))).decode(),
        }

    def test_missing_and_invalid_config_is_rejected_without_echoing_values(self):
        cases = [{}, {"LEADCTRL_SERVER": self.values["LEADCTRL_SERVER"]}]
        cases += [dict(self.values, **{name: value}) for name, value in (
            ("LEADCTRL_SERVER", 'bad"; injected'),
            ("LEADCTRL_SERVER", "server.invalid\nsecond-line"),
            ("LEADCTRL_PUBLIC_KEY", "not-a-public-key"),
            ("LEADCTRL_PUBLIC_KEY", base64.b64encode(b"short").decode()),
        )]
        for values in cases:
            with self.subTest(values=list(values)), patch.dict(os.environ, values, clear=True):
                with self.assertRaises(ValueError) as error:
                    customize.read_build_config()
                for value in values.values():
                    self.assertNotIn(value, str(error.exception))

    def test_both_editions_on_pinned_sources(self):
        config_source = Path(os.environ.get(
            "LEADCTRL_TEST_CONFIG_SOURCE",
            str(customize.ROOT / "libs/hbb_common/src/config.rs"),
        )).read_text(encoding="utf-8")
        windows_source = (customize.ROOT / "src/platform/windows.rs").read_text(encoding="utf-8")
        client_source = (customize.ROOT / "src/client.rs").read_text(encoding="utf-8")
        for edition in ("full", "lite"):
            with self.subTest(edition=edition), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                sources = {
                    "libs/hbb_common/src/config.rs": config_source,
                    "src/platform/windows.rs": windows_source,
                    "src/client.rs": client_source,
                }
                for path, source in sources.items():
                    destination = root / path
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    destination.write_text(source, encoding="utf-8")
                output = io.StringIO()
                with patch.dict(os.environ, self.values, clear=True), contextlib.redirect_stdout(output):
                    customize.customize(root, edition)
                for value in self.values.values():
                    self.assertNotIn(value, output.getvalue())
                config = (root / "libs/hbb_common/src/config.rs").read_text(encoding="utf-8")
                for value in self.values.values():
                    self.assertIn(value, config)
                self.assertIn('("hide-server-settings".to_owned(), "Y".to_owned())', config)
                incoming = '("conn-type".to_owned(), "incoming".to_owned())'
                client = (root / "src/client.rs").read_text(encoding="utf-8")
                if edition == "lite":
                    self.assertIn(incoming, config)
                    self.assertNotIn('if config::is_incoming_only() && !is_switch_sides_back', client)
                else:
                    self.assertNotIn(incoming, config)
                    self.assertEqual(client, client_source)
                before = (root / "libs/hbb_common/src/config.rs").read_bytes()
                with patch.dict(os.environ, self.values, clear=True):
                    with self.assertRaises(RuntimeError):
                        customize.customize(root, edition)
                self.assertEqual(before, (root / "libs/hbb_common/src/config.rs").read_bytes())


if __name__ == "__main__":
    unittest.main()
