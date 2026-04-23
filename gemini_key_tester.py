import json
import requests

def test_and_fetch_models(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"خطأ: الملف '{file_path}' غير موجود.")
        return

    accounts = data.get("accounts", [])
    
    for acc in accounts:
        api_key = acc.get("api_key")
        name = acc.get("name")
        gmail = acc.get("gmail")
        
        print(f"\n{'='*60}")
        print(f"🔍 Testing Account: {name} ({gmail})")
        print(f"{'='*60}")

        if not api_key:
            print("❌ No API key found for this account.")
            continue

        # طلب قائمة الموديلات المتاحة
        url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
        
        try:
            response = requests.get(url)
            
            if response.status_code == 200:
                acc["enabled"] = True
                models_data = response.json()
                available_models = [m["name"].split("/")[-1] for m in models_data.get("models", [])]
                
                print(f"✅ Status: Active")
                print(f"📦 Available Models: {', '.join(available_models[:5])}...") # عرض أول 5 موديلات كمثال
                
                # توضيح بخصوص التوكنز
                print(f"📊 Quota Info: Daily limit is {acc.get('daily_limit')} requests.")
                print(f"💡 Note: Remaining tokens are not provided via API. Check AI Studio for exact numbers.")
                
            elif response.status_code == 429:
                print(f"❌ Status: Exhausted (Quota Exceeded)")
                print(f"⚠️  You have reached the daily limit for this key.")
                acc["enabled"] = False
            else:
                print(f"⚠️ Status: Error {response.status_code}")
                print(f"Details: {response.text}")
                acc["enabled"] = False
                
        except Exception as e:
            print(f"❗ Connection Error: {str(e)}")

    # حفظ التعديلات
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)
    
    print(f"\n{'*'*60}")
    print(f"Done! Results saved to {file_path}")

test_and_fetch_models('gemini_config.json')