"""Reviewed upstream identities shared by adapters and installation checks.

These are integration requirements, not a claim about the local installation
or the live availability of an upstream service.  Python requirements describe
the environments supported by XTI's installers.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ReviewedComponentPin:
    identifier: str
    label: str
    distribution: str
    package: str
    version: str | None
    repository: str
    commit: str
    integration_profile: str
    catalog_size: int | None
    catalog_sha256: str | None
    license_spdx: str
    license_reference_url: str
    python_requirement: str
    deployment: str
    setup_command: tuple[str, ...]
    verify_command: tuple[str, ...]


MAIGRET_PIN = ReviewedComponentPin(
    identifier="maigret",
    label="Maigret",
    distribution="maigret",
    package="maigret",
    version="0.6.6",
    repository="https://github.com/soxoj/maigret.git",
    commit="b8747b98820f4df9d1baf23235db7b2cb55d0198",
    integration_profile="maigret-0.6.6-b8747b98820f-safe-v1",
    catalog_size=3_329_634,
    catalog_sha256="8dd404e6b3012f01fd467c154b5159386d1362587070c661c2565ec8fa649899",
    license_spdx="MIT",
    license_reference_url=(
        "https://github.com/soxoj/maigret/blob/"
        "b8747b98820f4df9d1baf23235db7b2cb55d0198/LICENSE"
    ),
    python_requirement=">=3.11",
    deployment="project-venv",
    setup_command=("./scripts/setup-brand",),
    verify_command=("./scripts/setup-brand", "--check"),
)

SHERLOCK_PIN = ReviewedComponentPin(
    identifier="sherlock",
    label="Sherlock",
    distribution="sherlock-project",
    package="sherlock_project",
    version="0.16.2",
    repository="https://github.com/sherlock-project/sherlock.git",
    commit="a38ba54fda799cd786a2ab67a50143e1a63169e6",
    integration_profile="sherlock-0.16.2-a38ba54fda79-safe-v1",
    catalog_size=104_039,
    catalog_sha256="3fdfc6694c5cd99798881215554b09e617c6d5284a6219fae309882566a9fb30",
    license_spdx="MIT",
    license_reference_url=(
        "https://github.com/sherlock-project/sherlock/blob/"
        "a38ba54fda799cd786a2ab67a50143e1a63169e6/LICENSE"
    ),
    python_requirement=">=3.11",
    deployment="project-venv",
    setup_command=("./scripts/setup-brand",),
    verify_command=("./scripts/setup-brand", "--check"),
)

HARVESTER_PIN = ReviewedComponentPin(
    identifier="theharvester",
    label="theHarvester",
    distribution="theHarvester",
    package="theHarvester",
    version=None,
    repository="https://github.com/laramies/theHarvester.git",
    commit="6790b147f52309e4eee22ed941db1d285ab2ec23",
    integration_profile="theharvester-6790b147f523-p0-archives-v3",
    catalog_size=None,
    catalog_sha256=None,
    license_spdx="GPL-2.0-only",
    license_reference_url=(
        "https://github.com/laramies/theHarvester/blob/"
        "6790b147f52309e4eee22ed941db1d285ab2ec23/LICENSE"
    ),
    python_requirement=">=3.14",
    deployment="isolated-tool-venv",
    setup_command=("./scripts/setup-harvester",),
    verify_command=(),
)

REVIEWED_COMPONENT_PINS = (MAIGRET_PIN, SHERLOCK_PIN, HARVESTER_PIN)


def component_pin(identifier: str) -> ReviewedComponentPin:
    for pin in REVIEWED_COMPONENT_PINS:
        if pin.identifier == identifier:
            return pin
    raise ValueError("Unknown reviewed component")
