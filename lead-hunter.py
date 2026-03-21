"""
Lead Hunter — Herhangi bir sektör + şehir için Google Maps'ten lead topla
Kullanım: python3 lead-hunter.py "diş doktoru" "istanbul"
         python3 lead-hunter.py "veteriner" "ankara"
         python3 lead-hunter.py "kuaför" "antalya"
"""

import sys
import json
import os
import re
import asyncio
import httpx
from datetime import datetime

AISA_KEY = os.getenv("AISA_API_KEY", "os.getenv("AISA_API_KEY", "")")
AISA_URL = "https://api.aisa.one/v1/chat/completions"
CRM_DIR = "/home/sagcan/.openclaw/workspace/salon-crm"
GIT_TOKEN = "os.getenv("GIT_TOKEN", "")"

# Sektör bazlı sorun tespiti ve pitch
SECTOR_CONFIG = {
    "kuaför": {
        "search_terms": ["kuaför", "güzellik salonu", "bayan kuaför", "hair salon"],
        "crm_folder": "kuaforler",
        "pain_points": [
            "Randevu karışıklığı — müşteri geldi ama sıra yok",
            "Telefona yetişememe — meşgulken kaçan müşteriler",
            "Müşteri takibi yok — kim geldi, ne yaptırdı, bilmiyorsun",
            "Kampanya yapamama — indirim var ama müşteriye ulaşamıyorsun",
        ],
        "solution": "Randevu otomasyonu, müşteri hafızası, kampanya yönetimi, 7/24 WhatsApp cevaplama",
    },
    "diş": {
        "search_terms": ["diş kliniği", "diş doktoru", "dental klinik", "ağız diş sağlığı"],
        "crm_folder": "dis-klinikleri",
        "pain_points": [
            "Randevu iptalleri — hasta gelmiyor, slot boş kalıyor",
            "Hatırlatma sistemi yok — hastalar randevuyu unutuyor",
            "Telefon yoğunluğu — asistan telefona yetişemiyor",
            "Hasta takibi — tedavi planı takibi yapılamıyor",
        ],
        "solution": "Otomatik randevu hatırlatma, hasta takip sistemi, tedavi planı yönetimi, 7/24 WhatsApp asistan",
    },
    "veteriner": {
        "search_terms": ["veteriner", "veteriner kliniği", "pet klinik"],
        "crm_folder": "veterinerler",
        "pain_points": [
            "Aşı takibi — hayvanların aşı takvimi kaçırılıyor",
            "Randevu yönetimi — acil vakalarda karışıklık",
            "Müşteri iletişimi — sonuç bildirimi telefona bağımlı",
            "Tekrar ziyaret hatırlatması — kontrol randevuları kaçıyor",
        ],
        "solution": "Aşı takvimi otomasyonu, randevu yönetimi, otomatik hatırlatma, hasta dosyası dijitalleştirme",
    },
    "emlak": {
        "search_terms": ["emlakçı", "emlak ofisi", "gayrimenkul"],
        "crm_folder": "emlakcilar",
        "pain_points": [
            "Müşteri kaybı — arayan kişiye hemen dönüş yapılamıyor",
            "İlan yönetimi — portföydeki ilanları takip edememe",
            "Lead takibi — kim aradı, neyle ilgilendi, unutuluyor",
            "7/24 erişilebilirlik — mesai dışı gelen talepler kaçıyor",
        ],
        "solution": "Otomatik müşteri cevaplama, portföy yönetimi, lead takip sistemi, 7/24 WhatsApp asistan",
    },
    "restoran": {
        "search_terms": ["restoran", "restaurant", "lokanta", "cafe"],
        "crm_folder": "restoranlar",
        "pain_points": [
            "Rezervasyon karışıklığı — telefonla takip edilemiyor",
            "Müşteri geri bildirimi — şikayet hemen çözülemiyor",
            "Menü güncellemesi — yeni menüyü duyurmak zor",
            "Sadakat programı yok — tekrar gelen müşteriyi ödüllendirememe",
        ],
        "solution": "Otomatik rezervasyon sistemi, müşteri geri bildirim yönetimi, dijital menü, sadakat programı",
    },
    "oto": {
        "search_terms": ["oto servis", "oto yıkama", "araç servis", "oto tamir"],
        "crm_folder": "oto-servisler",
        "pain_points": [
            "Bakım hatırlatması — müşteriler periyodik bakımı unutuyor",
            "Randevu yönetimi — telefon trafiği çok yoğun",
            "Müşteri geçmişi — aracına ne yapıldı hatırlanmıyor",
            "Fiyat teklifi — telefonda uzun açıklama gerekiyor",
        ],
        "solution": "Periyodik bakım hatırlatma, otomatik randevu, araç geçmişi takibi, WhatsApp fiyat teklifi",
    },
}


def get_sector(keyword: str) -> dict:
    """Anahtar kelimeye göre sektör config'i döndür"""
    keyword = keyword.lower()
    for key, config in SECTOR_CONFIG.items():
        if key in keyword or any(t in keyword for t in config["search_terms"]):
            return {**config, "key": key}
    # Bilinmeyen sektör — genel config
    return {
        "key": keyword.replace(" ", "-"),
        "search_terms": [keyword],
        "crm_folder": keyword.replace(" ", "-"),
        "pain_points": [
            "Müşteri iletişimi — telefonla takip edilemiyor",
            "Randevu/sipariş yönetimi karışıklığı",
            "7/24 erişilebilirlik sorunu",
            "Müşteri takip sistemi yok",
        ],
        "solution": "Otomatik müşteri cevaplama, randevu yönetimi, hatırlatma sistemi, 7/24 WhatsApp asistan",
    }


