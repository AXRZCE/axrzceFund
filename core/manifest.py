"""Deployment manifest — the version-pinning layer (WP2).

configuration.md §3 fixes family/tier by ROLE (the decorrelation design: different model
families so adversaries/judges aren't one model checking itself). This manifest pins the
exact `model_version` per role and each model's TRAINING-DATA cutoff. It carries its own hash
(`manifest_version`), stamped per call alongside `model_version` into the ReplayTuple
(core/replay.py), so a model swap is auditable in the replay identity.

R1 / backtesting-framework.md §6 C1: the post-cutoff fixture gate guards against MEMORIZATION,
so `cutoff` is the **training-data cutoff** (the broader range), not the narrower "reliable
knowledge cutoff". The binding cutoff for a fixture is the MAX cutoff across every model that
will read it.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Iterable

import yaml

DEFAULT_MANIFEST = Path("deploy/model_manifest.yaml")
_REQUIRED = ("family", "tier", "model_version", "cutoff")


class ManifestError(Exception):
    """Malformed/incomplete manifest. Fail-closed — an unpinned model or cutoff must never
    silently pass R1, so loading raises rather than defaulting."""


@dataclass(frozen=True)
class ModelSpec:
    role: str
    family: str
    tier: str
    model_version: str   # OpenRouter slug, e.g. "anthropic/claude-sonnet-4.6"
    cutoff: str          # training-data cutoff, ISO date (YYYY-MM-DD), end-of-month conservative

    @property
    def cutoff_date(self) -> date:
        return date.fromisoformat(self.cutoff)


@dataclass(frozen=True)
class Manifest:
    manifest_version: str          # sha256[:12] of the raw file bytes
    access: str
    specs: dict[str, ModelSpec]

    def resolve(self, role: str) -> ModelSpec:
        try:
            return self.specs[role]
        except KeyError:
            raise ManifestError(
                f"role {role!r} not in manifest (have: {sorted(self.specs)})"
            ) from None

    def binding_cutoff(self, roles: Iterable[str]) -> date:
        """R1: binding training-data cutoff for a fixture = MAX cutoff across the models that
        will read it. A fixture must be dated strictly AFTER this date to be usable."""
        roles = list(roles)
        if not roles:
            raise ManifestError("binding_cutoff requires at least one role")
        return max(self.resolve(r).cutoff_date for r in roles)


def load_manifest(path: Path = DEFAULT_MANIFEST) -> Manifest:
    """Load and hash the deployment manifest. Fail-closed on any missing required field or
    unparseable cutoff."""
    path = Path(path)
    if not path.exists():
        raise ManifestError(f"deployment manifest not found: {path}")

    raw = path.read_bytes()
    manifest_version = hashlib.sha256(raw).hexdigest()[:12]
    doc = yaml.safe_load(raw) or {}
    roles = doc.get("roles") or {}
    if not roles:
        raise ManifestError(f"manifest {path} has no roles")

    specs: dict[str, ModelSpec] = {}
    for role, d in roles.items():
        d = d or {}
        for field in _REQUIRED:
            if not d.get(field):
                raise ManifestError(
                    f"role {role!r}: missing required field {field!r} "
                    f"(fail-closed — an unpinned model/cutoff must never silently pass R1)"
                )
        cutoff = str(d["cutoff"])
        try:
            date.fromisoformat(cutoff)
        except ValueError:
            raise ManifestError(
                f"role {role!r}: cutoff {cutoff!r} is not an ISO date (YYYY-MM-DD)"
            ) from None
        specs[role] = ModelSpec(
            role=role,
            family=str(d["family"]),
            tier=str(d["tier"]),
            model_version=str(d["model_version"]),
            cutoff=cutoff,
        )

    return Manifest(
        manifest_version=manifest_version,
        access=str(doc.get("access", "openrouter")),
        specs=specs,
    )


if __name__ == "__main__":
    m = load_manifest()
    print(f"manifest_version: {m.manifest_version}  access: {m.access}")
    for role, spec in m.specs.items():
        print(f"  {role:10} {spec.tier:5} {spec.family:10} {spec.model_version:30} cutoff={spec.cutoff}")
    print(f"binding cutoff (all roles): {m.binding_cutoff(list(m.specs))}")
