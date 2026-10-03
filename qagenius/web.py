from fastapi import FastAPI

app = FastAPI(title="QA-Genius v2")


@app.get("/health")
def health() -> str:
    return "ok"
