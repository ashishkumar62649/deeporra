from pathlib import Path

Path("TRIPWIRE_EXECUTED").write_text("executed", encoding="utf-8")
raise RuntimeError("TRIPWIRE_TARGET_WAS_IMPORTED")


def static_only() -> str:
    return "analyze without execution"
