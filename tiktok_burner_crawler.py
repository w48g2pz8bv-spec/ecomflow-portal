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

def call_vertex_gemini(json_path, prompt, model="gemini-3.5-flash"):
    try:
        import urllib.request
        import json
        from google.oauth2 import service_account
        import google.auth.transport.requests
        
        credentials = service_account.Credentials.from_service_account_file(
            json_path,
            scopes=['https://www.googleapis.com/auth/cloud-platform']
        )
        request = google.auth.transport.requests.Request()
        credentials.refresh(request)
        token = credentials.token
        project_id = credentials.project_id
        
        # Map model name to actual production Vertex AI model ID
        vertex_model = model
        if "3.5-flash" in model or "3.5" in model:
            vertex_model = "gemini-1.5-flash-002"  # Safest globally-supported model on Vertex
            
        region = "us-central1"
        url = f"https://{region}-aiplatform.googleapis.com/v1/projects/{project_id}/locations/{region}/publishers/google/models/{vertex_model}:generateContent"
        
        payload = {
            "contents": [{
                "parts": [{"text": prompt}]
            }]
        }
        
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {token}"
            }
        )
        
        import urllib.error
        retries = 3
        delay = 6
        for attempt in range(retries):
            try:
                with urllib.request.urlopen(req, timeout=60) as response:
                    return json.loads(response.read().decode("utf-8"))
            except urllib.error.HTTPError as e:
                if e.code == 429:
                    print(f"[-] Vertex AI API Rate Limit (429) encountered. Retrying in {delay} seconds...")
                    time.sleep(delay)
                    delay *= 2
                else:
                    print(f"[-] Vertex HTTP Error {e.code}: {e.reason}")
                    break
            except Exception as e:
                print(f"[-] Vertex API call failed: {e}")
                break
    except Exception as e:
        print(f"[-] Vertex Auth failed: {e}")
    return None

