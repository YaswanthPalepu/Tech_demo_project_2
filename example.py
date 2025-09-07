import os
from openai import AzureOpenAI

endpoint = "https://devi-mezccwde-eastus2.cognitiveservices.azure.com/"
model_name = "gpt-5-nano"
deployment = "prasad8792"

subscription_key = "6WgLy2fILHX5917LTIALD7dFdeg4M8o3RtWPI3GPpwwWTMi0E7HfJQQJ99BHACHYHv6XJ3w3AAAAACOGrkxK"
api_version = "2024-12-01-preview"

client = AzureOpenAI(
    api_version=api_version,
    azure_endpoint=endpoint,
    api_key=subscription_key,
)

response = client.chat.completions.create(
    messages=[
        {
            "role": "system",
            "content": "You are a helpful assistant.",
        },
        {
            "role": "user",
            "content": "I am going to Paris, what should I see?",
        }
    ],
    max_completion_tokens=16384,
    model=deployment
)

print(response.choices[0].message.content)