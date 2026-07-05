#!/usr/bin/env python3
import os
import json
import time
import urllib.request
import urllib.parse
import re
from datetime import datetime

# Path definitions
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
COOKIES_PATH = os.path.join(BASE_DIR, "tiktok_cookies.json")
SEEN_VIDEOS_PATH = os.path.join(BASE_DIR, "seen_tiktok_videos.json")
PRODUCTS_PATH = os.path.join(BASE_DIR, "precrawled_products.json")
PORTAL_PATH = os.path.join(BASE_DIR, "index.html")

def get_api_key():
    """Attempts to find the Gemini API Key from multiple sources: env, argument, or portal localStorage."""
    # 1. Environment Variable
    env_key = os.environ.get("GEMINI_API_KEY")
    if env_key:
        return env_key

    # 2. LocalStorage Extraction fallback
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            # Navigate to the portal index file locally
            local_url = f"file://{PORTAL_PATH}"
            page.goto(local_url)
            api_key = page.evaluate("localStorage.getItem('gemini_api_key')")
            browser.close()
            if api_key:
                print(f"[*] API Key successfully auto-retrieved from Portal LocalStorage: {api_key[:6]}...{api_key[-4:]}")
                return api_key
    except Exception as e:
        pass
    
    return None

def load_seen_videos():
    if os.path.exists(SEEN_VIDEOS_PATH):
        try:
            with open(SEEN_VIDEOS_PATH, "r", encoding="utf-8") as f:
                return set(json.load(f))
        except Exception:
            return set()
    return set()

