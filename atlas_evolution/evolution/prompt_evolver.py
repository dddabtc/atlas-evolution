from __future__ import annotations

from collections import Counter, defaultdict

from atlas_evolution.models import EvolutionProposal, FeedbackRecord, Skill
from atlas_evolution.skill_bank import tokenize

STOPWORDS = {
    "a",
    "an",
    "and",
    "for",
    "from",
    "how",
    "i",
    "in",
    "of",
    "on",
    "or",
    "the",
    "to",
    "with",
}


class PromptEvolver:
    """Heuristic skill-description updater for v1."""

    def propose(
        self,
        feedback: list[FeedbackRecord],
        skills: dict[str, Skill],
        min_evidence: int,
    ) -> list[EvolutionProposal]:
        failure_terms: dict[str, Counter[str]] = defaultdict(Counter)
        evidence_counts: Counter[str] = Counter()
        for record in feedback:
            if record.score >= 0.6 or not record.selected_skill_ids:
                continue
            tokens = tokenize(record.task)
            tokens.update(tokenize(record.comment or ""))
            tokens = {token for token in tokens if token not in STOPWORDS and len(token) > 2}
            for skill_id in record.selected_skill_ids:
                skill = skills.get(skill_id)
                if skill is None:
                    continue
                existing = tokenize(skill.name) | tokenize(skill.description) | set(skill.tags)
                novel_terms = tokens.difference({item.lower() for item in existing})
                failure_terms[skill_id].update(novel_terms)
                evidence_counts[skill_id] += 1
        proposals: list[EvolutionProposal] = []
        for skill_id, counts in failure_terms.items():
            if evidence_counts[skill_id] < min_evidence or not counts:
                continue
            ranked_terms = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
            top_terms = [term for term, _count in ranked_terms[:3]]
            if not top_terms:
                continue
            confidence = min(0.95, 0.45 + 0.1 * evidence_counts[skill_id] + 0.05 * len(top_terms))
            summary = (
                f"Extend {skill_id} with observed failure terms: {', '.join(top_terms)}."
            )
            proposals.append(
                EvolutionProposal(
                    proposal_id=f"prompt-{skill_id}",
                    proposal_type="prompt_update",
                    title=f"Refine skill metadata for {skill_id}",
                    summary=summary,
                    rationale=(
                        "The same skill was selected for low-scoring sessions whose task language "
                        "included uncovered terms."
                    ),
                    target_id=skill_id,
                    evidence_count=evidence_counts[skill_id],
                    confidence=confidence,
                    changes={
                        "add_tags": top_terms,
                        "description_append": (
                            "Also handle requests involving "
                            + ", ".join(top_terms)
                            + "."
                        ),
                    },
                )
            )
        return proposals
