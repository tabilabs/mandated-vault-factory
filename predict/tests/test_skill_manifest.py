from __future__ import annotations

from conftest import get_predict_root, parse_skill_frontmatter


def test_skill_manifest_openclaw_contract() -> None:
    skill_path = get_predict_root() / "SKILL.md"
    frontmatter, body = parse_skill_frontmatter(skill_path)

    assert frontmatter["name"] == "predictclaw"
    assert "description" in frontmatter

    openclaw = frontmatter["metadata"]["openclaw"]
    assert openclaw["emoji"]
    assert openclaw["homepage"] == "https://predict.fun"
    assert openclaw["primaryEnv"] == "PREDICT_PRIVATE_KEY"
    assert "uv" in openclaw["requires"]["bins"]
    assert "PREDICT_PRIVATE_KEY" in openclaw["requires"]["env"]
    assert "install" in openclaw

    assert "{baseDir}" in body
    assert "~/.openclaw/skills/predictclaw/" in body
    assert "skills.entries.predictclaw.env" in body


def test_skill_manifest_uses_openclaw_single_line_metadata_json() -> None:
    skill_path = get_predict_root() / "SKILL.md"
    text = skill_path.read_text()
    frontmatter_text = text.split("---\n", 2)[1]

    metadata_lines = [
        line for line in frontmatter_text.splitlines() if line.startswith("metadata:")
    ]
    assert len(metadata_lines) == 1
    assert metadata_lines[0].startswith("metadata: {")
    assert '"openclaw"' in metadata_lines[0]


def test_openclaw_install_examples_are_valid() -> None:
    skill_path = get_predict_root() / "SKILL.md"
    _frontmatter, body = parse_skill_frontmatter(skill_path)

    assert "cd {baseDir} && uv sync" in body
    assert "manual install" in body.lower()
    assert "predict account" in body.lower()
    assert "wallet deposit" in body
    assert "wallet withdraw" in body
