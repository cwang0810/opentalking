from __future__ import annotations

import asyncio
import zipfile
from pathlib import Path

import pytest

from opentalking.agent.knowledge_store import KnowledgeStore
from opentalking.persona.package import (
    create_persona_package_from_dir,
    import_persona_package,
    validate_persona_package,
)
from opentalking.persona.schema import persona_from_dict
from opentalking.persona.store import PersonaStore


def _write_persona_source(root: Path) -> None:
    (root / "prompts").mkdir(parents=True)
    (root / "knowledge" / "docs").mkdir(parents=True)
    (root / "prompts" / "system.md").write_text("你是企业客服数字人。", encoding="utf-8")
    (root / "knowledge" / "docs" / "product.md").write_text(
        "OpenTalking 支持 Persona Package。",
        encoding="utf-8",
    )
    (root / "persona.json").write_text(
        """
{
  "schema_version": "0.1",
  "id": "customer-support-zh",
  "name": "中文客服",
  "description": "企业售前客服数字人",
  "locale": "zh-CN",
  "avatar": {"id": "singer", "model": "mock"},
  "voice": {"provider": "edge", "voice_id": "zh-CN-XiaoxiaoNeural"},
  "agent": {
    "system_prompt": "prompts/system.md",
    "memory_enabled": true,
    "knowledge_enabled": true
  },
  "runtime": {"stt_provider": "sensevoice", "tts_provider": "edge"},
  "safety": {
    "authorized_avatar": true,
    "authorized_voice": true,
    "content_label_required": true
  }
}
""".strip()
        + "\n",
        encoding="utf-8",
    )


def test_persona_schema_validates_required_fields() -> None:
    manifest = persona_from_dict(
        {
            "schema_version": "0.1",
            "id": "support_zh",
            "name": "客服",
            "description": "客服角色",
            "locale": "zh-CN",
            "avatar": {"id": "singer", "model": "mock"},
        }
    )

    assert manifest.id == "support_zh"
    assert manifest.agent.knowledge_enabled is True

    with pytest.raises(ValueError, match="persona missing field: avatar"):
        persona_from_dict(
            {
                "schema_version": "0.1",
                "id": "bad",
                "name": "bad",
                "description": "bad",
                "locale": "zh-CN",
            }
        )


def test_persona_package_rejects_path_traversal(tmp_path: Path) -> None:
    package = tmp_path / "bad.otpersona"
    with zipfile.ZipFile(package, "w") as zf:
        zf.writestr("persona.json", "{}")
        zf.writestr("../escape.txt", "x")

    with pytest.raises(ValueError, match="unsafe persona package path"):
        validate_persona_package(package)


def test_persona_package_imports_prompt_and_knowledge(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    _write_persona_source(source)
    package = tmp_path / "customer-support-zh.otpersona"
    create_persona_package_from_dir(source, package)

    store = PersonaStore(tmp_path / "personas")
    knowledge_store = KnowledgeStore(
        db_path=tmp_path / "agent.sqlite",
        knowledge_root=tmp_path / "knowledge",
    )

    record = asyncio.run(
        import_persona_package(package, store=store, knowledge_store=knowledge_store)
    )

    assert record.manifest.id == "customer-support-zh"
    assert record.manifest.agent.system_prompt == "prompts/_compiled_system.md"
    assert record.manifest.agent.knowledge_base_ids
    prompt = (record.path / "prompts" / "_compiled_system.md").read_text(encoding="utf-8")
    assert "企业客服数字人" in prompt
    bases = asyncio.run(knowledge_store.list_knowledge_bases())
    assert any(base.id == record.manifest.agent.knowledge_base_ids[0] for base in bases)
