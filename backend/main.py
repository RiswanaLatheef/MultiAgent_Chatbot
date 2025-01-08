from fastapi import FastAPI
from groq import Groq
from config import settings


app=FastAPI(title="ZiaBot")
client=Groq(api_key=settings.groq_api_key)
chat_history=[]
system_message={"role":"system","content":"you are helpful assistant to help in the queries about data science"}
chat_history.append(system_message)

@app.get("/")
def index():
    return{"ErrorCode":0,"Data":{},"message":"sucessful"}

@app.get("/query")
def query(q:str):
    user_message = {"role":"user","content":q}
    chat_history.append(user_message)
    chat_completion=client.chat.completions.create(messages=chat_history,model="llama-3.3-70b-versatile",max_tokens=1024,stream=False)
    answer=chat_completion.choices[0].message.content
    if answer:
        chat_history.append({"role":"assistant","content":answer})
        return {'ErrorCode':0,"Data":answer,"Message":"Success"}
    else:
        return{"ErrorCode":1,"Data":"try some time later","Mesaage":"Failure"}