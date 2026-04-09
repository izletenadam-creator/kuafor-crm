"""
World Scanner — Tüm dünyada sektör bazlı lead tarama makinesi
Google Places API + AI Analiz + WhatsApp Outreach + CRM

Kullanım:
  python3 world-scanner.py scan "kuaför" "TR" --cities "istanbul,ankara,izmir"
  python3 world-scanner.py scan "dentist" "DE" --cities "berlin,munich"
  python3 world-scanner.py scan "veterinary" "US" --cities "new york,los angeles"
  python3 world-scanner.py send --batch 20  # Günlük 20 mesaj gönder
  python3 world-scanner.py status           # Dashboard
  python3 world-scanner.py cron             # 7/24 daemon modu
"""

import os
import sys
import json
import asyncio
import httpx
import re
import time
import hashlib
from datetime import datetime, timedelta
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ── Config ──
AISA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/v1/chat/completions")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "mistral:7b")
WAHA_URL = os.getenv("WAHA_URL", "http://localhost:3000")
WAHA_KEY = os.getenv("WAHA_API_KEY", "")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT = os.getenv("TELEGRAM_CHAT_ID", "")
CRM_DIR = Path(os.getenv("CRM_DIR", Path(__file__).parent))
LEADS_DB = CRM_DIR / "leads-db.json"
QUEUE_FILE = CRM_DIR / "send-queue.json"
STATS_FILE = CRM_DIR / "stats.json"

# Google Places API (free $200/month credit)
GOOGLE_API_KEY = os.getenv("GOOGLE_PLACES_API_KEY", "")

# ── Ülke/Dil Config ──
COUNTRY_CONFIG = {
    "TR": {"lang": "tr", "currency": "₺", "phone_prefix": "+90", "name": "Türkiye"},
    "DE": {"lang": "de", "currency": "€", "phone_prefix": "+49", "name": "Almanya"},
    "US": {"lang": "en", "currency": "$", "phone_prefix": "+1", "name": "ABD"},
    "UK": {"lang": "en", "currency": "£", "phone_prefix": "+44", "name": "İngiltere"},
    "FR": {"lang": "fr", "currency": "€", "phone_prefix": "+33", "name": "Fransa"},
    "NL": {"lang": "nl", "currency": "€", "phone_prefix": "+31", "name": "Hollanda"},
    "SA": {"lang": "ar", "currency": "SAR", "phone_prefix": "+966", "name": "Suudi Arabistan"},
    "AE": {"lang": "ar", "currency": "AED", "phone_prefix": "+971", "name": "BAE"},
}

# ── Sektör Config (çok dilli) ──
SECTORS = {
    "kuaför": {
        "search": {"tr": "kuaför", "en": "hair salon", "de": "friseur", "fr": "coiffeur", "nl": "kapper", "ar": "صالون تجميل"},
        "osm_tag": "shop=hairdresser",
        "folder": "kuafor",
        "pain_points": {
            "tr": ["Randevu karışıklığı", "Telefona yetişememe", "Müşteri takibi yok", "Kampanya yapamama"],
            "en": ["Appointment chaos", "Missing phone calls", "No customer tracking", "Can't run campaigns"],
            "de": ["Terminchaos", "Verpasste Anrufe", "Keine Kundenverfolgung", "Keine Kampagnen"],
        },
    },
    "diş": {
        "search": {"tr": "diş kliniği", "en": "dental clinic", "de": "zahnarzt", "fr": "dentiste", "nl": "tandarts", "ar": "عيادة أسنان"},
        "osm_tag": "amenity=dentist",
        "folder": "dis",
    },
    "veteriner": {
        "search": {"tr": "veteriner", "en": "veterinary clinic", "de": "tierarzt", "fr": "vétérinaire", "nl": "dierenarts", "ar": "عيادة بيطرية"},
        "osm_tag": "amenity=veterinary",
        "folder": "veteriner",
    },
    "emlak": {
        "search": {"tr": "emlak ofisi", "en": "real estate agency", "de": "immobilienmakler", "fr": "agence immobilière", "nl": "makelaar", "ar": "مكتب عقارات"},
        "osm_tag": "office=estate_agent",
        "folder": "emlak",
    },
    "restoran": {
        "search": {"tr": "restoran", "en": "restaurant", "de": "restaurant", "fr": "restaurant", "nl": "restaurant", "ar": "مطعم"},
        "osm_tag": "amenity=restaurant",
        "folder": "restoran",
    },
    "oto": {
        "search": {"tr": "oto servis", "en": "auto repair shop", "de": "autowerkstatt", "fr": "garage automobile", "nl": "autogarage", "ar": "ورشة سيارات"},
        "osm_tag": "shop=car_repair",
        "folder": "oto",
    },
    "eczane": {
        "search": {"tr": "eczane", "en": "pharmacy", "de": "apotheke", "fr": "pharmacie", "nl": "apotheek", "ar": "صيدلية"},
        "osm_tag": "amenity=pharmacy",
        "folder": "eczane",
    },
    "spor": {
        "search": {"tr": "spor salonu", "en": "gym", "de": "fitnessstudio", "fr": "salle de sport", "nl": "sportschool", "ar": "صالة رياضية"},
        "osm_tag": "leisure=fitness_centre",
        "folder": "spor",
    },
    "otel": {
        "search": {"tr": "otel", "en": "hotel", "de": "hotel", "fr": "hôtel", "nl": "hotel", "ar": "فندق"},
        "osm_tag": "tourism=hotel",
        "folder": "otel",
    },
    "avukat": {
        "search": {"tr": "avukat", "en": "law firm", "de": "rechtsanwalt", "fr": "avocat", "nl": "advocaat", "ar": "محامي"},
        "osm_tag": "office=lawyer",
        "folder": "avukat",
    },
}

