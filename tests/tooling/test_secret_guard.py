"""The pre-commit secret guard refuses key-shaped content and .env files.

Fake keys are built by concatenation so this file never contains the pattern itself.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
FAKE_ANTHROPIC = "sk-" + "ant-" + "x" * 20
FAKE_GOOGLE = "AI" + "za" + "B" * 35


def git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    git(tmp_path, "init", "-q")
    git(tmp_path, "config", "user.email", "guard@example.invalid")
    git(tmp_path, "config", "user.name", "guard test")
    git(tmp_path, "config", "commit.gpgsign", "false")
    out = subprocess.run(["sh", str(ROOT / "scripts" / "install_hooks.sh")], cwd=tmp_path,
                         capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    return tmp_path


def commit(repo: Path, name: str, content: str) -> subprocess.CompletedProcess:
    path = repo / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    git(repo, "add", "-f", name)
    return git(repo, "commit", "-q", "-m", f"add {name}")


def test_fake_anthropic_key_is_refused(repo: Path) -> None:
    res = commit(repo, "config.py", f'KEY = "{FAKE_ANTHROPIC}"\n')
    assert res.returncode != 0
    assert "config.py" in res.stderr
    assert FAKE_ANTHROPIC not in res.stderr + res.stdout


def test_fake_google_key_is_refused(repo: Path) -> None:
    res = commit(repo, "notes/keys.md", f"google {FAKE_GOOGLE}\n")
    assert res.returncode != 0
    assert "notes/keys.md" in res.stderr
    assert FAKE_GOOGLE not in res.stderr + res.stdout


def test_staged_env_file_is_refused(repo: Path) -> None:
    res = commit(repo, ".env", "WHYLINE_MODE=replay\n")
    assert res.returncode != 0
    assert ".env" in res.stderr


def test_clean_commit_passes(repo: Path) -> None:
    res = commit(repo, "README.md", "hello\n")
    assert res.returncode == 0, res.stderr


def test_bare_prefixes_in_docs_pass(repo: Path) -> None:
    for doc in ("README.md", "LICENSES.md"):
        shutil.copy(ROOT / doc, repo / doc)
        git(repo, "add", doc)
    res = git(repo, "commit", "-q", "-m", "docs")
    assert res.returncode == 0, res.stderr
