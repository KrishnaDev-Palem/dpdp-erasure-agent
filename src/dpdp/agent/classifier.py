"""Adversarial classifier seam — protocol and deterministic stub."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

Verdict = Literal["clean", "adversarial"]


@dataclass(frozen=True)
class ClassificationResult:
    verdict: Verdict
    detail: str | None = None


class Classifier(Protocol):
    def classify(self, requester_note: str | None) -> ClassificationResult: ...


@dataclass(frozen=True)
class StubClassifier:
    """Deterministic classifier for acceptance tests — no model client."""

    verdict: Verdict
    detail: str | None = None

    def classify(self, requester_note: str | None) -> ClassificationResult:
        return ClassificationResult(verdict=self.verdict, detail=self.detail)
