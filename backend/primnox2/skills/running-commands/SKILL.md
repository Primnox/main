---
name: running-commands
description: running code or a command, and what the sandbox cannot reach
triggers: run the tests, pytest, git status, git log, git diff, in my repo, my project folder, command line, shell command, terminal, npm, node script, install the package, powershell, bash
---

Three runtimes, in the order you should reach for them:

    run_python   the default. Isolated, offline, approved once per turn.
    run_node     plain JavaScript. Same isolation. No packages, no npm.
    run_shell    cmd.exe. Asked of the user EVERY time, never reused.

Prefer `run_python`. It does almost everything a shell would, and its approval
carries across the turn instead of interrupting the user again for each step.

## Where the command actually runs

In a fresh, empty directory created for that one execution. Not your repo, not
their repo, not their Documents, not their desktop. Nothing from the user's
machine is in it, and nothing you write there persists unless it becomes a file
the app registers.

It has no network. Downloads fail, `pip install` fails, `npm install` fails,
`git clone` fails. A `git status` runs in an empty folder and tells you about
nothing.

So when the user asks you to run their tests, check their repo, or look at a
file on their disk: **you cannot, and saying you did is the worst available
outcome.** Say what the sandbox reaches, and ask them to paste the file or
upload it — an uploaded file is readable with `search_assets` and `read_asset`.

What does work is anything self-contained: write the code and the input into
the execution directory, run it there, read the output.

    import subprocess, textwrap, pathlib
    pathlib.Path('t.py').write_text(textwrap.dedent('''
        def slug(s): return "-".join(s.lower().split())
        assert slug("Hello There") == "hello-there"
        print("ok")
    '''))
    print(subprocess.run(['python', 't.py'], capture_output=True, text=True).stdout)

Files a run leaves behind become assets the user can open, so writing the result
to a file is how you hand something over.

## When you do use run_shell

It is `cmd.exe`, so `ls`, `grep`, `cat` and `&&`-heavy POSIX lines are the wrong
syntax — `dir`, `findstr`, `type`. It carries the highest danger rating and the
user is asked to approve it on *every single call*, with no reuse. Ten small
commands is ten interruptions. Put the whole job in one command, or better,
write it as Python.

## Reading the result honestly

An execution that exits 0 with no output is the most dangerous result you can
get: it reads as success, and the silence gets filled in with a plausible
number. Measured on a 7B — `result = 137 * 449` on the last line printed
nothing, and the reply reported 61,013 for a value that is 61,513.

`print()` what you want to see. If the output came back empty, run it again
with the print rather than reporting a result you never saw. If it failed, the
error text is the answer — quote it, do not paraphrase it into a guess.

Executions stop at 300 seconds. A long loop that gets killed has produced
nothing, however far it got.
