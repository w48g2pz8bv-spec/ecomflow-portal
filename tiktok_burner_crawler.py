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

def safe_goto(page, url, timeout=15000):
    try:
        print(f"[*] Navigating to {url}...")
        page.goto(url, wait_until="commit", timeout=timeout)
        return True
    except Exception as e:
        print(f"[-] Navigation warning for {url}: {e}. Proceeding anyway...")
        return False

def get_api_key():
    """Attempts to find the Gemini API Key from multiple sources: env, local file."""
    # 1. Environment Variable
    env_key = os.environ.get("GEMINI_API_KEY")
    if env_key:
        return env_key

    # 2. Local text file
    secret_path = os.path.join(BASE_DIR, "gemini_api_key.txt")
    if os.path.exists(secret_path):
        try:
            with open(secret_path, "r", encoding="utf-8") as f:
                return f.read().strip()
        except Exception:
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
    import urllib.error
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
    
    retries = 3
    delay = 6
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=60) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 429:
                print(f"[-] Gemini API Rate Limit (429) encountered. Retrying in {delay} seconds (Attempt {attempt+1}/{retries})...")
                time.sleep(delay)
                delay *= 2
            else:
                print(f"[-] Gemini HTTP Error {e.code}: {e.reason}")
                break
        except Exception as e:
            print(f"[-] Gemini API call failed: {e}")
            break
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

def capture_video_screenshot(page, video_id):
    os.makedirs(os.path.join(BASE_DIR, "product_images"), exist_ok=True)
    img_path = os.path.join(BASE_DIR, "product_images", f"{video_id}.png")
    try:
        # Try to locate the video element or container
        video_el = page.query_selector('video') or page.query_selector('div[data-e2e="feed-active-video"]')
        if video_el:
            video_el.screenshot(path=img_path)
        else:
            page.screenshot(path=img_path)
        print(f"[+] Screenshot captured: product_images/{video_id}.png")
        return f"product_images/{video_id}.png"
    except Exception as e:
        print(f"[-] Could not capture video screenshot: {e}")
        return "https://images.unsplash.com/photo-1523275335684-37898b6baf30?auto=format&fit=crop&q=80&w=200"

def run_warmup_search(page):
    import random
    keywords = [
        "tiktok made me buy it", 
        "amazon finds", 
        "dropshipping product", 
        "viral gadget", 
        "cool product", 
        "must have gadgets"
    ]
    selected_keyword = random.choice(keywords)
    print(f"\n[*] Algoritmayı ısıtmak için arama yapılıyor: '{selected_keyword}'...")
    
    search_url = f"https://www.tiktok.com/search?q={urllib.parse.quote(selected_keyword)}"
    try:
        safe_goto(page, search_url)
        time.sleep(5)
        
        # Click on the first video link in search results to open the video feed player
        first_video_link = page.query_selector('a[href*="/video/"]')
        if first_video_link:
            first_video_link.click()
            print("[*] Arama sonuçlarındaki ilk video açıldı. Isıtma etkileşimleri yapılıyor...")
            time.sleep(3)
            
            # Interact with 4 videos in search results to train algorithm
            for v_idx in range(4):
                watch_time = random.randint(12, 18)
                print(f"  -> Video #{v_idx+1} izleniyor ({watch_time} sn)...")
                time.sleep(watch_time)
                
                # Drop a like on the warm-up video (interact to train feed)
                try:
                    like_btn = page.query_selector('span[data-e2e="like-icon"]') or page.query_selector('button[class*="Like"]')
                    if like_btn:
                        like_btn.click()
                        print("  -> Beğenildi (Algoritma Beslendi)")
                except Exception:
                    pass
                    
                time.sleep(1)
                page.keyboard.press("ArrowDown") # Next search video
                time.sleep(2)
            print("[+] Aktif algoritma ısıtma aşaması tamamlandı! Organik For You akışına geçiliyor...")
        else:
            print("[-] Arama sonuçlarında video bulunamadı.")
    except Exception as e:
        print(f"[-] Isıtma aşamasında hata oluştu: {e}")

