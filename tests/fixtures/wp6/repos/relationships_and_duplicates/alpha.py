from fastapi import FastAPI

app = FastAPI()


def duplicate() -> str:
    return "alpha"


class AlphaService:
    def process(self) -> str:
        return duplicate()


@app.get("/shared")
def get_shared() -> str:
    return duplicate()
