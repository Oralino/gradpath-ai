"""The API runs without the optional dependency groups (T-025).

The Docker image installs only `[project] dependencies` (`uv sync --no-default-groups`); the
`local`, `eval` and `ingest` groups are left out. Tests and CI install every group, so without
this check a new top-level import of one of them would pass here and break only on Render.
"""

import re
import subprocess
import sys
from pathlib import Path

# Top-level modules of the groups the image leaves out. Keep in step with pyproject.toml
# [dependency-groups] local, eval and ingest when a library is added to one of them.
# langchain_text_splitters is not listed: langchain-voyageai pulls it into the runtime set anyway.
LEFT_OUT = ["claude_agent_sdk", "fastembed", "onnxruntime", "bs4", "pypdf"]

SCRIPT = f"""
import importlib.abc, sys

class Block(importlib.abc.MetaPathFinder):
    def find_spec(self, name, path=None, target=None):
        if name.split(".")[0] in {LEFT_OUT!r}:
            raise ModuleNotFoundError(f"{{name}} is not in the runtime image")
        return None

sys.meta_path.insert(0, Block())
import gradpath.api.main as main
import gradpath.retrieval.guarded, gradpath.retrieval.service
main.create_app()
leaked = sorted(m for m in sys.modules if m.split(".")[0] in {LEFT_OUT!r})
assert not leaked, leaked
print("ok")
"""


def test_api_imports_without_optional_groups() -> None:
    """Import the app, every router it mounts and the retrieval stack with the left-out modules
    blocked, in a fresh interpreter so this test's own imports don't count."""
    proc = subprocess.run(
        [sys.executable, "-c", SCRIPT], capture_output=True, text=True, timeout=300
    )
    assert proc.returncode == 0, proc.stderr[-2000:]
    assert proc.stdout.strip().endswith("ok")


SRC = Path(__file__).resolve().parents[1] / "src" / "gradpath"
# The only files allowed to import a left-out module, each reached only from local runs, evals or
# index building (never from api/): a lazy import on a request path elsewhere would pass the
# import test above and still fail on Render.
ALLOWED = {
    "providers/claude_code.py",
    "retrieval/sparse.py",
    "retrieval/rerank.py",
    "ingestion/clean.py",
}
IMPORT = re.compile(r"^\s*(?:from|import)\s+(" + "|".join(LEFT_OUT) + r")\b", re.MULTILINE)


def test_left_out_modules_imported_only_in_allowed_files() -> None:
    """Static check of every source file, including imports inside functions."""
    offenders = sorted(
        str(p.relative_to(SRC).as_posix())
        for p in SRC.rglob("*.py")
        if IMPORT.search(p.read_text(encoding="utf-8"))
        and p.relative_to(SRC).as_posix() not in ALLOWED
    )
    assert not offenders, offenders
