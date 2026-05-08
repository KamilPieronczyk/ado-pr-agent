from pathlib import Path


def fixture_path(name: str) -> Path:
    return Path(__file__).parent / "fixtures" / name
