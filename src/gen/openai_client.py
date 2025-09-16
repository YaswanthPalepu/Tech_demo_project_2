from typing import List, Dict
from openai import AzureOpenAI, RateLimitError
from .env import get_any_env

def client() -> AzureOpenAI:
    return AzureOpenAI(
        api_key=get_any_env("AZURE_OPENAI_KEY", "AZURE_OPENAI_API_KEY"),
        azure_endpoint=get_any_env("AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_API_ENDPOINT"),
        api_version=get_any_env("AZURE_OPENAI_API_VERSION", "OPENAI_API_VERSION"),
    )

def deployment_name() -> str:
    return get_any_env("AZURE_OPENAI_DEPLOYMENT", "OPENAI_DEPLOYMENT")

def chat_completion_create(cli: AzureOpenAI, deployment: str, messages: List[Dict[str,str]]):
    return cli.chat.completions.create(model=deployment, messages=messages)

RateLimitError = RateLimitError
