PR-01 (Run analysis now + Telegram alerts + UI buttons)

الملفات ضمن هذا الأرشيف هي "استبدال مباشر" للملفات في مشروعك:
- gateway/requirements.txt
- gateway/main.py
- analysis/requirements.txt
- analysis/app.py
- frontend/src/main.tsx

طريقة الدمج (الأسهل):
1) فك الضغط وانسخ الملفات فوق مشروعك (استبدال).
2) حدّث .env بمفاتيح TELEGRAM_BOT_TOKEN و TELEGRAM_CHAT_ID (إن أردت تنبيهات).
3) شغّل:
   docker compose build gateway analysis frontend
   docker compose up -d

اختبار:
- http://localhost:8000/telegram/test  (أو زر "اختبار تيليغرام" في الواجهة)
- زر "تحديث المؤشرات الآن" من الواجهة.

بديل (Git):
  git checkout -b feature/telegram-run-now
  انسخ الملفات المستبدلة ثم:
  git add -A
  git commit -m "PR-01: run-analysis endpoint + Telegram alerts + UI buttons"
  git push -u origin feature/telegram-run-now
  افتح Pull Request من GitHub.
