from __future__ import annotations

import tempfile
from pathlib import Path
import unittest

from atlas_evolution.config import load_config, write_default_config


class ConfigTests(unittest.TestCase):
    def test_relative_paths_resolve_from_config_location(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_path = root / "demo" / "atlas.toml"
            write_default_config(config_path)
            config = load_config(config_path)
            self.assertEqual(config.paths.skills_dir, (root / "demo" / "skills").resolve())
            self.assertEqual(config.paths.state_dir, (root / "demo" / "state").resolve())


if __name__ == "__main__":
    unittest.main()
