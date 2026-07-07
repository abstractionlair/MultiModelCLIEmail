"""Test configuration to ensure local 'code' package is importable.

PyTorch and Python stdlib include a top-level module named 'code'. When pytest
or other libs import stdlib 'code' early, relative imports like
`from code.evaluator_base import ...` will fail because stdlib 'code' is a
module, not a package. This conftest ensures our project-local 'code' package
is available under the 'code' name for tests.
"""

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CODE_DIR = ROOT / "code"

# Ensure project root is on sys.path
sys.path.insert(0, str(ROOT))

# If a 'code' module is already loaded and is not our package, remove it
mod = sys.modules.get("code")
if mod is not None:
    mod_path = getattr(mod, "__file__", "") or ""
    if str(CODE_DIR) not in mod_path:
        # Remove stdlib/module 'code' so we can import our package
        del sys.modules["code"]

# Import or re-load our local 'code' package explicitly
if CODE_DIR.exists() and (CODE_DIR / "__init__.py").exists():
    spec = importlib.util.spec_from_file_location(
        "code",
        CODE_DIR / "__init__.py",
        submodule_search_locations=[str(CODE_DIR)],
    )
    if spec and spec.loader:
        pkg = importlib.util.module_from_spec(spec)
        pkg.__path__ = [str(CODE_DIR)]  # mark as package
        sys.modules["code"] = pkg
        spec.loader.exec_module(pkg)

