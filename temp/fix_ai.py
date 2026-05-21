import sys
import os

with open('main.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Replace analyze_with_ai with the stable REST API version
new_ai = '''def analyze_with_ai(input_text: str, mode: str = 'extract', boat_name: str = "مركب غير مسمى"):
    """Uses Gemini to extract invoice data or chat. Returns dict or string."""
    if mode == 'text_intent':
        text_lower = input_text.lower()
        num = _extract_amount(input_text)
        if 'بنزين' in text_lower or 'سولار' in text_lower or 'جاز' in text_lower:
            return {"action": "expense", "amount": num, "category": "بنزين"}
        if 'ماركت' in text_lower or 'أكل' in text_lower or 'شرب' in text_lower:
            return {"action": "expense", "amount": num, "category": "ماركت"}

    try:
        gemini_key = os.getenv("GEMINI_API_KEY")
        if not gemini_key:
            raise ValueError("GEMINI_API_KEY missing")

        if mode in ['extract', 'retry_extract', 'total_only', 'full_storage', 'text_intent']:
            if mode == 'text_intent':
                prompt = (f"Extract price and category from this Arabic text. "
                          f"Categories: [بنزين,صيانة,ماركت,إكرامية,أدوات نظافة,عام]. "
                          f"Return ONLY JSON: {{\\"action\\":\\"expense\\",\\"amount\\":float,\\"category\\":\\"string\\"}}. "
                          f"Text: {input_text}")
            else:
                extra = "\\nWARNING: Look closer, find every item.\\n" if mode == 'retry_extract' else ""
                mode_desc = ("Return JSON with store, date, total only." if mode == 'total_only'
                             else "Return full JSON with all items, prices, total.")
                prompt = (f"{extra}You are an Arabic invoice OCR analyst. {mode_desc}\\n"
                          f"JSON format: {{\\"mode\\":\\"total/full\\",\\"store\\":\\"str\\",\\"date\\":\\"YYYY-MM-DD\\","
                          f"\\"total\\":float,\\"items\\":[{{\\"name\\":\\"str\\",\\"price\\":float,\\"qty\\":int}}]}}\\n"
                          f"Return ONLY valid JSON. Input:\\n{input_text}")
            system = f"أنت محاسب AbsyCode لمركب '{boat_name}'. أجب بـ JSON فقط."
        else:
            prompt = input_text
            system = (f"You are AbsyCode Assistant for boat '{boat_name}'. "
                      f"Speak in friendly Egyptian Arabic. Be concise.")

        url = f"https://generativelanguage.googleapis.com/v1/models/gemini-2.5-flash:generateContent?key={gemini_key}"
        payload = {
            "contents": [{"parts": [{"text": f"{system}\\n\\n{prompt}"}]}]
        }
        
        response_text = None
        resp = requests.post(url, json=payload, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            if "candidates" in data and len(data["candidates"]) > 0:
                response_text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
        else:
            logging.warning(f"Gemini API returned {resp.status_code}: {resp.text}")

        if not response_text:
            return None
            
        content = response_text
'''

import re
content = re.sub(
    r'def analyze_with_ai\(input_text: str.*?return content\n', 
    new_ai, 
    content, 
    flags=re.DOTALL
)

# 2. Update handle_weather to use Gemini formatting
new_weather = '''@dp.message(F.text == "🌤️ حالة البحر")
async def handle_weather(message: Message):
    user_data = await database.get_user(message.from_user.id)
    boat_name = user_data[2] if user_data and user_data[2] else "مركب غير مسمى"
    wait_msg  = await message.answer("جاري استطلاع حالة البحر... 🔭")
    lat, lon  = 27.25, 33.81
    api_key   = os.getenv("OPENWEATHER_API_KEY", "")
    try:
        url  = (f"https://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}"
                f"&appid={api_key}&units=metric&lang=ar")
        data = requests.get(url, timeout=5).json()
        temp       = data['main']['temp']
        wind_knots = data['wind']['speed'] * 1.94384
        desc       = data['weather'][0]['description']
        suitability = ("البحر هادي ومثالي للرحلات 🛥️✨" if wind_knots < 10
                       else "جو مناسب للإبحار 🌊" if wind_knots < 20
                       else "الرياح قوية، احتاط يا ريس ⚠️")
                       
        raw_text = (f"☀️ تقرير البحر — {boat_name}\\n\\n"
                    f"🌡️ {temp:.1f}°C  |  🌬️ {wind_knots:.1f} عقدة\\n"
                    f"☁️ {desc}\\n\\n💎 {suitability}")
                    
        # AI Formatting
        final_text = raw_text
        try:
            gemini_key = os.getenv("GEMINI_API_KEY")
            if gemini_key:
                ai_url = f"https://generativelanguage.googleapis.com/v1/models/gemini-2.5-flash:generateContent?key={gemini_key}"
                prompt = f"قم بصياغة تقرير الطقس هذا بأسلوب بحري مصري ودود ومختصر للقبطان:\\n{raw_text}"
                payload = {"contents": [{"parts": [{"text": prompt}]}]}
                resp = requests.post(ai_url, json=payload, timeout=8)
                if resp.status_code == 200:
                    ai_data = resp.json()
                    if "candidates" in ai_data and len(ai_data["candidates"]) > 0:
                        final_text = ai_data["candidates"][0]["content"]["parts"][0]["text"].strip()
        except Exception as ai_err:
            logging.warning(f"Gemini weather summary failed: {ai_err}")

        await wait_msg.edit_text(final_text)
    except Exception as e:
        logging.error(f"Weather error: {e}")
        await wait_msg.edit_text("مش قادر أوصل لبيانات الطقس حالياً. 😅")
'''

content = re.sub(
    r'@dp\.message\(F\.text == "🌤️ حالة البحر"\)\nasync def handle_weather\(message: Message\):.*?await wait_msg\.edit_text\("مش قادر أوصل لبيانات الطقس حالياً\. 😅"\)\n',
    new_weather,
    content,
    flags=re.DOTALL
)

with open('main.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("AI logic updated")
