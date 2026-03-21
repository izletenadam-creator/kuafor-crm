# Salon CRM — FS Roket Teknoloji

Her müşteri adayı bir dosya. Konuşma geçmişi, analiz, durum — hepsi burada.

## Yapı

```
leads/
  izmir/
    kuaforler/
      by-sadettin-kuafor.md      ← her müşteri ayrı dosya
      namik-koc-kuafor.md
      ...
    emlakcilar/
      ...
  istanbul/
    ...
templates/
  ilk-mesaj.md                   ← mesaj şablonları
  takip-mesaji.md
  demo-teklif.md
```

## Müşteri Dosya Formatı

```markdown
# Salon Adı
**Durum:** 🟡 İlk mesaj gönderildi | 🟢 Demo yapıldı | 🔴 Red | ✅ Müşteri

## Bilgiler
- Telefon: ...
- Adres: ...
- Rating: ...
- Website: ...

## Analiz
- Sorunları: ...

## Konuşma
| Tarih | Kimden | Mesaj |
|-------|--------|-------|
| 2026-03-21 | Biz | ... |
| 2026-03-21 | Müşteri | ... |
```

## Nasıl Çalışır
1. Lead topla (Google Maps scrape)
2. Analiz et (website, Maps, Instagram)
3. Kişisel mesaj üret (AI)
4. WhatsApp'tan gönder
5. Yanıtları AI ile cevapla
6. Her şeyi buraya logla
