#!/bin/bash
# ══════════════════════════════════════════════════
# News Bot — Oracle Cloud Setup
# Run from inside the news-bot folder
# ══════════════════════════════════════════════════

echo "🚀 Setting up News Bot on Oracle Cloud..."

cd "$(dirname "$0")"
BOT_DIR="$(pwd)"

# 1. Create virtual environment
python3 -m venv venv
source venv/bin/activate

# 2. Install dependencies
pip install --upgrade pip
pip install -r requirements.txt

# 3. Create .env file
if [ ! -f .env ]; then
    cp .env.example .env
    echo "📝 Fill in your keys: nano .env"
fi

# 4. Create systemd service
sudo tee /etc/systemd/system/news-bot.service > /dev/null << EOF
[Unit]
Description=Trading News Bot
After=network.target

[Service]
Type=simple
User=$(whoami)
WorkingDirectory=$BOT_DIR
EnvironmentFile=$BOT_DIR/.env
ExecStart=$BOT_DIR/venv/bin/python main.py
Restart=always
RestartSec=30

[Install]
WantedBy=multi-user.target
EOF

echo ""
echo "═══════════════════════════════════════"
echo "✅ News Bot setup complete!"
echo "═══════════════════════════════════════"
echo ""
echo "Step 1 — Fill in keys:  nano .env"
echo "Step 2 — Test:          source venv/bin/activate && python main.py"
echo "Step 3 — Start forever:"
echo "   sudo systemctl enable news-bot"
echo "   sudo systemctl start news-bot"
echo ""
echo "Commands:"
echo "   sudo systemctl status news-bot"
echo "   sudo systemctl restart news-bot"
echo "   journalctl -u news-bot -f"
echo "═══════════════════════════════════════"
