"""Type-checks every Python sample in README.md, the examples and the smoke
quickstart with pyright against src/, so the docs can't drift from the library.

    python scripts/check_docs.py   (needs pyright: pip install pyright==1.1.414)
"""
import pathlib
import re
import shutil
import subprocess
import sys

root = pathlib.Path(__file__).resolve().parent.parent
out = root / "build-docs-check"
shutil.rmtree(out, ignore_errors=True)
out.mkdir()

# Names the README samples assume from earlier samples.
PRELUDE = """import os
import uuid
import typing
from blujay import Blujay, MessageInputParams
message: MessageInputParams = {"parts": [{"type": "text", "text": "hi"}]}
raw_body = b""
class _Request:
    headers: typing.Dict[str, str] = {}
request = _Request()
"""
blocks = re.findall(r"```python\n(.*?)```", (root / "README.md").read_text(), re.S)
for i, code in enumerate(blocks):
    # Samples that don't create a client use the one from the Usage sample.
    prelude = PRELUDE if re.search(r"^client = ", code, re.M) else PRELUDE + "client = Blujay()\n"
    (out / f"readme_{i}.py").write_text(prelude + code)
for path in (root / "examples").glob("*.py"):
    shutil.copy(path, out / f"example_{path.name}")
shutil.copy(root / "smoke" / "quickstart.py", out / "smoke_quickstart.py")
# Frameworks the samples show but this library doesn't depend on.
(out / "fastapi").mkdir()
(out / "fastapi" / "__init__.pyi").write_text(
    "import typing\n"
    "class Request:\n    headers: typing.Mapping[str, str]\n    async def body(self) -> bytes: ...\n"
    "class FastAPI:\n    def post(self, path: str) -> typing.Callable[[typing.Any], typing.Any]: ...\n"
    "class HTTPException(Exception):\n    def __init__(self, status_code: int) -> None: ...\n"
)

(out / "pyrightconfig.json").write_text(
    '{"extraPaths": ["../src"], "pythonVersion": "3.9", "typeCheckingMode": "basic", "reportMissingModuleSource": false}'
)
result = subprocess.run([sys.executable, "-m", "pyright", "-p", str(out)], cwd=out)
shutil.rmtree(out, ignore_errors=True)
if result.returncode != 0:
    sys.exit(result.returncode)
print(f"check_docs: {len(blocks)} README samples, the examples and the quickstart type-check")
