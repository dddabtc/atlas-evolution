from __future__ import annotations

from dataclasses import dataclass
from difflib import unified_diff
import json
from pathlib import Path
import re
from typing import Any

from atlas_evolution.models import Skill, SkillMatch

TOKEN_RE = re.compile(r"[a-z0-9_]+")
STOPWORDS = {
    "a",
    "an",
    "and",
    "for",
    "from",
    "in",
    "of",
    "on",
    "or",
    "the",
    "this",
    "to",
    "with",
}


def tokenize(text: str) -> set[str]:
    return {token for token in TOKEN_RE.findall(text.lower()) if token not in STOPWORDS}


@dataclass(slots=True)
class SkillBank:
    skills: dict[str, Skill]
    sources: dict[str, Path]

    @classmethod
    def from_directory(cls, directory: str | Path) -> "SkillBank":
        skill_dir = Path(directory).expanduser().resolve()
        skills: dict[str, Skill] = {}
        sources: dict[str, Path] = {}
        for file_path in sorted(skill_dir.glob("*.json")):
            raw = json.loads(file_path.read_text(encoding="utf-8"))
            skill = Skill(
                id=raw["id"],
                name=raw["name"],
                description=raw["description"],
                tags=list(raw.get("tags", [])),
                examples=list(raw.get("examples", [])),
                instructions=list(raw.get("instructions", [])),
                metadata=dict(raw.get("metadata", {})),
            )
            skills[skill.id] = skill
            sources[skill.id] = file_path
        return cls(skills=skills, sources=sources)

    def list_skills(self) -> list[Skill]:
        return [self.skills[key] for key in sorted(self.skills)]

    def retrieve(self, query: str, top_k: int = 3) -> list[SkillMatch]:
        query_terms = tokenize(query)
        matches: list[SkillMatch] = []
        for skill in self.skills.values():
            name_terms = tokenize(skill.name)
            description_terms = tokenize(skill.description)
            tag_terms = tokenize(" ".join(skill.tags))
            example_terms = tokenize(" ".join(skill.examples))
            matched = sorted(
                query_terms.intersection(name_terms | description_terms | example_terms | tag_terms)
            )
            score = 0.0
            score += 4.0 * len(query_terms.intersection(name_terms))
            score += 2.0 * len(query_terms.intersection(tag_terms))
            score += 1.5 * len(query_terms.intersection(description_terms))
            score += 1.0 * len(query_terms.intersection(example_terms))
            if query and query.lower() in skill.description.lower():
                score += 3.0
            if score > 0:
                matches.append(SkillMatch(skill=skill, score=score, matched_terms=matched))
        matches.sort(key=lambda item: (-item.score, item.skill.name))
        return matches[:top_k]

    def build_prompt_bundle(self, matches: list[SkillMatch]) -> str:
        lines = ["Atlas Evolution skill context:"]
        if not matches:
            lines.append("- No matching local skills were found.")
            return "\n".join(lines)
        for match in matches:
            skill = match.skill
            lines.append(f"- {skill.name} ({skill.id})")
            lines.append(f"  Description: {skill.description}")
            if skill.tags:
                lines.append(f"  Tags: {', '.join(skill.tags)}")
            if skill.instructions:
                lines.append(f"  Instructions: {'; '.join(skill.instructions)}")
        return "\n".join(lines)

    def preview_prompt_changes(self, target_id: str, changes: dict[str, object]) -> dict[str, Any]:
        if target_id not in self.skills:
            raise KeyError(f"Unknown skill: {target_id}")
        skill = self.skills[target_id]
        path = self.sources[target_id]
        updated_skill, operation_summary = self._materialize_prompt_changes(skill, changes)
        current_text = json.dumps(skill.to_dict(), indent=2) + "\n"
        proposed_text = json.dumps(updated_skill.to_dict(), indent=2) + "\n"
        diff = "\n".join(
            unified_diff(
                current_text.splitlines(),
                proposed_text.splitlines(),
                fromfile=str(path),
                tofile=f"{path} (proposed)",
                lineterm="",
            )
        )
        return {
            "target_id": target_id,
            "target_path": str(path),
            "current": skill.to_dict(),
            "proposed": updated_skill.to_dict(),
            "operation_summary": operation_summary,
            "diff": diff + ("\n" if diff else ""),
        }

    def apply_prompt_changes(self, target_id: str, changes: dict[str, object]) -> Path:
        if target_id not in self.skills:
            raise KeyError(f"Unknown skill: {target_id}")
        updated_skill, _operation_summary = self._materialize_prompt_changes(self.skills[target_id], changes)
        self.skills[target_id] = updated_skill
        path = self.sources[target_id]
        path.write_text(json.dumps(updated_skill.to_dict(), indent=2) + "\n", encoding="utf-8")
        return path

    @staticmethod
    def _materialize_prompt_changes(skill: Skill, changes: dict[str, object]) -> tuple[Skill, list[str]]:
        updated_skill = Skill(
            id=skill.id,
            name=skill.name,
            description=skill.description,
            tags=list(skill.tags),
            examples=list(skill.examples),
            instructions=list(skill.instructions),
            metadata=dict(skill.metadata),
        )
        operation_summary: list[str] = []
        added_tags: list[str] = []
        for tag in [str(item) for item in changes.get("add_tags", [])]:
            if tag in updated_skill.tags:
                continue
            updated_skill.tags.append(tag)
            added_tags.append(tag)
        if added_tags:
            operation_summary.append("Add tags: " + ", ".join(added_tags))
        description_append = str(changes.get("description_append", "")).strip()
        if description_append and description_append not in updated_skill.description:
            updated_skill.description = f"{updated_skill.description} {description_append}".strip()
            operation_summary.append(f"Append description text: {description_append}")
        if not operation_summary:
            operation_summary.append("No material prompt metadata changes would be applied.")
        return updated_skill, operation_summary
