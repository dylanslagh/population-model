"""The conversation export does not leak what it promises to remove.

This is the only part of the repository whose output is published verbatim
rather than computed, so the checks here are about redaction and filtering
rather than about numbers being right.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from popmodel import paths

SCRIPT = paths.REPO_ROOT / "scripts" / "export_conversations.py"
CONVERSATIONS = paths.REPO_ROOT / "conversations"


def load_exporter():
    """Import the script by path.

    It has to be registered in `sys.modules` before it is executed: the module
    uses postponed annotations, so `@dataclass` resolves its field types by
    looking its own module up by name, and fails confusingly if it is not there.
    """
    if "export_conversations" in sys.modules:
        return sys.modules["export_conversations"]
    spec = importlib.util.spec_from_file_location("export_conversations", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules["export_conversations"] = module
    spec.loader.exec_module(module)
    return module


def test_home_directory_is_redacted_in_every_form_the_tools_emit():
    export = load_exporter()
    home = str(Path.home())
    drive, rest = home[0], home[2:].replace("\\", "/")
    for form in (home, home.replace("\\", "/"), f"/{drive.lower()}{rest}"):
        assert export.clean(f"reading {form}/x.txt") == "reading ~/x.txt"


def test_encoded_scratch_paths_are_redacted_too():
    """Redacting one form of the username and not another reads as deliberate."""
    export = load_exporter()
    user = Path.home().name
    cleaned = export.clean(f"Temp/claude/C--Users-{user}-Documents-GitHub-thing/abc")
    assert user not in cleaned


def test_harness_scaffolding_is_not_treated_as_conversation():
    export = load_exporter()
    for injected in ("<system-reminder>do a thing</system-reminder>",
                     "<task-notification>done</task-notification>",
                     "[SYSTEM NOTIFICATION - NOT USER INPUT]",
                     "<command-name>/loop</command-name>"):
        assert export.is_injected(injected), injected
    assert not export.is_injected("Time to work on the paper")


def test_a_credential_shaped_string_stops_the_export():
    export = load_exporter()
    with pytest.raises(SystemExit):
        export.scan_for_secrets("token ghp_" + "a" * 30, "a test")


def test_tool_summaries_do_not_carry_output():
    """A tool line is a label. Anything longer is output creeping back in."""
    export = load_exporter()
    line = export.summarise_tool("Read", {"file_path": "x" * 400})
    assert len(line) < 160


@pytest.mark.skipif(not CONVERSATIONS.exists(), reason="not exported yet")
def test_exported_files_carry_no_scaffolding_or_credentials():
    for path in CONVERSATIONS.glob("*.md"):
        text = path.read_text(encoding="utf-8")
        for marker in ("<system-reminder>", "[SYSTEM NOTIFICATION",
                       "<task-notification>"):
            assert marker not in text, f"{path.name} contains {marker}"
        for pattern in load_exporter().SECRET_PATTERNS:
            assert not pattern.search(text), f"{path.name} matches {pattern.pattern}"
