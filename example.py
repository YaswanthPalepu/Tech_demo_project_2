# test_azure.py - Run this first
from openai import AzureOpenAI

client = AzureOpenAI(
    api_key="HrdzfDsLw8SZ2gOKtXaXxCtpJ3jtXogSJvFcOw21B2p4mKZO8MeBJQQJ99BIACYeBjFXJ3w3AAABACOGp11U",
    azure_endpoint="https://prasadopenai.openai.azure.com/",
    api_version="2024-02-15-preview"
)

response = client.chat.completions.create(
    model="gpt-5-mini",
    messages=[{"role": "user", "content": "Say 'hello'"}]
)

print("Response:", response.choices[0].message.content)
print("Full response:", response)