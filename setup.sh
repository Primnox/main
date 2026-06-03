#!/bin/bash
echo "=============================================="
echo "Primnox Auto-Setup Script"
echo "=============================================="

if ! command -v python3 &> /dev/null; then
    echo "[!] Python 3 is required but not installed. Please install Python 3.10+"
    exit 1
fi

if ! command -v node &> /dev/null; then
    echo "[!] Node.js is required but not installed. Please install Node.js 18+"
    exit 1
fi

echo "[*] Setting up Backend Environment..."
cd backend || exit
echo "[*] Creating virtual environment..."
python3 -m venv venv
source venv/bin/activate
echo "[*] Installing python dependencies..."
pip install --upgrade pip
pip install -r requirements.txt
cd ..

echo ""
echo "[*] Setting up Frontend Environment..."
cd frontend || exit
echo "[*] Installing Node modules..."
npm install
cd ..

echo ""
echo "=============================================="
echo "[+] Setup Complete!"
echo "=============================================="
echo "You can now use ./start.sh to launch Primnox."
