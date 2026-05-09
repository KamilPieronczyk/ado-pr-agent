from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ChangedFile:
    status: str
    path: str


def parse_changed_files(name_status: str) -> list[ChangedFile]:
    files: list[ChangedFile] = []
    for line in name_status.splitlines():
        if not line:
            continue

        parts = line.split("\t")
        if len(parts) < 2:
            continue

        files.append(ChangedFile(status=parts[0], path=parts[-1]))

    return files
