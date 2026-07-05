import os
import json
import urllib.request
import re
import time
from datetime import datetime

API_KEY = os.environ.get("GEMINI_API_KEY")
if not API_KEY:
    raise ValueError("GEMINI_API_KEY environment variable not found. Please set the secret key in GitHub.")

def call_gemini(prompt, use_lite=False, use_grounding=True):
    model = "gemini-3.1-flash-lite" if use_lite else "gemini-3.5-flash"
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={API_KEY}"
    
    payload = {
        "contents": [{
            "parts": [{"text": prompt}]
        }]
    }
    if use_grounding:
        payload["tools"] = [{"googleSearch": {}}]
        
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    
    with urllib.request.urlopen(req, timeout=120) as response:
        return json.loads(response.read().decode("utf-8"))

CATEGORIES = [
    "Mutfak Gereçleri",
    "Güzellik ve Cilt Bakımı",
    "Ev ve Yaşam / Dekorasyon",
    "Evcil Hayvan Ürünleri",
    "Teknoloji ve Oto Aksesuar"
]

BLACKBLIST = [
    "sunset lamp", "gün batımı lambası", "galaxy projector", "galaksi projektör",
    "chomchom", "tüy toplayıcı", "massage gun", "masaj tabancası", "vegetable chopper",
    "sebze doğrayıcı", "nemlendirici", "humidifier", "water drop", "led strip", "led şerit"
]

def clean_json_string(text):
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\n", "", text)
        text = re.sub(r"\n```$", "", text)
        text = text.strip()
    return text

def is_saturated(product_name, description):
    combined = (product_name + " " + description).lower()
    for item in BLACKBLIST:
        if item in combined:
            return True
    return False

def scan_category(category):
    print(f"Scanning category: {category}...")
    prompt = f"""
    Lütfen Google Arama grounding aracını kullanarak son 7-14 gün içinde TikTok ve Instagram'da yeni viral olmaya başlamış, doymamış ve e-ticarete/dropshippinge uygun en az 20 farklı aday ürünü derinlemesine araştır. Bu adaylar arasından 4 Altın Kural puanı en yüksek olan, sosyal kanıtı (yorum talebi) en güçlü olan ve doymamış en iyi 10 ürünü seçerek detaylıca raporla. Acele etme, derinlemesine karşılaştırmalı analiz yap.

    Arama Yöntemleri ve Sorguları (Google Search Grounding aracını bu sorgularla tetikle):
    1. site:tiktok.com "tiktok made me buy it" "{category}"
    2. site:instagram.com "amazon finds" "{category}"
    3. viral dropshipping products "{category}" 2026
    4. problem solving gadgets "{category}"
    5. life hack products "{category}"

    Ürün Tespit ve Eleme Kriterleri:
    - Çekilebilirlik ve Pratiklik (Çelik Kuralı): LEGO veya dizilmesi/hazırlığı saatler süren ürünleri yeni başlayanlar için ele. Çekimi evde veya dışarıda telefonla kolayca yapılabilecek, karmaşık olmayan pratik ürünleri seç.
    - Sosyal Kanıt ve Yorum Analizi: Ürün videolarının veya inceleme sayfalarının yorumlarında insanların "fiyatı ne?", "nereden alabilirim?", "link?" gibi doğrudan satın alma niyeti belirten sorular sorduğunu doğrula.
    - Satürasyon (Doygunluk) Kontrolü: Chomchom tüy toplayıcı, gün batımı lambası, galaksi projektörü, masaj tabancası, klasik sebze doğrayıcı, hava nemlendirici gibi çoktan doymuş ürünleri listeleme. Tamamen yeni trendlere odaklan.

    Eğitim kriterlerimiz (4 Altın Kural) şunlardır:
    1. Görsel Tatmin (Visual Satisfaction) (1-5 Puan): Videoda izlemesi ne kadar keyifli, satisfying ve hipnotize edici?
    2. Problem Çözme Gücü (1-5 Puan): İnsanların günlük hayattaki can sıkıcı bir sorununu ne kadar güçlü çözüyor?
    3. Anında Anlaşılabilirlik (1-5 Puan): Videonun ilk 3 saniyesinde izleyici ürünün ne işe yaradığını hemen anlıyor mu?
    4. Tepki Potansiyeli (1-5 Puan): Yorum yazma, arkadaş etiketleme, paylaşma veya "nereden bulurum" deme isteği uyandırma gücü nedir?

    Yanıtını tam olarak şu JSON şemasında döndür. Markdown sarmalayıcıları (```json vb.) kullanma, doğrudan geçerli bir JSON string döndür:

    [
      {{
        "name": "Ürün Adı",
        "category": "{category}",
        "product_type": "Showcase" veya "Regular",
        "description": "Ürünün kısa açıklaması ve işlevi",
        "image_url": "Google Arama grounding aracıyla bulduğun, ürüne ait doğrudan geçerli bir görsel URL'si (Shopify CDN, AliExpress, Amazon, Pinterest vb. sitelerden hotlink edilebilir doğrudan jpg, png, webp vb. uzantılı resim adresi)",
        "video_url": "Google Arama grounding aracıyla bulduğun, bu ürünün viral olduğu TikTok veya Instagram video linki (örn: https://www.tiktok.com/@username/video/...) veya eğer doğrudan video linki bulamadıysan, bu ürünün TikTok üzerindeki arama linki (https://www.tiktok.com/search?q=urun-adi)",
        "why_viral": "Son 7-14 gündeki viral olma durumu, video yorumlarındaki talep seviyesi ve viral gerekçesi",
        "hook_ideas": [
          "Sesli Kanca: [Merak uyandıran sesli başlangıç cümlesi]",
          "Yazılı Kanca: [Sessiz izleyenler için ekranda görünecek dikkat çekici metin]",
          "Görsel Kanca: [İlk saniyede yapılacak sıra dışı görsel aksiyon/hareket]"
        ],
        "est_price": "29.99",
        "aliexpress_url": "https://www.aliexpress.com/w/wholesale-ürün-adı.html",
        "competitor_url": "Google Arama grounding aracıyla bulduğun, bu ürünü satan aktif bir dropshipping/Shopify mağaza linki (örn: https://storename.com/products/...) veya doğrudan bulamadıysan, bu ürünü satan Shopify mağazalarını aratacak Google arama linki (https://www.google.com/search?q=site:myshopify.com+urun-adi)",
        "creative_style": "Bu ürünü satmak için en uygun video konsepti türü (örn: 'Tersine Sarma Kurgusu', 'Kışkırtıcı Hata / Yorum Çekme', 'POV Yaşam Hilesi', 'Önce/Sonra Karşılaştırması')",
        "target_audience": "Bu ürünün duygusal bağ kuracağı spesifik hedef kitle / alt niş (örn: 'Minimalist mutfak severler', 'Kedi sahipleri')",
        "scores": {{
          "visual_satisfaction": 5,
          "problem_solving": 4,
          "immediate_understandability": 5,
          "reaction_potential": 5
        }},
        "total_score": 19,
        "verdict": "Winner Adayı"
      }}
    ]
    """

    res = None
    try:
        print("  -> Trying gemini-3.5-flash with search grounding...")
        res = call_gemini(prompt, use_lite=False, use_grounding=True)
    except Exception as e:
        print(f"  -> Grounding search failed: {e}. Retrying WITHOUT grounding...")
        try:
            res = call_gemini(prompt, use_lite=False, use_grounding=False)
        except Exception as e2:
            print(f"  -> Grounding-free gemini-3.5-flash also failed: {e2}. Switching to gemini-3.1-flash-lite fallback...")
            try:
                res = call_gemini(prompt, use_lite=True, use_grounding=False)
            except Exception as e3:
                print(f"  -> All fallback attempts failed: {e3}")
                return []

    try:
        if res and "candidates" in res and res["candidates"]:
            text = res["candidates"][0]["content"]["parts"][0]["text"].strip()
            cleaned = clean_json_string(text)
            products = json.loads(cleaned)
            
            # Filter out saturated items
            filtered = []
            for p in products:
                if not is_saturated(p.get("name", ""), p.get("description", "")):
                    filtered.append(p)
                else:
                    print(f"Skipping saturated product: {p.get('name')}")
            return filtered
        else:
            print(f"No candidates returned for {category}")
            return []
    except Exception as e:
        print(f"Error parsing response for category {category}: {e}")
        return []

