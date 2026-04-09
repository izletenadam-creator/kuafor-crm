#!/bin/bash
# Kuaför CRM — Kurulum Scripti
set -e

echo "======================================"
echo " Kuaför CRM — Kurulum"
echo "======================================"

# 1. Python bağımlılıkları
echo ""
echo "📦 Python bağımlılıkları kuruluyor..."
pip install -r requirements.txt -q
echo "   ✅ httpx, python-dotenv kuruldu"

# 2. .env dosyası
if [ ! -f .env ]; then
    cp .env.example .env
    echo ""
    echo "📝 .env dosyası oluşturuldu."
    echo "   ⚠️  Lütfen .env dosyasını düzenleyin:"
    echo "   nano .env"
else
    echo ""
    echo "✅ .env dosyası zaten mevcut"
fi

# 3. Ollama kontrolü
echo ""
echo "🤖 Ollama kontrol ediliyor..."
if command -v ollama &>/dev/null; then
    echo "   ✅ Ollama kurulu"
    if ollama list 2>/dev/null | grep -q "mistral"; then
        echo "   ✅ mistral:7b modeli mevcut"
    else
        echo "   ⬇️  mistral:7b indiriliyor (4GB)..."
        ollama pull mistral:7b
        echo "   ✅ mistral:7b hazır"
    fi
else
    echo "   ⚠️  Ollama kurulu değil!"
    echo "   Kurulum: https://ollama.com"
    echo "   Sonra: ollama pull mistral:7b"
fi

# 4. Leads klasörü
mkdir -p leads
echo ""
echo "✅ leads/ klasörü hazır"

# 5. Özet
echo ""
echo "======================================"
echo " Kurulum tamamlandı!"
echo "======================================"
echo ""
echo "Kullanım:"
echo "  python3 lead-hunter.py 'kuaför' 'istanbul'"
echo "  python3 world-scanner.py scan 'kuaför' 'TR'"
echo "  python3 world-scanner.py status"
echo ""
echo "WAHA (WhatsApp) için Docker gerekli:"
echo "  docker run -d -p 3000:3000 devlikeapro/waha"
echo ""