# ── Türkiye İlleri ──
TR_CITIES = [
    "istanbul", "ankara", "izmir", "bursa", "antalya", "adana", "konya",
    "gaziantep", "mersin", "diyarbakır", "kayseri", "eskişehir", "samsun",
    "denizli", "malatya", "trabzon", "manisa", "balıkesir", "hatay",
    "sakarya", "muğla", "tekirdağ", "van", "mardin", "aydın",
    "kocaeli", "elazığ", "kahramanmaraş", "erzurum", "batman",
]

DE_CITIES = ["berlin", "münchen", "hamburg", "köln", "frankfurt", "düsseldorf", "stuttgart", "leipzig"]
US_CITIES = ["new york", "los angeles", "chicago", "houston", "phoenix", "philadelphia", "san antonio", "san diego"]


def load_db() -> dict:
    if LEADS_DB.exists():
        with open(LEADS_DB) as f:
            return json.load(f)
    return {"leads": {}, "stats": {"total_scanned": 0, "total_sent": 0, "total_replied": 0}}


def save_db(db: dict):
    with open(LEADS_DB, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)


def lead_id(name: str, phone: str) -> str:
    """Unique lead ID"""
    return hashlib.md5(f"{name}:{phone}".encode()).hexdigest()[:12]


async def search_overpass(osm_tag: str, city: str, country: str) -> list:
    """OpenStreetMap Overpass API — API key gerekmez, ücretsiz"""
    key, value = osm_tag.split("=", 1)
    country_cfg = COUNTRY_CONFIG.get(country, {})
    country_name = country_cfg.get("name", country)
    headers = {"User-Agent": "kuafor-crm/1.0 (world-scanner)"}

    try:
        async with httpx.AsyncClient(timeout=25, headers=headers) as client:
            geo = await client.get(
                "https://nominatim.openstreetmap.org/search",
                params={"q": f"{city}, {country_name}", "format": "json", "limit": 1},
            )
            geo_data = geo.json()
            if not geo_data:
                return []

            south, north, west, east = geo_data[0]["boundingbox"]
            await asyncio.sleep(1)

            query = f"""[out:json][timeout:30];
(
  node["{key}"="{value}"]({south},{west},{north},{east});
  way["{key}"="{value}"]({south},{west},{north},{east});
);
out body 60;"""

            ov = await client.post("https://overpass-api.de/api/interpreter", data=query)
            elements = ov.json().get("elements", [])

            leads = []
            for el in elements:
                tags = el.get("tags", {})
                name = tags.get("name") or tags.get(f"name:{country_cfg.get('lang','en')}", "")
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
        print(f"   ❌ Overpass hatası: {e}")
        return []


