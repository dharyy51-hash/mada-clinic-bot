# تشغيل البوت — خطوات بسيطة

## 1. احصل على Claude API Key
- روح: https://console.anthropic.com
- سجل حساب مجاني
- من القائمة: API Keys ← Create Key
- انسخ الـ key

## 2. حضّر الملفات
```
انسخ ملف .env.example وسمّه .env
افتحه وحط الـ key:
ANTHROPIC_API_KEY=sk-ant-...الكود هنا...
```

## 3. ثبّت المتطلبات
```bash
pip install -r requirements.txt
```

## 4. شغّل البوت
```bash
python app.py
```

## 5. افتح المتصفح
```
http://localhost:5000
```

## تخصيص العيادة
افتح bot.py وعدّل DEFAULT_CLINIC:
- clinic_name: اسم العيادة
- specialty: التخصص
- hours: أوقات الدوام
- location: الموقع
- prices: الأسعار

## ربط الواتساب (لاحقاً)
- سجّل في twilio.com
- شغّل ngrok لتوجيه الـ webhook
- حط رابط: https://رابطك.ngrok.io/webhook/whatsapp