async def generate_sector_pitch(lead: dict, sector: dict, issues: list) -> str:
    """Sektöre özel kişiselleştirilmiş mesaj üret"""
    prompt = f"""Bir dijital pazarlama uzmanısın. Bir işletmeye WhatsApp mesajı yazacaksın.

İŞLETME:
- İsim: {lead['name']}
- Sektör: {sector['key']}
- Adres: {lead.get('address', '?')}
- Rating: {lead.get('rating', '?')} ({lead.get('reviews', '?')} yorum)

SEKTÖREL SORUNLAR:
{chr(10).join(f"- {p}" for p in sector['pain_points'][:2])}

DİJİTAL EKSİKLER:
{chr(10).join(f"- {i}" for i in issues[:2])}

ÇÖZÜM: {sector['solution']}

Sen FATIH'sin (FS Roket Teknoloji kurucusu). Samimi, profesyonel, kısa (3-4 cümle).
"Bot", "AI", "Ela" kelimelerini KULLANMA. "Dijital sistem", "otomasyon" de.
İlk ay ücretsiz demo teklif et. Baskı yapma.
WhatsApp formatı kullan (*bold*).

Sadece mesajı yaz."""

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                AISA_URL,
                json={"model": "gpt-4o-mini", "messages": [{"role": "user", "content": prompt}], "temperature": 0.7, "max_tokens": 250},
                headers={"Authorization": f"Bearer {AISA_KEY}", "Content-Type": "application/json"},
            )
            return resp.json()["choices"][0]["message"]["content"]
    except Exception as e:
        return f"Merhaba {lead['name']}! İşletmeniz için geliştirdiğimiz dijital yönetim sistemini göstermek isteriz. İlk ay tamamen ücretsiz. Demo için yazabilirsiniz 🙌 — Fatih, FS Roket Teknoloji"


def create_crm_file(lead: dict, sector: dict, pitch: str, issues: list):
    """CRM dosyası oluştur"""
    name = lead["name"]
    slug = re.sub(r'[^a-z0-9]+', '-', name.lower()
        .replace('ö','o').replace('ü','u').replace('ş','s')
        .replace('ç','c').replace('ı','i').replace('ğ','g')
        .replace('İ','i').replace('Ö','O').replace('Ü','U')
    ).strip('-')
    
    folder = f"{CRM_DIR}/leads/{lead.get('city','genel')}/{sector['crm_folder']}"
    os.makedirs(folder, exist_ok=True)
    
    content = f"""# {name}
**Durum:** ⬜ Hazır (mesaj gönderilmedi)
**Sektör:** {sector['key']}
**Şehir:** {lead.get('city', '?')}
**Tarih:** {datetime.now().strftime('%Y-%m-%d')}

## Bilgiler
| Alan | Değer |
|------|-------|
| Telefon | {lead.get('phone', '❌ Yok')} |
| Adres | {lead.get('address', '?')} |
| Rating | ⭐{lead.get('rating', '?')} ({lead.get('reviews', '?')} yorum) |
| Website | {lead.get('website', '❌ Yok')} |

## Sektörel Sorunlar
"""
    for p in sector['pain_points']:
        content += f"- {p}\n"
    
    content += f"""
## Dijital Analiz
"""
    for i in issues:
        content += f"- ❌ {i}\n"
    
    content += f"""
## Hazırlanan Mesaj
```
{pitch}
```

## Konuşma Geçmişi
| Tarih | Kimden | Mesaj |
|-------|--------|-------|

## Notlar
- Lead {datetime.now().strftime('%Y-%m-%d')} tarihinde Google Maps'ten toplandı
"""
    
    filepath = f"{folder}/{slug}.md"
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
    return filepath


def git_push(message: str):
    """CRM'i GitHub'a push et"""
    os.system(f'cd {CRM_DIR} && git add -A && git commit -m "{message}" --quiet 2>/dev/null')
    os.system(f'cd {CRM_DIR} && git push --quiet 2>/dev/null')


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Kullanım: python3 lead-hunter.py <sektör> <şehir>")
        print()
        print("Örnekler:")
        print('  python3 lead-hunter.py "kuaför" "istanbul"')
        print('  python3 lead-hunter.py "diş doktoru" "izmir"')
        print('  python3 lead-hunter.py "veteriner" "ankara"')
        print('  python3 lead-hunter.py "emlakçı" "antalya"')
        print('  python3 lead-hunter.py "restoran" "bursa"')
        print('  python3 lead-hunter.py "oto servis" "kocaeli"')
        print()
        print(f"Desteklenen sektörler: {', '.join(SECTOR_CONFIG.keys())}")
        sys.exit(0)
    
    sector_name = sys.argv[1]
    city = sys.argv[2]
    
    sector = get_sector(sector_name)
    print(f"🔍 Sektör: {sector['key']} | Şehir: {city}")
    print(f"📋 Arama terimleri: {sector['search_terms']}")
    print(f"🎯 CRM klasörü: leads/{city}/{sector['crm_folder']}/")
    print()
    print("⚠️  Google Maps scraping için browser tool gerekli.")
    print("    NICO'ya söyle: 'lead-hunter çalıştır, [sektör] [şehir]'")
    print(f"    Browser'da ara: https://www.google.com/maps/search/{sector['search_terms'][0]}+{city}")