async def search_google_maps(query: str, city: str, country: str, lang: str) -> list:
    """Google Maps'te arama yap — API veya scrape"""
    
    # Google Places API varsa kullan (en güvenilir)
    if GOOGLE_API_KEY:
        return await _search_places_api(query, city, country, lang)
    
    # Yoksa SearXNG ile dene
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                "http://localhost:8080/search",
                params={
                    "q": f"{query} {city} telefon",
                    "format": "json",
                    "engines": "google",
                    "language": lang,
                },
            )
            if resp.status_code == 200:
                results = resp.json().get("results", [])
                leads = []
                for r in results[:20]:
                    # Telefon numarası çıkar
                    text = r.get("content", "") + " " + r.get("title", "")
                    phones = re.findall(r'[\+]?[0-9\s\-\(\)]{10,15}', text)
                    if phones:
                        leads.append({
                            "name": r.get("title", "")[:60],
                            "phone": phones[0].strip(),
                            "address": city,
                            "source": "searxng",
                        })
                return leads
    except:
        pass
    
    # Son çare: AI ile sahte veri üretme — boş dön
    return []


async def _search_places_api(query: str, city: str, country: str, lang: str) -> list:
    """Google Places API (Text Search)"""
    leads = []
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            # Text Search
            resp = await client.get(
                "https://maps.googleapis.com/maps/api/place/textsearch/json",
                params={
                    "query": f"{query} in {city}",
                    "key": GOOGLE_API_KEY,
                    "language": lang,
                },
            )
            data = resp.json()
            
            for place in data.get("results", [])[:20]:
                place_id = place.get("place_id")
                
                # Place Details — telefon ve website al
                detail_resp = await client.get(
                    "https://maps.googleapis.com/maps/api/place/details/json",
                    params={
                        "place_id": place_id,
                        "fields": "name,formatted_phone_number,international_phone_number,website,formatted_address,rating,user_ratings_total",
                        "key": GOOGLE_API_KEY,
                        "language": lang,
                    },
                )
                detail = detail_resp.json().get("result", {})
                
                phone = detail.get("international_phone_number", "")
                if phone:
                    leads.append({
                        "name": detail.get("name", ""),
                        "phone": phone,
                        "address": detail.get("formatted_address", ""),
                        "website": detail.get("website", ""),
                        "rating": str(detail.get("rating", "")),
                        "reviews": str(detail.get("user_ratings_total", "")),
                        "source": "google_places",
                        "place_id": place_id,
                    })
                
                await asyncio.sleep(0.1)  # Rate limit
    except Exception as e:
        print(f"❌ Places API error: {e}")
    
    return leads


async def analyze_and_pitch(lead: dict, sector: str, country: str, lang: str) -> dict:
    """Lead'i analiz et ve kişisel mesaj üret"""
    
    country_cfg = COUNTRY_CONFIG.get(country, {"lang": "en", "name": country})
    sector_cfg = SECTORS.get(sector, {})
    
    issues = []
    if not lead.get("website"):
        issues.append("Website yok" if lang == "tr" else "No website")
    if int(lead.get("reviews", "0") or "0") < 50:
        issues.append("Az yorum" if lang == "tr" else "Few reviews")
    
    prompt = f"""Write a WhatsApp outreach message for a business.

BUSINESS: {lead['name']}
SECTOR: {sector}
CITY: {lead.get('address', '')}
COUNTRY: {country_cfg['name']}
LANGUAGE: {lang} (WRITE IN THIS LANGUAGE!)
RATING: {lead.get('rating', '?')} ({lead.get('reviews', '?')} reviews)

ISSUES: {', '.join(issues) if issues else 'General outreach'}

YOU ARE: Fatih from FS Roket Technology. Professional, friendly, not pushy.
OFFERING: Digital management system — automation, appointment booking, customer tracking, reminders.
Free first month trial.

RULES:
1. Write in {lang} language!
2. 3-4 sentences max
3. Mention their specific issue
4. Offer free demo
5. WhatsApp format (*bold*)
6. Never say "bot", "AI", "Ela"
7. Sound human, not robotic

Write ONLY the message."""

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                AISA_URL,
                json={"model": OLLAMA_MODEL, "messages": [{"role": "user", "content": prompt}], "temperature": 0.7, "max_tokens": 250},
                headers={"Content-Type": "application/json"},
            )
            pitch = resp.json()["choices"][0]["message"]["content"]
    except:
        pitch = ""
    
    lead["pitch"] = pitch
    lead["issues"] = issues
    lead["sector"] = sector
    lead["country"] = country
    lead["lang"] = lang
    lead["analyzed_at"] = datetime.now().isoformat()
    
    return lead


