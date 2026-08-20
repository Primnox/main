"""PyInstaller's entry point — NOT the dev entry point (that's run.py).

run.py hands uvicorn the string "primnox2.app:app" and lets it import the
module itself at runtime. PyInstaller builds its bundle by statically
analyzing whichever script it is pointed at, and a bare string is invisible
to that analysis: primnox2_backend.spec targeting run.py directly would
produce a frozen exe containing uvicorn and nothing of primnox2 at all,
failing the instant uvicorn tried to resolve the string against an empty
bundle. Importing the app object directly here makes the whole package graph
part of THIS script's own imports, which is what static analysis can see —
and passing the object instead of the string to uvicorn.run() is otherwise
behaviourally identical (it only changes how `--reload` re-imports on a file
change, and this build never sets reload=True).
"""
import uvicorn

from primnox2.app import app

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=4109, log_level="info")
