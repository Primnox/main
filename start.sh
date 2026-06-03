#!/bin/bash
echo "=============================================="
echo "Launching Primnox..."
echo "=============================================="

if [ ! -f "backend/venv/bin/activate" ]; then
    echo "[!] Virtual environment not found. Please run ./setup.sh first!"
    exit 1
fi

echo "[*] Starting Backend Server..."
cd backend || exit
source venv/bin/activate
python server.py &
BACKEND_PID=$!
cd ..

echo "[*] Starting Frontend UI..."
cd frontend || exit
npm run electron:dev &
FRONTEND_PID=$!
cd ..

echo ""
echo "[+] Services are running in the background."
echo "Press Ctrl+C to stop all services."

trap "echo '[*] Stopping services...'; kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit" SIGINT SIGTERM
wait