async def scan_city(sector: str, city: str, country: str):
    """Bir şehirde bir sektörü tara"""
    country_cfg = COUNTRY_CONFIG.get(country, {"lang": "en"})
    lang = country_cfg["lang"]
    sector_cfg = SECTORS.get(sector, {})
    search_term = sector_cfg.get("search", {}).get(lang, sector)
    
    print(f"\n🔍 Taranıyor: {search_term} — {city} ({country})")
    
    leads = await search_google_maps(search_term, city, country, lang)

    # Google Places boş döndüyse OpenStreetMap ile dene
    if not leads and sector_cfg.get("osm_tag"):
        print(f"   🗺️  OpenStreetMap fallback...")
        leads = await search_overpass(sector_cfg["osm_tag"], city, country)

    print(f"   📊 {len(leads)} lead bulundu")

    if not leads:
        return []
    
    # Analiz et
    analyzed = []
    for lead in leads:
        lead["city"] = city
        result = await analyze_and_pitch(lead, sector, country, lang)
        analyzed.append(result)
        print(f"   ✅ {lead['name']} — {lead.get('phone', '?')}")
    
    # DB'ye kaydet
    db = load_db()
    for lead in analyzed:
        lid = lead_id(lead["name"], lead.get("phone", ""))
        if lid not in db["leads"]:
            db["leads"][lid] = lead
            db["stats"]["total_scanned"] += 1
    save_db(db)
    
    # CRM dosyaları oluştur
    folder = CRM_DIR / "leads" / city / sector_cfg.get("folder", sector)
    folder.mkdir(parents=True, exist_ok=True)
    
    for lead in analyzed:
        slug = re.sub(r'[^a-z0-9]+', '-', lead["name"].lower()[:40]).strip('-')
        filepath = folder / f"{slug}.md"
        if not filepath.exists():
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(f"# {lead['name']}\n")
                f.write(f"**Durum:** ⬜ Hazır\n")
                f.write(f"**Telefon:** {lead.get('phone','?')}\n")
                f.write(f"**Adres:** {lead.get('address','?')}\n")
                f.write(f"**Rating:** ⭐{lead.get('rating','?')} ({lead.get('reviews','?')})\n")
                f.write(f"**Website:** {lead.get('website','❌')}\n\n")
                f.write(f"## Mesaj\n```\n{lead.get('pitch','')}\n```\n")
    
    return analyzed


async def send_batch(count: int = 20):
    """Günlük mesaj gönderimi — ban riski olmadan"""
    db = load_db()
    unsent = [l for l in db["leads"].values() if l.get("status") != "sent" and l.get("phone")]
    
    if not unsent:
        print("📭 Gönderilecek lead kalmadı")
        return
    
    batch = unsent[:count]
    print(f"📤 {len(batch)} mesaj gönderiliyor...\n")
    
    sent = 0
    for lead in batch:
        phone = lead.get("phone", "")
        pitch = lead.get("pitch", "")
        if not phone or not pitch:
            continue
        
        # WhatsApp'tan gönder
        try:
            chat_id = re.sub(r'[^0-9]', '', phone)
            if not chat_id.startswith("9"):
                chat_id = chat_id.lstrip("0")
            chat_id = f"{chat_id}@c.us"
            
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(
                    f"{WAHA_URL}/api/sendText",
                    json={"chatId": chat_id, "text": pitch, "session": "default"},
                    headers={"X-Api-Key": WAHA_KEY},
                )
                if resp.status_code in (200, 201):
                    lid = lead_id(lead["name"], phone)
                    db["leads"][lid]["status"] = "sent"
                    db["leads"][lid]["sent_at"] = datetime.now().isoformat()
                    db["stats"]["total_sent"] += 1
                    sent += 1
                    print(f"   ✅ {lead['name']} → {phone}")
                else:
                    print(f"   ❌ {lead['name']} → {resp.status_code}")
        except Exception as e:
            print(f"   ❌ {lead['name']} → {e}")
        
        await asyncio.sleep(15)  # 15 sn bekle — ban koruması
    
    save_db(db)
    
    # Telegram bildir
    await _telegram(f"📤 *Günlük mesaj gönderimi*\n✅ {sent}/{len(batch)} gönderildi\n📊 Toplam: {db['stats']['total_sent']} mesaj")
    
    print(f"\n✅ {sent} mesaj gönderildi")


