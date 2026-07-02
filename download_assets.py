import json
import os
import re
import urllib.request
import urllib.parse
import hashlib

data_js_path = "/Users/melihakkali/Desktop/Organik_Celik_Videolari/data.js"
desktop_dir = "/Users/melihakkali/Desktop/Organik_Celik_Videolari"
images_dir = os.path.join(desktop_dir, "images")
files_dir = os.path.join(desktop_dir, "files")

os.makedirs(images_dir, exist_ok=True)
os.makedirs(files_dir, exist_ok=True)

def parse_data_js():
    if not os.path.exists(data_js_path):
        print("data.js not found!")
        return None
        
    with open(data_js_path, "r", encoding="utf-8") as f:
        content = f.read()
        
    json_str = content.replace("// Yerel veri tabanı\nconst portalData = ", "").strip()
    if json_str.endswith(";"):
        json_str = json_str[:-1].strip()
        
    try:
        return json.loads(json_str)
    except Exception as e:
        print(f"Error parsing data.js: {e}")
        return None

def write_data_js(items):
    with open(data_js_path, "w", encoding="utf-8") as f:
        f.write("// Yerel veri tabanı\n")
        f.write("const portalData = ")
        json.dump(items, f, indent=2, ensure_ascii=False)
        f.write(";\n")
    print(f"Updated data.js written to {data_js_path}")

def get_safe_filename(url, prefix="asset"):
    # Create a safe unique filename based on md5 hash
    parsed = urllib.parse.urlparse(url)
    ext = os.path.splitext(parsed.path)[1]
    if not ext:
        ext = ".png" # default for images
    # Limit extension length and remove queries
    ext = ext.split("?")[0]
    if len(ext) > 5 or not ext.startswith("."):
        ext = ".png"
        
    h = hashlib.md5(url.encode('utf-8')).hexdigest()
    return f"{prefix}_{h}{ext}"

def download_file(url, filepath):
    if os.path.exists(filepath) and os.path.getsize(filepath) > 0:
        return True # already downloaded
        
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as response, open(filepath, 'wb') as out_file:
            out_file.write(response.read())
        print(f"Downloaded: {url} -> {os.path.basename(filepath)}")
        return True
    except Exception as e:
        print(f"Failed to download {url}: {e}")
        return False

def run_download():
    items = parse_data_js()
    if not items:
        return
        
    print(f"Loaded {len(items)} items from data.js. Scanning for assets...")
    
    total_images = 0
    downloaded_images = 0
    total_attachments = 0
    downloaded_attachments = 0
    
    for item in items:
        body = item.get("bodyHtml", "")
        # Find all image URLs (src="...")
        img_urls = re.findall(r'src="([^"]+)"', body)
        
        # We filter out local assets or external tracker pixels
        valid_img_urls = [u for u in img_urls if "http" in u and "stripe.com" not in u and "recaptcha" not in u]
        
        if valid_img_urls:
            new_body = body
            for url in valid_img_urls:
                filename = get_safe_filename(url, "img")
                filepath = os.path.join(images_dir, filename)
                
                total_images += 1
                if download_file(url, filepath):
                    downloaded_images += 1
                    # Replace with relative path in bodyHtml
                    new_body = new_body.replace(url, f"images/{filename}")
            item["bodyHtml"] = new_body
            
        # Find all attachments
        attachments = item.get("attachments", [])
        if attachments:
            for att in attachments:
                url = att.get("url")
                if url and "http" in url:
                    filename = get_safe_filename(url, "file")
                    filepath = os.path.join(files_dir, filename)
                    
                    total_attachments += 1
                    if download_file(url, filepath):
                        downloaded_attachments += 1
                        # Replace with relative path in attachments
                        att["url"] = f"files/{filename}"
                        
    print(f"\n--- ASSETS SYNCHRONIZATION REPORT ---")
    print(f"Images: Found {total_images}, Downloaded {downloaded_images}")
    print(f"Attachments: Found {total_attachments}, Downloaded {downloaded_attachments}")
    
    # Save back
    write_data_js(items)
    
if __name__ == "__main__":
    run_download()