def save_seen_videos(seen_set):
    try:
        with open(SEEN_VIDEOS_PATH, "w", encoding="utf-8") as f:
            json.dump(list(seen_set), f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[-] Error saving seen videos: {e}")

def call_gemini(api_key, prompt, model="gemini-3.5-flash", use_grounding=False):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
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
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            return json.loads(response.read().decode("utf-8"))
    except Exception as e:
        print(f"[-] Gemini API call failed: {e}")
        return None

def evaluate_video_with_gemini(api_key, video_data):
    """Sends video data to Gemini to classify as dropshipping candidate, score it, and draft comment/likes strategy."""
    prompt = f"""
    Aşağıdaki TikTok videosuna ait verileri (yazar, açıklama, yorumlar) analiz et:
    Yazar: {video_data.get('author')}
    Açıklama: {video_data.get('description')}
    Kayıtlı Yorumlar: {json.dumps(video_data.get('comments', []), ensure_ascii=False)}

    Bu videodaki ürünün e-ticarete/dropshippinge uygun yeni viral bir winner ürün olup olmadığını tespit et.
    Kriterler:
    - Çekilebilirlik ve Pratiklik (Çelik Kuralı): Evde telefonla çekilebilecek pratik bir ürün olmalı.
    - Saturated olmamalı (klasik doymuş ürünleri ele).
    - Yorumlardaki satın alma niyeti (fiyat, link sorma oranı) yüksek olmalı.

    Eğer ürün dropshippinge uygunsa:
    - 4 Altın Kural Puanı ver (Görsel Tatmin, Problem Çözme, Anlaşılabilirlik, Tepki - her biri 1-5 arası).
    - Hedef Kitle ve Kurgu tarzını belirle.
    - 3 adet reklam kancası (hooks) üret (Sesli, Yazılı, Görsel).
    - Tedarik ve Türkiye gümrük analizini yap (Örn: Numune için Trendyol, ölçekleme için özel DDP acenteleri).
    - İnsansı etkileşim olarak botun bu videoyu beğenip (give_like: true), kaydetmesini (give_save: true) öner.
    - AI yorumu üret (post_comment: true). Yorum çok kısa, doğal ve insansı olmalı (Örn: "I need this!", "Link please?", "This looks so satisfying!"). Ürün videosu dışındaki saçma videolara asla yorum yazma (post_comment: false).

    Yanıtını tam olarak aşağıdaki JSON şemasında döndür. Markdown sarmalayıcıları (```json vb.) kullanma, doğrudan geçerli bir JSON string döndür:

    {{
      "is_dropshipping_product": true/false,
      "product_name": "Bulunan Ürün Adı",
      "category": "Mutfak Gereçleri" veya "Güzellik ve Cilt Bakımı" veya "Ev ve Yaşam / Dekorasyon" veya "Evcil Hayvan Ürünleri" veya "Teknoloji ve Oto Aksesuar",
      "description": "Ürün açıklaması",
      "why_viral": "Viral olma gerekçesi ve yorumlardaki satın alma talebi",
      "creative_style": "Önerilen reklam kurgusu konsepti",
      "target_audience": "Hedef kitle tanımı",
      "scores": {{
        "visual_satisfaction": 5,
        "problem_solving": 4,
        "immediate_understandability": 5,
        "reaction_potential": 5
      }},
      "hook_ideas": [
        "Sesli Kanca: ...",
        "Yazılı Kanca: ...",
        "Görsel Kanca: ..."
      ],
      "sourcing_tips": "Numune alma ve özel acente tedarik tavsiyesi",
      "customs_warning": "30 Euro limiti ve DDP kargo gümrük uyarısı",
      "give_like": true/false,
      "give_save": true/false,
      "post_comment": true/false,
      "comment_content": "AI üretimi kısa insansı yorum"
    }}
    """
    
    res = call_gemini(api_key, prompt, model="gemini-3.5-flash")
    if res and "candidates" in res and res["candidates"]:
        try:
            text = res["candidates"][0]["content"]["parts"][0]["text"].strip()
            # Clean markdown wrappers if any
            if text.startswith("```"):
                text = re.sub(r"^```(?:json)?\n", "", text)
                text = re.sub(r"\n```$", "", text)
                text = text.strip()
            return json.loads(text)
        except Exception as e:
            print(f"[-] Error parsing Gemini JSON: {e}")
    return {"is_dropshipping_product": False}

def sync_product_to_portal(product):
    """Appends a newly discovered winner product to the shared database."""
    products = []
    if os.path.exists(PRODUCTS_PATH):
        try:
            with open(PRODUCTS_PATH, "r", encoding="utf-8") as f:
                products = json.load(f)
                if not isinstance(products, list):
                    products = []
        except Exception:
            pass

    # Check for duplicates by name
    if any(p.get("name", "").lower() == product.get("name", "").lower() for p in products):
        print(f"[*] Product {product.get('name')} already in database. Skipping sync.")
        return

    product["crawled_at"] = datetime.today().strftime('%Y-%m-%d')
    product["product_type"] = "Showcase" if product.get("scores", {}).get("shooting_feasibility", 5) >= 4 else "Regular"
    
    # Map values to match UI format
    total_score = sum(product.get("scores", {}).values())
    product["total_score"] = total_score
    product["verdict"] = "Winner Adayı" if total_score >= 15 else "Test Edilebilir"
    product["est_price"] = "29.99"
    product["competitor_url"] = f"https://www.google.com/search?q=site:myshopify.com+{urllib.parse.quote(product.get('name', ''))}"
    product["video_url"] = f"https://www.tiktok.com/search?q={urllib.parse.quote(product.get('name', '') + ' made me buy it')}"

    products.insert(0, product) # Add to top
    
    try:
        with open(PRODUCTS_PATH, "w", encoding="utf-8") as f:
            json.dump(products, f, indent=2, ensure_ascii=False)
        print(f"[+] Product {product.get('name')} successfully synced to EcomFlow portal database!")
    except Exception as e:
        print(f"[-] Error writing to precrawled products: {e}")

def run_burner_automation(api_key, duration_minutes=30):
    from playwright.sync_api import sync_playwright
    
    seen_videos = load_seen_videos()
    print(f"[*] Loaded {len(seen_videos)} seen videos.")
    print(f"[*] Launching TikTok Burner automation (Target Duration: {duration_minutes} minutes)...")

    # Start Playwright chromium
    with sync_playwright() as playwright_instance:
        # Launch browser. Headless=False if we need to let the user log in
        headless_mode = os.path.exists(COOKIES_PATH)
        browser = playwright_instance.chromium.launch(
            headless=headless_mode,
            args=["--mute-audio", "--no-sandbox"]
        )
        
        # Load context
        if os.path.exists(COOKIES_PATH):
            print("[*] Stored TikTok cookies found. Loading session context...")
            with open(COOKIES_PATH, "r") as f:
                cookies = json.load(f)
            context = browser.new_context()
            context.add_cookies(cookies)
        else:
            print("[!] TikTok cookies not found! Opening browser for manual login...")
            context = browser.new_context()
        
        page = context.new_page()
        page.goto("https://www.tiktok.com/foryou", wait_until="domcontentloaded")

        # Handle login if cookies were missing
        if not os.path.exists(COOKIES_PATH):
            print("[!] TikTok oturum çerezleri bulunamadı. Lütfen açılan tarayıcı penceresinden hesabınıza giriş yapın.")
            print("[*] QR kod okutarak veya normal girişle (gerekirse yapbozu çözerek) giriş yapabilirsiniz.")
            page.goto("https://www.tiktok.com/login", wait_until="domcontentloaded")
            
            # Check in a loop for login success
            login_success = False
            for i in range(120): # Up to 2 minutes
                time.sleep(1)
                # If we redirected away from the login subdomain/page
                if "login" not in page.url:
                    login_success = True
                    break
            
            if login_success:
                print("[+] Giriş başarılı! Çerezler kaydediliyor...")
                time.sleep(3) # Wait for page to settle
                cookies = context.cookies()
                with open(COOKIES_PATH, "w") as f:
                    json.dump(cookies, f, indent=2)
                print("[+] Çerezler başarıyla 'tiktok_cookies.json' dosyasına kaydedildi!")
                page.goto("https://www.tiktok.com/foryou", wait_until="domcontentloaded")
            else:
                print("[-] Giriş zaman aşımına uğradı. Lütfen scripti tekrar çalıştırıp giriş yapın.")
                browser.close()
                return

        # Start scraping loop
        start_time = time.time()
        end_time = start_time + (duration_minutes * 60)
        
        video_count = 0
        validated_count = 0
        
        while time.time() < end_time:
            time.sleep(3) # Wait for page load / transition
            
            # Extract video details
            try:
                # Get current video element or URL
                current_url = page.url
                video_id = None
                match = re.search(r"/video/(\d+)", current_url)
                if match:
                    video_id = match.group(1)
                else:
                    # Alternative url hash or identifier
                    video_id = current_url.split("?")[0]
                
                # Check for duplicates
                if video_id in seen_videos:
                    print(f"[*] Skipping duplicate video: {video_id}")
                    # Swipe down to next video
                    page.keyboard.press("ArrowDown")
                    continue
                
                seen_videos.add(video_id)
                save_seen_videos(seen_videos)
                
                # Extract caption & author
                caption_el = page.query_selector('h1[data-e2e="browse-video-desc"]') or page.query_selector('div[data-e2e="video-desc"]')
                caption = caption_el.inner_text() if caption_el else "Ürün Açıklaması Alınamadı"
                
                author_el = page.query_selector('span[data-e2e="browse-username"]') or page.query_selector('h3[data-e2e="video-author-uniqueid"]')
                author = author_el.inner_text() if author_el else "Bilinmeyen Kullanıcı"
                
                # Extract comments
                comments = []
                comment_els = page.query_selector_all('p[data-e2e="comment-level-1"]') or page.query_selector_all('p[class*="CommentText"]')
                for el in comment_els[:10]: # Check first 10 comments
                    try:
                        comments.append(el.inner_text())
                    except Exception:
                        pass
                
                video_data = {
                    "url": current_url,
                    "author": author,
                    "description": caption,
                    "comments": comments
                }
                
                video_count += 1
                print(f"\n[*] Evaluating Video #{video_count} by @{author}: {caption[:50]}...")
                
                # Evaluate with Gemini
                decision = evaluate_video_with_gemini(api_key, video_data)
                
                if decision.get("is_dropshipping_product"):
                    validated_count += 1
                    print(f"[+] Verified Dropshipping Candidate: {decision.get('product_name')} (Score: {decision.get('scores', {}).get('visual_satisfaction', 0) + decision.get('scores', {}).get('problem_solving', 0) + decision.get('scores', {}).get('immediate_understandability', 0) + decision.get('scores', {}).get('reaction_potential', 0)}/20)")
                    
                    # Watch video (Simulate humanlike watch-time 15-20s)
                    watch_sec = 15
                    print(f"[*] Watching video for {watch_sec} seconds...")
                    time.sleep(watch_sec)
                    
                    # Interact 1: Like
                    if decision.get("give_like"):
                        try:
                            like_btn = page.query_selector('span[data-e2e="like-icon"]') or page.query_selector('button[class*="Like"]')
                            if like_btn:
                                like_btn.click()
                                print("[*] Dropped Like on video.")
                        except Exception as e:
                            print(f"[-] Could not click like button: {e}")
                            
                    # Interact 2: Save
                    if decision.get("give_save"):
                        try:
                            save_btn = page.query_selector('span[data-e2e="save-icon"]') or page.query_selector('button[class*="Collect"]')
                            if save_btn:
                                save_btn.click()
                                print("[*] Bookmarked video.")
                        except Exception as e:
                            print(f"[-] Could not click save button: {e}")
                            
                    # Interact 3: Comment
                    if decision.get("post_comment") and decision.get("comment_content"):
                        try:
                            comment_input = page.query_selector('div[contenteditable="true"]') or page.query_selector('input[data-e2e="comment-input"]')
                            if comment_input:
                                comment_input.click()
                                time.sleep(1)
                                comment_input.fill(decision["comment_content"])
                                time.sleep(1)
                                post_btn = page.query_selector('div[data-e2e="comment-post"]') or page.query_selector('button[class*="Post"]')
                                if post_btn:
                                    post_btn.click()
                                    print(f"[*] Posted AI comment: '{decision['comment_content']}'")
                        except Exception as e:
                            print(f"[-] Could not post comment: {e}")
                            
                    # Sync validated winner candidate to portal database
                    sync_product_to_portal({
                        "name": decision.get("product_name"),
                        "category": decision.get("category"),
                        "description": decision.get("description"),
                        "why_viral": decision.get("why_viral"),
                        "creative_style": decision.get("creative_style"),
                        "target_audience": decision.get("target_audience"),
                        "scores": decision.get("scores"),
                        "hook_ideas": decision.get("hook_ideas"),
                        "sourcing_tips": decision.get("sourcing_tips"),
                        "customs_warning": decision.get("customs_warning"),
                        "image_url": "https://images.unsplash.com/photo-1523275335684-37898b6baf30?auto=format&fit=crop&q=80&w=200" # Placeholder
                    })
                else:
                    # Swipe immediately
                    print("[-] Not a winner candidate. Swiping next.")
                    
            except Exception as e:
                print(f"[-] Error processing current video element: {e}")
            
            # Swipe down to next video
            page.keyboard.press("ArrowDown")
            
        browser.close()
        print(f"\n[+] Scans completed. Evaluated: {video_count} videos. Validated: {validated_count} products.")

if __name__ == "__main__":
    api_key = get_api_key()
    if not api_key:
        print("[-] GEMINI_API_KEY could not be found. Please set the environment variable or add it in your portal localStorage.")
        # Attempt to prompt
        api_key = input("Lütfen Gemini API Anahtarınızı girin: ").strip()
    
    if api_key:
        run_burner_automation(api_key, duration_minutes=30)
    else:
        print("[-] Aborting. API key is required.")
