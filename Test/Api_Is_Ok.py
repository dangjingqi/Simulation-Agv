import requests
import json

API_KEY = "sk-fda2bbcbbd444ac083ce27678e78c097"  # 替换成真实的

# 如果用硅基流动
#url = "https://api.siliconflow.cn/v1/chat/completions"
#model = "Qwen/Qwen2-7B-Instruct"

# 如果用 DeepSeek
url = "https://api.deepseek.com/v1/chat/completions"
model = "deepseek-chat"

headers = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json"
}

payload = {
    "model": model,
    "messages": [{"role": "user", "content": "你好"}]
}

response = requests.post(url, headers=headers, json=payload)
print("状态码:", response.status_code)
print("返回:", json.dumps(response.json(), indent=2, ensure_ascii=False))