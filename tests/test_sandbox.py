"""Code sandbox: AST gate and subprocess limits. Runs real Python, no models."""
from __future__ import annotations

import pytest

from backend.sandbox import runner


def test_passing_code_and_tests():
    r = runner.run_python("def double(x):\n    return 2 * x\n", "assert double(3) == 6\nprint('ok')")
    if not r.ok and "sandbox_apply" in r.stderr:
        pytest.skip("sandbox-exec can't nest inside this test runner's sandbox")
    assert r.ok and r.stdout.strip() == "ok"


def test_failing_test_reports_assertion():
    r = runner.run_python("def double(x):\n    return x\n", "assert double(3) == 6")
    assert not r.ok and r.blocked is None


@pytest.mark.parametrize("code", [
    "import os\nos.system('ls')",
    "import subprocess",
    "from socket import socket",
    "import ctypes",
    "open('/etc/passwd').read()",
    "eval('1+1')",
    "__import__('os')",
    "().__class__.__bases__[0].__subclasses__()",
    "from . import x",
    "import io\nio.open('x')",
])
def test_ast_gate_blocks_dangerous_code(code):
    assert runner.ast_gate(code) is not None
    assert runner.run_python(code).blocked


def test_pandas_only_in_data_profile():
    assert runner.ast_gate("import pandas as pd") is not None
    assert runner.ast_gate("import pandas as pd", profile="data") is None


def test_allowed_stdlib():
    assert runner.ast_gate("import math, re, collections\nfrom itertools import chain") is None
    assert runner.ast_gate("xs = [1, 2]\nxs.remove(1)") is None
    assert runner.ast_gate("import io, pandas as pd\npd.read_csv(io.StringIO('a\\n1'))", profile="data") is None


def test_parse_reply_splits_code_and_tests():
    from backend.workers.code import parse_reply

    raw = 'Uses a set.\n```python\ndef f(s):\n    return "x" in s\n```\n```python\nassert f("x")\n```'
    d = parse_reply(raw)
    assert d.explanation == "Uses a set." and d.code.startswith("def f") and d.tests == 'assert f("x")'
    d = parse_reply("```python\ndef g():\n    return 1\nassert g() == 1\n```")
    assert d.code.endswith("return 1") and d.tests == "assert g() == 1"
    d = parse_reply("(1) Uses math.\n\nHere's the code:\n```python\nx = 1\n```")
    assert d.explanation == "Uses math."


def test_add_missing_imports():
    from backend.workers.code import add_missing_imports

    allowed = runner.allowed_modules("data")
    out = add_missing_imports("def f(x):\n    return math.sqrt(x) + len(io.StringIO('a').read())", allowed)
    assert out.startswith("import io\nimport math\n")
    assert add_missing_imports("import math\nmath.pi", allowed) == "import math\nmath.pi"
    assert add_missing_imports("df = pd.DataFrame()", allowed).startswith("import pandas as pd\n")
    assert add_missing_imports("obj.value + self.x", allowed) == "obj.value + self.x"


def test_syntax_error_is_reported():
    assert "syntax error" in runner.ast_gate("def f(:\n  pass")
    r = runner.run_python("def f(:\n  pass")
    assert not r.ok and r.blocked is None and "syntax error" in r.stderr


def test_timeout_kills_the_process():
    r = runner.run_python("while True:\n    pass", timeout_s=1)
    if "sandbox_apply" in r.stderr:
        pytest.skip("sandbox-exec can't nest inside this test runner's sandbox")
    assert r.timed_out and not r.ok


def test_output_is_capped():
    r = runner.run_python("print('x' * 100000)")
    if "sandbox_apply" in r.stderr:
        pytest.skip("sandbox-exec can't nest inside this test runner's sandbox")
    assert len(r.stdout.encode()) < 25000 and "output cut" in r.stdout
