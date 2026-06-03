# Primnox 🌌

Primnox is a high-performance, modular desktop intelligence application designed to seamlessly bridge state-of-the-art open-source LLMs with real-world OS interactions. Running on an Electron React frontend and a Python FastAPI backend, it provides ultra-low latency inference, secure local state management, and direct integration with Groq.

**Current Version:** `0.0.2-alpha`

## Architecture
- **Frontend**: React 18, Vite, TailwindCSS, Zustand, Electron.
- **Backend**: Python 3.11, FastAPI, SQLite, PyInstaller (standalone executable).
- **Inference**: High-speed Groq API Fallback Chain (`gpt-oss-120b` -> `llama-3.3-70b-versatile` -> `qwen3-32b`, etc.).
- **Build Pipeline**: Obfuscated React compiler (`terser`), stripped source maps, and PyInstaller bundled assets wrapped in a secure `NSIS` ASAR bundle.

## Security & Deployment
- The backend is packaged into a secure binary utilizing the `NSIS` builder to ensure no raw source files are exposed.
- Source maps are aggressively stripped via the `prebuild` npm hook.
- User-supplied API keys (like the Groq API key) are intercepted during installation via custom `NSIS` scripting and securely written to `%APPDATA%\Primnox\.env` rather than being hardcoded.

## Development Setup
### Prerequisites
- Node.js & npm
- Python 3.11

### Running Locally
```bash
# 1. Install frontend dependencies
cd frontend
npm install

# 2. Run the development suite
npm run electron:dev
```

### Production Build
```bash
# Compile and generate the NSIS Installer (.exe)
cd frontend
npm run electron:build:full
```
The final installer will be located in `frontend/dist-electron/`.

---

## 🚀 Roadmap & Future Enhancements
*The "Future Thingys"*

1. **System-wide Auto-Updater**: Integrate `electron-updater` directly with GitHub Releases for silent background patching and hot-reloads.
2. **Local Vector Database (RAG)**: Replace basic memory strings with a lightweight local ChromaDB or FAISS instance for semantic search across thousands of offline notes.
3. **Advanced Screen Intelligence**: Expand the existing clipboard and UIA monitoring to support real-time OCR and visual understanding of the user's desktop state.
4. **Enhanced Encryption**: Transition Python state bundles to Cythonized `.pyd` or Pyarmor deployments to provide robust, enterprise-grade logic obfuscation.
5. **Plugin Marketplace**: Finalize the dynamically-loaded python `skills/` architecture to allow 3rd party developers to easily drop in modular workflow automations.
6. **Cross-Platform Compilation**: Port the Pyinstaller and NSIS build workflows over to `.dmg` and `.AppImage` to fully support macOS and Linux environments.
