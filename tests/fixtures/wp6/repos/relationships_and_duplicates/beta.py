from .alpha import duplicate
from fastapi import FastAPI

app = FastAPI()


def duplicate() -> str:
    return "beta"


class BetaService:
    def process(self) -> str:
        return duplicate()


@app.post("/shared")
def post_shared() -> str:
    return duplicate()
