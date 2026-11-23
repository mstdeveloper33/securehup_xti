"""Keep application decisions independent of persistence and user interfaces."""

import ast
from pathlib import Path
import unittest


class ArchitectureTests(unittest.TestCase):
    def test_domain_and_application_do_not_depend_on_concrete_adapters(self):
        source_root = Path(__file__).resolve().parents[1] / "src" / "xti"
        for layer in ("domain", "application", "ports"):
            files = list((source_root / layer).rglob("*.py"))
            self.assertTrue(files, f"Expected implementation for {layer}")
            for path in files:
                tree = ast.parse(path.read_text(encoding="utf-8"))
                for node in ast.walk(tree):
                    modules = []
                    if isinstance(node, ast.Import):
                        modules = [item.name for item in node.names]
                    elif isinstance(node, ast.ImportFrom):
                        modules = [node.module or ""]
                    for module in modules:
                        with self.subTest(path=path, imported=module):
                            parts = set(module.split("."))
                            self.assertFalse(parts & {"sqlite3", "adapters", "interfaces", "argparse"})

    def test_terminal_source_catalog_has_one_canonical_application_service(self):
        path = (
            Path(__file__).resolve().parents[1]
            / "src" / "xti" / "interfaces" / "cli.py"
        )
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imports = {
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
        }
        self.assertIn("xti.application.source_governance", imports)
        self.assertNotIn("xti.application.sources", imports)


if __name__ == "__main__":
    unittest.main()
