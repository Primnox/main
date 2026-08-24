"""Entry point pinned to the local echo provider.

Same runtime, no network and no key. Useful for two things: demonstrating the
full turn lifecycle on a machine whose configured provider is down, and
separating "the runtime is broken" from "the provider is broken" — which is
otherwise the hardest question to answer quickly.
"""
import os

os.environ["PRIMNOX_PROVIDER"] = "echo"

import uvicorn

if __name__ == "__main__":
    uvicorn.run("primnox2.app:app", host="127.0.0.1", port=4109, reload=False, log_level="info")
