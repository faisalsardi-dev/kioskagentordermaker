import os
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

load_dotenv("kisoskagentapi.env")

llm = ChatOpenAI(
    api_key=os.getenv("kioskagentapikey"),
    base_url="https://api.groq.com/openai/v1",
    model="llama-3.3-70b-versatile",
)