#!/bin/bash
# Vite dev server launcher for macOS.
# Node is installed under ~/.local/node (Homebrew could not be used: /opt/homebrew
# is not owned by the user and fixing it needs sudo). npm's shebang is
# `#!/usr/bin/env node`, so PATH must carry node before npm is invoked.
export PATH="$HOME/.local/node/bin:$PATH"
cd "$(dirname "$0")"
exec npm run dev -- --host 127.0.0.1 --port 5173
