DEFAULT_GREETING = "golden hello"


def normalize_name(name: str) -> str:
    return name.strip().title()


async def fetch_profile(user_id: str) -> dict[str, str]:
    return {"id": user_id, "name": "Golden User"}