def run_burner_automation(api_key, duration_minutes=30):
    from playwright.sync_api import sync_playwright
    
    seen_videos = load_seen_videos()
    print(f"[*] Loaded {len(seen_videos)} seen videos.")
    print(f"[*] Launching TikTok Burner automation (Target Duration: {duration_minutes} minutes)...")

    # Read optional proxy environment variable
    proxy_server = os.environ.get("TIKTOK_PROXY")
    proxy_args = {}
    if proxy_server:
        print(f"[*] Proxy routing enabled: {proxy_server}")
        proxy_args["proxy"] = {"server": proxy_server}

    # Start Playwright chromium
    with sync_playwright() as playwright_instance:
        # Launch browser. Run headless in cloud, otherwise detect based on cookies
        headless_mode = os.environ.get("GITHUB_ACTIONS") == "true" or os.path.exists(COOKIES_PATH)
        browser = playwright_instance.chromium.launch(
            headless=headless_mode,
            args=[
                "--mute-audio",
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--disable-infobars"
            ],
            **proxy_args
        )
        
        # Define desktop agent
        user_agent = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        
        # Load context
        if os.path.exists(COOKIES_PATH):
            print("[*] Stored TikTok cookies found. Loading session context...")
            with open(COOKIES_PATH, "r") as f:
                cookies = json.load(f)
            context = browser.new_context(
                user_agent=user_agent,
                viewport={"width": 1280, "height": 720},
                device_scale_factor=1,
                **proxy_args
            )
            context.add_cookies(cookies)
        else:
            print("[!] TikTok cookies not found! Opening browser for manual login...")
            context = browser.new_context(
                user_agent=user_agent,
                viewport={"width": 1280, "height": 720},
                device_scale_factor=1,
                **proxy_args
            )
        
        page = context.new_page()
        
        # Inject Javascript to bypass navigator.webdriver bot check
        page.add_init_script("delete navigator.__proto__.webdriver")
        
        safe_goto(page, "https://www.tiktok.com/foryou")

        # Handle login if cookies were missing
        if not os.path.exists(COOKIES_PATH):
            print("[!] TikTok oturum çerezleri bulunamadı. Lütfen açılan tarayıcı penceresinden hesabınıza giriş yapın.")
            print("[*] QR kod okutarak veya normal girişle (gerekirse yapbozu çözerek) giriş yapabilirsiniz.")
            safe_goto(page, "https://www.tiktok.com/login")
            
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
                safe_goto(page, "https://www.tiktok.com/foryou")
            else:
                print("[-] Giriş zaman aşımına uğradı. Lütfen scripti tekrar çalıştırıp giriş yapın.")
                browser.close()
                return

        # Active Algorithm Warming Phase (Algoritmayı Isıtma Aşaması)
        # Search targeted keywords and like content to feed the recommendation engine
        run_warmup_search(page)
        
        # Navigate to For You Page to scan organically warmed feed
        print("\n[*] Organik Sizin İçin (For You) akışına bağlanılıyor...")
        safe_goto(page, "https://www.tiktok.com/foryou")
        time.sleep(5)

        # Start scraping loop
        start_time = time.time()
        end_time = start_time + (duration_minutes * 60)
        
        video_count = 0
        validated_count = 0
        consecutive_duplicates = 0
        last_seen_video_id = None
        
        while time.time() < end_time:
            time.sleep(3) # Wait for page load / transition
            
            # Extract video details
            try:
                # Get current video element or URL
                current_url = page.url
                video_id = None
                
                # Wait up to 3 seconds for the URL or DOM to settle
                for _ in range(3):
                    match = re.search(r"/video/(\d+)", page.url)
                    if match:
                        video_id = match.group(1)
                        current_url = page.url
                        break
                    active_link = page.query_selector('a[href*="/video/"]')
                    if active_link:
                        href = active_link.get_attribute("href")
                        match = re.search(r"/video/(\d+)", href)
                        if match:
                            video_id = match.group(1)
                            current_url = href
                            break
                    time.sleep(1)

                # Extract author username from DOM profile links
                author = "Bilinmeyen Kullanıcı"
                profile_link = page.query_selector('a[href*="/@"]')
                if profile_link:
                    href = profile_link.get_attribute("href")
                    match = re.search(r"/@([^/?#\s]+)", href)
                    if match:
                        author = match.group(1)
                else:
                    author_el = page.query_selector('span[data-e2e="browse-username"]') or page.query_selector('h3[data-e2e="video-author-uniqueid"]')
                    if author_el:
                        author = author_el.inner_text().strip()

                # Extract caption
                caption = "Ürün Açıklaması Alınamadı"
                caption_el = page.query_selector('h1[data-e2e="browse-video-desc"]') or page.query_selector('div[data-e2e="video-desc"]') or page.query_selector('[class*="Desc"]') or page.query_selector('[class*="desc"]')
                if caption_el:
                    caption = caption_el.inner_text().strip()

                # Fallback video_id to avoid infinite loading loops
                if not video_id:
                    if author != "Bilinmeyen Kullanıcı" or caption != "Ürün Açıklaması Alınamadı":
                        clean_cap = re.sub(r'[^a-zA-Z0-9]', '', caption[:20])
                        video_id = f"hash_{author}_{clean_cap}"
                    else:
                        video_id = f"fallback_{int(time.time())}"
                # Check for duplicates
                if video_id in seen_videos:
                    print(f"[*] Skipping duplicate video: {video_id}")
                    
                    if video_id == last_seen_video_id:
                        consecutive_duplicates += 1
                    else:
                        last_seen_video_id = video_id
                        consecutive_duplicates = 1
                        
                    if consecutive_duplicates >= 10:
                        print(f"[!] Stuck detected on video {video_id} (consecutive skips: {consecutive_duplicates}). Attempting to recover...")
                        consecutive_duplicates = 0
                        try:
                            # Reload page and navigate to /foryou to force load a scrollable feed
                            page.reload()
                            time.sleep(12)
                            safe_goto(page, "https://www.tiktok.com/foryou")
                            time.sleep(8)
                        except Exception as re_err:
                            print(f"[-] Recovery reload failed: {re_err}")
                            
                    # Simulate humanlike quick evaluation before swiping (1 to 2 seconds)
                    import random
                    time.sleep(random.uniform(1.0, 2.5))
                    page.keyboard.press("ArrowDown")
                    continue
                else:
                    consecutive_duplicates = 0
                    last_seen_video_id = None
                
                seen_videos.add(video_id)
                save_seen_videos(seen_videos)
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
                            
                    # Capture screenshot of the video frame
                    screenshot_img = capture_video_screenshot(page, video_id)

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
                        "image_url": screenshot_img
                    })
                else:
                    # Swipe immediately with a tiny humanlike pause (1-2 seconds)
                    print("[-] Not a winner candidate. Swiping next.")
                    import random
                    time.sleep(random.uniform(1.0, 2.0))
                    
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
