import json
import os
import sys

def load_json(path):
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"[-] Error loading {path}: {e}")
    return []

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--local-seen', default='seen_tiktok_videos.json')
    parser.add_argument('--local-products', default='precrawled_products.json')
    parser.add_argument('--remote-seen-ref', default='origin/main:seen_tiktok_videos.json')
    parser.add_argument('--remote-products-ref', default='origin/main:precrawled_products.json')
    args = parser.parse_args()

    # 1. Read local modified databases
    local_seen = load_json(args.local_seen)
    local_products = load_json(args.local_products)

    # 2. Fetch remote databases from origin/main
    import subprocess
    
    remote_seen = []
    try:
        res = subprocess.run(['git', 'show', args.remote_seen_ref], capture_output=True, text=True, check=True)
        remote_seen = json.loads(res.stdout)
    except Exception as e:
        print(f"[*] Could not load remote seen file (might be first run): {e}")

    remote_products = []
    try:
        res = subprocess.run(['git', 'show', args.remote_products_ref], capture_output=True, text=True, check=True)
        remote_products = json.loads(res.stdout)
    except Exception as e:
        print(f"[*] Could not load remote products file: {e}")

    # 3. Merge seen videos (lists of strings)
    merged_seen = list(set((local_seen if isinstance(local_seen, list) else []) + 
                           (remote_seen if isinstance(remote_seen, list) else [])))

    # 4. Merge products (lists of dicts, match by name case-insensitive)
    merged_products = list(remote_products) if isinstance(remote_products, list) else []
    existing_names = {p.get('name', '').lower().strip() for p in merged_products if 'name' in p}

    if isinstance(local_products, list):
        for p in local_products:
            name = p.get('name', '').lower().strip()
            if not name:
                continue
            if name in existing_names:
                # Update existing product with local version
                for idx, r_prod in enumerate(merged_products):
                    if r_prod.get('name', '').lower().strip() == name:
                        merged_products[idx] = p
                        break
            else:
                merged_products.append(p)
                existing_names.add(name)

    # 5. Save merged databases to temp files
    os.makedirs('/tmp/ecomflow_merge', exist_ok=True)
    
    with open('/tmp/ecomflow_merge/seen_tiktok_videos.json', 'w', encoding='utf-8') as f:
        json.dump(merged_seen, f, indent=2, ensure_ascii=False)
        
    with open('/tmp/ecomflow_merge/precrawled_products.json', 'w', encoding='utf-8') as f:
        json.dump(merged_products, f, indent=2, ensure_ascii=False)

    print("[+] Successfully merged databases. Temp files written to /tmp/ecomflow_merge/")

if __name__ == '__main__':
    main()
