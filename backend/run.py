"""Entry point. Loopback-only, like V1 — nothing about V2 changes that."""
import uvicorn

if __name__ == "__main__":
    uvicorn.run("primnox2.app:app", host="127.0.0.1", port=4109, reload=False, log_level="info")