def main():
    all_products = []
    for cat in CATEGORIES:
        products = scan_category(cat)
        all_products.extend(products)
        # Sleep to avoid rate limiting
        time.sleep(15)
        
    print(f"\nTotal products found in this scan: {len(all_products)}")
    
    # Add crawled_at field to newly scanned products
    import urllib.parse
    today_str = datetime.today().strftime('%Y-%m-%d')
    for p in all_products:
        p["crawled_at"] = today_str
        name = p.get("name", "")
        # Fallback to TikTok search if no direct video URL is provided by Gemini
        if not p.get("video_url") or not p["video_url"].startswith("http"):
            p["video_url"] = f"https://www.tiktok.com/search?q={urllib.parse.quote(name)}"
        # Fallback to Shopify competitor search if no direct competitor URL is provided by Gemini
        if not p.get("competitor_url") or not p["competitor_url"].startswith("http"):
            p["competitor_url"] = f"https://www.google.com/search?q=site:myshopify.com+{urllib.parse.quote(name)}"
        # Check defaults
        if not p.get("creative_style"):
            p["creative_style"] = "POV Yaşam Hilesi"
        if not p.get("target_audience"):
            p["target_audience"] = "Genel Alıcı Kitlesi"
        
    output_path = "precrawled_products.json"
    existing_products = []
    
    # Read existing products if file exists
    if os.path.exists(output_path):
        try:
            with open(output_path, "r", encoding="utf-8") as f:
                existing_products = json.load(f)
                if not isinstance(existing_products, list):
                    existing_products = []
            print(f"Loaded {len(existing_products)} existing products from history.")
        except Exception as e:
            print(f"Error reading existing products file: {e}")
            existing_products = []

    # Merge new products with existing history, avoiding duplicates by name (case-insensitive)
    existing_by_name = {p["name"].lower().strip(): p for p in existing_products if "name" in p}
    merged_products = list(existing_products)
    
    new_added_count = 0
    updated_count = 0
    
    for p in all_products:
        name_lower = p.get("name", "").lower().strip()
        if not name_lower:
            continue
        if name_lower in existing_by_name:
            # Overwrite the existing product details with updated info
            old_prod = existing_by_name[name_lower]
            idx = merged_products.index(old_prod)
            merged_products[idx] = p
            updated_count += 1
        else:
            # Append new product
            merged_products.append(p)
            new_added_count += 1
            
    print(f"Merge summary: {new_added_count} new products added, {updated_count} existing products updated.")
    
    # Save output
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(merged_products, f, indent=2, ensure_ascii=False)
    print(f"Saved total {len(merged_products)} products to {output_path}")

if __name__ == "__main__":
    main()
