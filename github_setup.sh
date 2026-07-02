#!/bin/bash
echo "⚡ EcomFlow Portal - GitHub Otomasyon Kurulum Yardımcısı ⚡"
echo "--------------------------------------------------------"
echo "Lütfen önce GitHub.com'a girip yeni bir 'Public' repo oluşturun."
echo "Ardından oluşturduğunuz reponun URL'sini girin (örn: https://github.com/kullanici/repo-adi.git):"
read repo_url
if [ -z "$repo_url" ]; then
  echo "Hata: Repo URL'si boş olamaz!"
  exit 1
fi

git remote remove origin 2>/dev/null
git remote add origin "$repo_url"
echo "Kodlar bulut deposuna yükleniyor (Push)..."
git push -u origin main

echo "--------------------------------------------------------"
echo "🚀 Başarıyla GitHub'a yüklendi!"
echo "Şimdi GitHub deponuzun 'Settings -> Secrets' kısmına gidip GEMINI_API_KEY secret'ını eklemeyi unutmayın!"
