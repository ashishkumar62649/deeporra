from fastapi import FastAPI

from .helpers import DEFAULT_GREETING, fetch_profile, normalize_name

app = FastAPI()


class GreetingService:
    def greet(self, name: str) -> str:
        return f"{DEFAULT_GREETING}, {normalize_name(name)}"

    def _audit(self, user_id: str) -> str:
        return f"audit:{user_id}"


@app.get("/profiles/{user_id}")
async def get_profile(user_id: str) -> dict[str, str]:
    return await fetch_profile(user_id)


@app.post("/profiles")
def create_profile(name: str) -> dict[str, str]:
    return {"name": normalize_name(name)}
