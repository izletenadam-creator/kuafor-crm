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
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/v1/chat/completions")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "mistral:7b")
GOOGLE_API_KEY = os.getenv("GOOGLE_PLACES_API_KEY", "")
CRM_DIR = Path(os.getenv("CRM_DIR", Path(__file__).parent))
GIT_TOKEN = os.getenv("GIT_TOKEN", "")

# Sektör bazlı sorun tespiti ve pitch
SECTOR_CONFIG = {
    "kuaför": {
        "search_terms": ["kuaför", "güzellik salonu", "bayan kuaför", "hair salon"],
        "osm_tag": "shop=hairdresser",
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
        "osm_tag": "amenity=dentist",
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
        "osm_tag": "amenity=veterinary",
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
        "osm_tag": "office=estate_agent",
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
        "osm_tag": "amenity=restaurant",
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
        "osm_tag": "shop=car_repair",
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
    keyword_lower = keyword.lower()
    for key, config in SECTOR_CONFIG.items():
        if key in keyword_lower or any(t in keyword_lower for t in config["search_terms"]):
            return {**config, "key": key}
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


async def search_google_places(query: str, city: str) -> list:
    """Google Places API ile lead ara"""
    if not GOOGLE_API_KEY:
        return []

    leads = []
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(
                "https://maps.googleapis.com/maps/api/place/textsearch/json",
                params={"query": f"{query} {city}", "key": GOOGLE_API_KEY, "language": "tr"},
            )
            data = resp.json()

            for place in data.get("results", [])[:20]:
                detail_resp = await client.get(
                    "https://maps.googleapis.com/maps/api/place/details/json",
                    params={
                        "place_id": place["place_id"],
                        "fields": "name,formatted_phone_number,international_phone_number,website,formatted_address,rating,user_ratings_total",
                        "key": GOOGLE_API_KEY,
                        "language": "tr",
                    },
                )
                detail = detail_resp.json().get("result", {})
                phone = detail.get("international_phone_number", "") or detail.get("formatted_phone_number", "")
                leads.append({
                    "name": detail.get("name", place.get("name", "")),
                    "phone": phone,
                    "address": detail.get("formatted_address", ""),
                    "website": detail.get("website", ""),
                    "rating": str(detail.get("rating", "")),
                    "reviews": str(detail.get("user_ratings_total", "")),
                    "city": city,
                })
                await asyncio.sleep(0.1)
    except Exception as e:
        print(f"❌ Google Places API hatası: {e}")

    return leads


async def search_overpass(osm_tag: str, city: str) -> list:
    """OpenStreetMap Overpass API ile ücretsiz lead ara — API key gerekmez"""
    key, value = osm_tag.split("=", 1)
    headers = {"User-Agent": "kuafor-crm/1.0 (lead-hunter)"}

    try:
        async with httpx.AsyncClient(timeout=20, headers=headers) as client:
            # Nominatim ile şehri geocode et → bounding box al
            geo = await client.get(
                "https://nominatim.openstreetmap.org/search",
                params={"q": city, "format": "json", "limit": 1, "countrycodes": "tr"},
            )
            geo_data = geo.json()
            if not geo_data:
                # Ülke kodu olmadan dene
                geo = await client.get(
                    "https://nominatim.openstreetmap.org/search",
                    params={"q": city, "format": "json", "limit": 1},
                )
                geo_data = geo.json()
            if not geo_data:
                print(f"   ❌ Şehir bulunamadı: {city}")
                return []

            south, north, west, east = geo_data[0]["boundingbox"]

            # Overpass QL sorgusu
            query = f"""[out:json][timeout:30];
(
  node["{key}"="{value}"]({south},{west},{north},{east});
  way["{key}"="{value}"]({south},{west},{north},{east});
);
out body 60;"""

            await asyncio.sleep(1)  # Nominatim rate limit
            ov = await client.post("https://overpass-api.de/api/interpreter", data=query)
            elements = ov.json().get("elements", [])

            leads = []
            for el in elements:
                tags = el.get("tags", {})
                name = tags.get("name") or tags.get("name:tr", "")
                if not name:
                    continue
                phone = tags.get("phone") or tags.get("contact:phone", "")
                website = tags.get("website") or tags.get("contact:website", "")
                street = tags.get("addr:street", "")
                housenumber = tags.get("addr:housenumber", "")
                address = f"{street} {housenumber}".strip() or city
                leads.append({
                    "name": name,
                    "phone": phone,
                    "website": website,
                    "address": address,
                    "city": city,
                    "source": "openstreetmap",
                })
            return leads
    except Exception as e:
        print(f"   ❌ Overpass API hatası: {e}")
        return []


async def generate_sector_pitch(lead: dict, sector: dict, issues: list) -> str:
    """Sektöre özel kişiselleştirilmiş mesaj üret (Ollama)"""
    prompt = f"""Bir dijital pazarlama uzmanısın. Bir işletmeye WhatsApp mesajı yazacaksın.

İŞLETME:
- İsim: {lead['name']}
- Sektör: {sector['key']}
- Adres: {lead.get('address', '?')}
- Rating: {lead.get('rating', '?')} ({lead.get('reviews', '?')} yorum)

SEKTÖREL SORUNLAR:
{chr(10).join(f"- {p}" for p in sector['pain_points'][:2])}

DİJİTAL EKSİKLER:
{chr(10).join(f"- {i}" for i in issues[:2]) if issues else "- Genel dijital eksiklik"}

ÇÖZÜM: {sector['solution']}

Sen FATIH'sin (FS Roket Teknoloji kurucusu). Samimi, profesyonel, kısa (3-4 cümle).
"Bot", "AI", "Ela" kelimelerini KULLANMA. "Dijital sistem", "otomasyon" de.
İlk ay ücretsiz demo teklif et. Baskı yapma.
WhatsApp formatı kullan (*bold*).

Sadece mesajı yaz."""

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                OLLAMA_URL,
                json={
                    "model": OLLAMA_MODEL,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.7,
                    "max_tokens": 250,
                },
                headers={"Content-Type": "application/json"},
            )
            return resp.json()["choices"][0]["message"]["content"].strip()
    except Exception:
        return (
            f"Merhaba *{lead['name']}*! İşletmeniz için geliştirdiğimiz dijital yönetim "
            f"sistemini göstermek isteriz. İlk ay tamamen ücretsiz. "
            f"Demo için yazabilirsiniz 🙌 — Fatih, FS Roket Teknoloji"
        )


def create_crm_file(lead: dict, sector: dict, pitch: str, issues: list) -> str:
    """CRM markdown dosyası oluştur"""
    name = lead["name"]
    slug = re.sub(
        r'[^a-z0-9]+', '-',
        name.lower()
        .replace('ö', 'o').replace('ü', 'u').replace('ş', 's')
        .replace('ç', 'c').replace('ı', 'i').replace('ğ', 'g')
        .replace('İ', 'i').replace('Ö', 'o').replace('Ü', 'u')
    ).strip('-')

    folder = CRM_DIR / "leads" / lead.get('city', 'genel') / sector['crm_folder']
    folder.mkdir(parents=True, exist_ok=True)

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

    content += "\n## Dijital Analiz\n"
    for i in issues:
        content += f"- ❌ {i}\n"
    if not issues:
        content += "- Analiz yapılmadı\n"

    content += f"""
## Hazırlanan Mesaj
```
{pitch}
```

## Konuşma Geçmişi
| Tarih | Kimden | Mesaj |
|-------|--------|-------|

## Notlar
- Lead {datetime.now().strftime('%Y-%m-%d')} tarihinde toplandı
"""

    filepath = folder / f"{slug}.md"
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
    return str(filepath)


def git_push(message: str):
    """Değişiklikleri GitHub'a push et"""
    os.system(f'cd "{CRM_DIR}" && git add -A && git commit -m "{message}" --quiet 2>/dev/null')
    os.system(f'cd "{CRM_DIR}" && git push --quiet 2>/dev/null')


async def run(sector_name: str, city: str):
    sector = get_sector(sector_name)
    print(f"🔍 Sektör: {sector['key']} | Şehir: {city}")

    leads = []

    # 1. Google Places API (varsa — en detaylı veri)
    if GOOGLE_API_KEY:
        print(f"🌐 Google Places API ile aranıyor...")
        leads = await search_google_places(sector['search_terms'][0], city)
        if leads:
            print(f"   ✅ Google Places: {len(leads)} işletme")

    # 2. OpenStreetMap Overpass API (ücretsiz fallback)
    if not leads and sector.get("osm_tag"):
        print(f"🗺️  OpenStreetMap ile aranıyor (ücretsiz)...")
        leads = await search_overpass(sector["osm_tag"], city)
        if leads:
            print(f"   ✅ OpenStreetMap: {len(leads)} işletme")

    if not leads:
        print("❌ Hiç lead bulunamadı.")
        print(f"   İpucu: https://www.google.com/maps/search/{sector['search_terms'][0]}+{city}")
        return

    created = 0
    for lead in leads:
        issues = []
        if not lead.get("website"):
            issues.append("Website yok")
        if int(lead.get("reviews", "0") or "0") < 50:
            issues.append("Az Google yorumu")

        print(f"   🤖 AI mesajı üretiliyor: {lead['name']}")
        pitch = await generate_sector_pitch(lead, sector, issues)

        filepath = create_crm_file(lead, sector, pitch, issues)
        print(f"   ✅ {lead['name']} → {filepath.split('/')[-1]}")
        created += 1

    git_push(f"🎯 Lead Hunter: {sector['key']} {city} — {created} lead")
    print(f"\n✅ {created} lead CRM'e eklendi ve push edildi.")


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
        print()
        print("Gerekli .env değişkenleri:")
        print("  GOOGLE_PLACES_API_KEY  — Google Places API anahtarı (zorunlu)")
        print("  OLLAMA_URL             — Ollama endpoint (varsayılan: http://localhost:11434/v1/chat/completions)")
        print("  OLLAMA_MODEL           — Model adı (varsayılan: mistral:7b)")
        sys.exit(0)

    asyncio.run(run(sys.argv[1], sys.argv[2]))