def show_status():
    """Dashboard"""
    db = load_db()
    s = db["stats"]
    leads = db["leads"]
    
    sent = len([l for l in leads.values() if l.get("status") == "sent"])
    replied = len([l for l in leads.values() if l.get("status") == "replied"])
    pending = len([l for l in leads.values() if l.get("status") != "sent"])
    
    # Sektör bazlı
    sectors = {}
    for l in leads.values():
        sec = l.get("sector", "?")
        sectors[sec] = sectors.get(sec, 0) + 1
    
    # Şehir bazlı
    cities = {}
    for l in leads.values():
        city = l.get("city", "?")
        cities[city] = cities.get(city, 0) + 1
    
    print("=" * 50)
    print("📊 WORLD SCANNER — DASHBOARD")
    print("=" * 50)
    print(f"📋 Toplam lead: {len(leads)}")
    print(f"📤 Gönderilen: {sent}")
    print(f"📩 Yanıt gelen: {replied}")
    print(f"⏳ Bekleyen: {pending}")
    print()
    print("📂 Sektörler:")
    for sec, count in sorted(sectors.items(), key=lambda x: -x[1]):
        print(f"   {sec}: {count}")
    print()
    print("🌍 Şehirler:")
    for city, count in sorted(cities.items(), key=lambda x: -x[1])[:10]:
        print(f"   {city}: {count}")


async def _telegram(text: str):
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                json={"chat_id": TELEGRAM_CHAT, "text": text, "parse_mode": "Markdown"},
            )
    except:
        pass


async def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return
    
    cmd = sys.argv[1]
    
    if cmd == "scan":
        if len(sys.argv) < 4:
            print("Kullanım: python3 world-scanner.py scan <sektör> <ülke> [--cities şehir1,şehir2]")
            return
        
        sector = sys.argv[2]
        country = sys.argv[3].upper()
        
        # Şehirleri belirle
        cities = []
        if "--cities" in sys.argv:
            idx = sys.argv.index("--cities")
            cities = sys.argv[idx + 1].split(",")
        elif country == "TR":
            cities = TR_CITIES[:10]  # İlk 10 il
        elif country == "DE":
            cities = DE_CITIES
        elif country == "US":
            cities = US_CITIES
        else:
            cities = [sys.argv[4]] if len(sys.argv) > 4 else [""]
        
        print(f"🌍 WORLD SCANNER")
        print(f"   Sektör: {sector}")
        print(f"   Ülke: {country}")
        print(f"   Şehirler: {', '.join(cities)}")
        
        total = 0
        for city in cities:
            results = await scan_city(sector, city.strip(), country)
            total += len(results)
        
        print(f"\n🎯 TOPLAM: {total} lead toplandı")
        
        # Git push
        os.system(f'cd "{CRM_DIR}" && git add -A && git commit -m "🌍 Scan: {sector} {country} — {total} lead" --quiet 2>/dev/null && git push --quiet 2>/dev/null')
    
    elif cmd == "send":
        count = 20
        if "--batch" in sys.argv:
            idx = sys.argv.index("--batch")
            count = int(sys.argv[idx + 1])
        await send_batch(count)
    
    elif cmd == "status":
        show_status()
    
    elif cmd == "cron":
        print("🤖 Cron modu — 7/24 çalışıyor")
        while True:
            # Her 6 saatte scan
            for sector in ["kuaför", "diş", "veteriner"]:
                for city in TR_CITIES[:5]:
                    await scan_city(sector, city, "TR")
                    await asyncio.sleep(5)
            
            # Her gün 20 mesaj gönder
            await send_batch(20)
            
            # 6 saat bekle
            print(f"⏰ Sonraki scan: {(datetime.now() + timedelta(hours=6)).strftime('%H:%M')}")
            await asyncio.sleep(6 * 3600)


if __name__ == "__main__":
    asyncio.run(main())