def call_gemini(api_key, prompt, model="gemini-3.5-flash", use_grounding=False):
    # Check if Vertex AI service account credentials exist in workspace
    key_path = os.path.join(BASE_DIR, "ecomflow_key.json")
    if os.path.exists(key_path):
        print(f"[*] GCP Service Account key found. Routing request to Vertex AI ({model})...")
        return call_vertex_gemini(key_path, prompt, model)

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
    hashtags = [
        "tiktokmademebuyit", 
        "amazonfinds", 
        "dropshipping", 
        "viralproduct"
    ]
    selected_hashtag = random.choice(hashtags)
    print(f"\n[*] Algoritmayı ısıtmak için doğrudan hashtag sayfasına yönlendiriliyor: '#{selected_hashtag}'...")
    
    tag_url = f"https://www.tiktok.com/tag/{selected_hashtag}"
    try:
        safe_goto(page, tag_url)
        time.sleep(6)
        
        # Click on the first video link in tag grid to open theater mode player
        first_video_link = page.query_selector('a[href*="/video/"]')
        if first_video_link:
            first_video_link.click(force=True)
            print("[*] Etiket akışındaki ilk video açıldı. Isıtma etkileşimleri yapılıyor...")
            time.sleep(4)
            
            # Interact with 4 videos in tag stream to train algorithm feed
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
                page.keyboard.press("ArrowDown") # Next video
                time.sleep(2.5)
            print("[+] Aktif algoritma ısıtma aşaması başarıyla tamamlandı! Organik For You akışına geçiliyor...")
        else:
            print("[-] Etiket akışında video bulunamadı.")
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
        
        # Capture login/profile check screenshot to verify if we are correctly logged in
        try:
            print("[*] Oturum durumunu doğrulamak için profil ekran görüntüsü alınıyor...")
            time.sleep(8) # Wait for page load and session cookies to be applied
            os.makedirs(os.path.join(BASE_DIR, "product_images"), exist_ok=True)
            screenshot_path = os.path.join(BASE_DIR, "product_images", "profile_login_check.png")
            page.screenshot(path=screenshot_path)
            print(f"[+] Profil ekran görüntüsü kaydedildi: {screenshot_path}")
        except Exception as scr_err:
            print(f"[-] Profil ekran görüntüsü alınamadı: {scr_err}")

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

        # Read option for warming up mode (staying on hashtags instead of For You feed)
        warmup_only_mode = os.environ.get("WARMUP_ONLY_MODE", "true") == "true"
        hashtags = ["tiktokmademebuyit", "amazonfinds", "dropshipping", "viralproduct", "uniquefinds", "coolproducts", "homehacks", "gadgets"]
        current_tag_idx = 0

        if warmup_only_mode:
            selected_tag = hashtags[current_tag_idx]
            print(f"\n[*] UYARI: Algoritma Isıtma Modu (Hashtag Taraması) Aktif!")
            print(f"[*] Doğrudan #{selected_tag} etiket akışına bağlanılıyor...")
            safe_goto(page, f"https://www.tiktok.com/tag/{selected_tag}")
            time.sleep(6)
            
            # Scroll down the grid page first to load more videos and prevent duplicates
            print("[*] Izgaradaki videoları çeşitlendirmek için aşağı kaydırılıyor...")
            for _ in range(4):
                page.evaluate("window.scrollBy(0, 1000)")
                time.sleep(1.5)
            
            # Extract and select the first unseen video link
            video_links = page.query_selector_all('a[href*="/video/"]')
            unseen_video = None
            for link in video_links:
                href = link.get_attribute("href")
                if href:
                    v_match = re.search(r"/video/(\d+)", href)
                    if v_match:
                        v_id = v_match.group(1)
                        if v_id not in seen_videos:
                            unseen_video = link
                            break
            
            if unseen_video:
                print("[+] Izgarada daha önce taranmamış yeni video bulundu. Tıklanarak açılıyor...")
                unseen_video.click(force=True)
                time.sleep(4)
            else:
                print("[-] Izgaradaki tüm videolar daha önce taranmış. İlk video tıklanıyor...")
                first_video = page.query_selector('a[href*="/video/"]')
                if first_video:
                    first_video.click(force=True)
                    time.sleep(4)
                else:
                    print("[-] Etiket sayfasında hiç video bulunamadı. For You akışına geçiliyor...")
                    safe_goto(page, "https://www.tiktok.com/foryou")
                    time.sleep(5)
        else:
            # Active Algorithm Warming Phase (Algoritmayı Isıtma Aşaması)
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
        last_switched_count = 0
        
        while time.time() < end_time:
            # Switch hashtag feed periodically in warmup mode to diversify products (every 12 evaluated videos)
            if warmup_only_mode and video_count > 0 and video_count % 12 == 0 and video_count != last_switched_count:
                last_switched_count = video_count
                current_tag_idx = (current_tag_idx + 1) % len(hashtags)
                selected_tag = hashtags[current_tag_idx]
                print(f"\n[*] Algoritma Isıtması: Yeni kategoriye geçiş yapılıyor: #{selected_tag}...")
                try:
                    safe_goto(page, f"https://www.tiktok.com/tag/{selected_tag}")
                    time.sleep(6)
                    first_video = page.query_selector('a[href*="/video/"]')
                    if first_video:
                        first_video.click(force=True)
                        time.sleep(4)
                except Exception as switch_err:
                    print(f"[-] Hashtag geçiş hatası: {switch_err}")

            time.sleep(3) # Wait for page load / transition
            
            # Extract video details using active viewport element evaluation
            try:
                active_info = page.evaluate("""() => {
                    const videos = document.querySelectorAll('video');
                    let activeVideo = null;
                    let minDiff = Infinity;
                    const viewportCenter = window.innerHeight / 2;
                    
                    for (const v of videos) {
                        const rect = v.getBoundingClientRect();
                        if (rect.height > 0 && rect.width > 0) {
                            const center = rect.top + rect.height / 2;
                            const diff = Math.abs(center - viewportCenter);
                            if (diff < minDiff) {
                                minDiff = diff;
                                activeVideo = v;
                            }
                        }
                    }
                    
                    if (!activeVideo) return null;
                    
                    // Traverse up to find container with author and caption info
                    let c = activeVideo.parentElement;
                    let authorEl = null;
                    let captionEl = null;
                    let videoLinkEl = null;
                    
                    for (let i = 0; i < 15; i++) {
                        if (!c) break;
                        authorEl = c.querySelector('a[href*="/@"], [data-e2e="video-author-uniqueid"], [data-e2e="video-user-name"], [class*="UniqueId"], [class*="username"]');
                        captionEl = c.querySelector('[data-e2e="video-desc"], [data-e2e="feed-video-desc"], [class*="DivDesc"], [class*="desc"], h1[data-e2e="browse-video-desc"]');
                        videoLinkEl = c.querySelector('a[href*="/video/"]');
                        if (authorEl || captionEl) {
                            break;
                        }
                        c = c.parentElement;
                    }
                    
                    let author = "Bilinmeyen Kullanıcı";
                    if (authorEl) {
                        const href = authorEl.getAttribute('href');
                        if (href) {
                            const m = href.match(/\/@([^/?#\\s]+)/);
                            if (m) author = m[1];
                        } else {
                            author = authorEl.innerText.trim();
                        }
                    }
                    
                    const caption = captionEl ? captionEl.innerText.trim() : "Ürün Açıklaması Alınamadı";
                    let videoUrl = videoLinkEl ? videoLinkEl.getAttribute('href') : "";
                    let videoId = "";
                    if (videoUrl) {
                        const m = videoUrl.match(/\/video\/(\\d+)/);
                        if (m) videoId = m[1];
                    }
                    
                    return { author, caption, videoUrl, videoId };
                }""")
                
                if active_info:
                    author = active_info.get("author") or "Bilinmeyen Kullanıcı"
                    caption = active_info.get("caption") or "Ürün Açıklaması Alınamadı"
                    current_url = active_info.get("videoUrl") or page.url
                    video_id = active_info.get("videoId")
                else:
                    author = "Bilinmeyen Kullanıcı"
                    caption = "Ürün Açıklaması Alınamadı"
                    current_url = page.url
                    video_id = None
                
                # Fallback video_id to avoid infinite loading loops
                if not video_id:
                    match = re.search(r"/video/(\d+)", page.url)
                    if match:
                        video_id = match.group(1)
                        current_url = page.url
                    else:
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
                        
                    # Swipe to next video
                    swipe_success = False
                    if warmup_only_mode:
                        # Try clicking the next video arrow button in the lightbox overlay
                        for sel in ['button[data-e2e="arrow-dest"]', 'button[data-e2e="video-page-next"]', 'button[aria-label="Next video"]', 'button[class*="ArrowDown"]', 'button[class*="arrow"]']:
                            try:
                                btn = page.query_selector(sel)
                                if btn and btn.is_visible():
                                    init_url = page.url
                                    btn.click(force=True)
                                    time.sleep(2)
                                    if page.url != init_url:
                                        swipe_success = True
                                        break
                            except Exception:
                                pass
                                
                    if not swipe_success:
                        page.keyboard.press("ArrowDown")
                        time.sleep(2.0)
                        
                    # If we are stuck on the exact same video ID (swipe did not work)
                    if consecutive_duplicates >= 12:
                        print(f"[!] Swiping stuck detected on duplicate video {video_id}. Attempting to reload tag grid...")
                        consecutive_duplicates = 0
                        try:
                            if warmup_only_mode:
                                # Switch to next tag or reload current tag page
                                current_tag_idx = (current_tag_idx + 1) % len(hashtags)
                                selected_tag = hashtags[current_tag_idx]
                                print(f"[*] Recovery: #{selected_tag} etiket sayfasına geri dönülüyor...")
                                safe_goto(page, f"https://www.tiktok.com/tag/{selected_tag}")
                                time.sleep(6)
                                # Scroll down further to fetch fresh content
                                scroll_amt = random.randint(3, 6)
                                print(f"[*] Scrolling down grid {scroll_amt} times to load more unseen videos...")
                                for _ in range(scroll_amt):
                                    page.evaluate("window.scrollBy(0, 1000)")
                                    time.sleep(1.5)
                                    
                                # Extract links and click first unseen
                                video_links = page.query_selector_all('a[href*="/video/"]')
                                clicked = False
                                for link in video_links:
                                    href = link.get_attribute("href")
                                    if href:
                                        v_m = re.search(r"/video/(\d+)", href)
                                        if v_m and v_m.group(1) not in seen_videos:
                                            print(f"[+] Clicked unseen video from grid: {v_m.group(1)}")
                                            link.click(force=True)
                                            # Wait up to 5 seconds for URL to transition to the clicked video
                                            for _ in range(5):
                                                if "/video/" in page.url:
                                                    break
                                                time.sleep(1)
                                            clicked = True
                                            break
                                if not clicked and video_links:
                                    # Fallback click first link
                                    video_links[0].click(force=True)
                                    # Wait for transition
                                    for _ in range(5):
                                        if "/video/" in page.url:
                                            break
                                        time.sleep(1)
                            else:
                                page.reload()
                                time.sleep(12)
                                safe_goto(page, "https://www.tiktok.com/foryou")
                                time.sleep(8)
                        except Exception as re_err:
                            print(f"[-] Recovery reload failed: {re_err}")
                            
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
                    # Swipe next
                    print("[-] Not a winner candidate. Swiping next.")
                    import random
                    if warmup_only_mode:
                        # Since we are on dropshipping hashtag feeds, we watch longer to train the TikTok algorithm
                        watch_time = random.uniform(8.0, 14.0)
                        print(f"[*] Algoritma Eğitimi: Dropshipping videosu {watch_time:.1f} saniye izleniyor...")
                        time.sleep(watch_time)
                        # 20% chance to drop a like to further train the feed recommendation engine
                        if random.random() < 0.20:
                            try:
                                like_btn = page.query_selector('span[data-e2e="like-icon"]') or page.query_selector('button[class*="Like"]')
                                if like_btn:
                                    like_btn.click()
                                    print("[*] Algoritma Eğitimi: Etiket videosu beğeni ile beslendi.")
                            except Exception:
                                pass
                    else:
                        # On organic feed, swipe fast to hide irrelevant content (dances, memes, news)
                        time.sleep(random.uniform(1.0, 2.5))
                    
            except Exception as e:
                print(f"[-] Error processing current video element: {e}")
            
            # Swipe down to next video
            page.keyboard.press("ArrowDown")
            time.sleep(3.0)
            
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
