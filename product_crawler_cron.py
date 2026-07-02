import os
import json
import urllib.request
import re
import time
from datetime import datetime

API_KEY = os.environ.get("GEMINI_API_KEY")
if not API_KEY:
    raise ValueError("GEMINI_API_KEY environment variable not found. Please set the secret key in GitHub.")

URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={API_KEY}"

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
    Lütfen Google Arama grounding aracını kullanarak son 7-14 gün içinde TikTok ve Instagram'da yeni viral olmaya başlamış, doymamış ve e-ticarete/dropshippinge uygun 10 adet benzersiz "{category}" ürünü tespit et.

    Eğitim kriterlerimiz şunlardır:
    1. Ürün Tipi: 'Showcase' (gösterişli, estetik ve çekimi kolay) veya 'Regular' (hikaye/kurgu gerektiren, yüksek potansiyelli).
    2. Viral Potansiyel (1-5 Puan)
    3. Çekilebilirlik/İçerik Kolaylığı (1-5 Puan)
    4. Satın Alma Talebi (1-5 Puan)
    5. Problem Çözme/Değer (1-5 Puan)
    6. Tedarik/Kargo Kolaylığı (1-5 Puan)

    ÖNEMLİ: Klasikleşmiş, doymuş ürünleri kesinlikle listeleme! Tamamen yeni trendlere odaklan.

    Yanıtını tam olarak şu JSON şemasında döndür. Markdown sarmalayıcıları (```json vb.) kullanma, doğrudan geçerli bir JSON string döndür:

    [
      {{
        "name": "Ürün Adı",
        "category": "{category}",
        "product_type": "Showcase" veya "Regular",
        "description": "Ürünün kısa açıklaması ve işlevi",
        "image_url": "Google Arama grounding aracıyla bulduğun, ürüne ait doğrudan geçerli bir görsel URL'si (Shopify CDN, AliExpress, Amazon, Pinterest vb. sitelerden hotlink edilebilir doğrudan jpg, png, webp vb. uzantılı resim adresi)",
        "why_viral": "Son 7-14 gündeki viral olma durumu ve gerekçesi",
        "hook_ideas": ["Kanca fikri 1", "Kanca fikri 2"],
        "est_price": "29.99",
        "aliexpress_url": "https://www.aliexpress.com/w/wholesale-ürün-adı.html",
        "scores": {{
          "viral_potential": 4,
          "shooting_feasibility": 5,
          "purchase_desire": 4,
          "problem_solving": 5,
          "shipping_ease": 5
        }},
        "total_score": 23,
        "verdict": "Winner Adayı"
      }}
    ]
    """

    payload = {
        "contents": [{
            "parts": [{"text": prompt}]
        }],
        "tools": [{"googleSearch": {}}]
    }

    req = urllib.request.Request(
        URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )

    try:
        with urllib.request.urlopen(req) as response:
            res = json.loads(response.read().decode("utf-8"))
            if "candidates" in res and res["candidates"]:
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
        print(f"Error scanning category {category}: {e}")
        return []

def main():
    all_products = []
    for cat in CATEGORIES:
        products = scan_category(cat)
        all_products.extend(products)
        # Sleep to avoid rate limiting
        time.sleep(3)
        
    print(f"\nTotal products found in this scan: {len(all_products)}")
    
    # Add crawled_at field to newly scanned products
    today_str = datetime.today().strftime('%Y-%m-%d')
    for p in all_products:
        p["crawled_at"] = today_str
        
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
