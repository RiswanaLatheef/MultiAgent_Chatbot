from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import Session, select
from database import engine, User, ChatSession, ChatMessage, UserFiles, create_db_and_tables
from datetime import datetime
from typing import Optional, Dict
from pydantic import BaseModel
import logging
import PyPDF2
from crewai import Agent, Task, Crew, Process
from config import settings
import litellm

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="MultiAgentChatbot")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize database
create_db_and_tables()
logger.info("Database tables initialized.")

# Set up LiteLLM API key
litellm.api_key = settings.GROQ_API_KEY

def get_db():
    with Session(engine) as session:
        yield session

def authenticate_user(db: Session, username: str, password: str):
    all_users = db.exec(select(User)).all()
    logger.info(f"All users in DB: {[(u.username, u.hashed_password, u.id) for u in all_users]}")
    
    user = db.exec(select(User).where(User.username == username)).first()
    if not user or user.hashed_password != password:
        logger.warning(f"Authentication failed for {username}")
        return None
    logger.info(f"Authenticated user: {username}, user_id: {user.id}")
    return user

class UserCreate(BaseModel):
    username: str
    email: str
    password: str

class UserRead(BaseModel):
    username: str
    email: str

class ChatRequest(BaseModel):
    message: str
    session_id: Optional[int] = None

def extract_file_content(file: UploadFile) -> str:
    try:
        if file.filename.endswith('.txt'):
            content = file.file.read().decode('utf-8')
            logger.info(f"Extracted TXT content for {file.filename}, length: {len(content)}")
            return content
        elif file.filename.endswith('.pdf'):
            pdf_reader = PyPDF2.PdfReader(file.file)
            text = "".join(page.extract_text() or "" for page in pdf_reader.pages).strip()
            logger.info(f"Extracted PDF content for {file.filename}, length: {len(text)}")
            return text
        else:
            raise HTTPException(status_code=400, detail="Unsupported file format. Please upload .txt or .pdf files.")
    except Exception as e:
        logger.error(f"Error extracting file content: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Error processing file: {str(e)}")

def is_file_relevant(query: str) -> bool:
    file_keywords = ["file", "document", "content", "uploaded", "pdf", "txt", "summarize", "describe"]
    query_lower = query.lower()
    return any(keyword in query_lower for keyword in file_keywords)

@app.post("/register", response_model=UserRead)
def register(user: UserCreate, db: Session = Depends(get_db)):
    db_user = db.exec(select(User).where(User.username == user.username)).first()
    if db_user:
        logger.info(f"User {user.username} already exists with id: {db_user.id}")
        raise HTTPException(status_code=400, detail="Username already registered")
    
    db_user = User(username=user.username, email=user.email, hashed_password=user.password)
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    logger.info(f"Registered user: {db_user.username}, user_id: {db_user.id}, email: {db_user.email}")
    return {"username": db_user.username, "email": db_user.email}

@app.post("/upload_file")
async def upload_file(
    file: UploadFile = File(...),
    username: str = Query(...),
    password: str = Query(...),
    db: Session = Depends(get_db)
):
    user = authenticate_user(db, username, password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    logger.info(f"User {username} uploaded a new file: {file.filename}")
    file_content = extract_file_content(file)
    if not file_content.strip():
        raise HTTPException(status_code=400, detail="File content is empty")
    
    user_file = UserFiles(
        user_id=user.id,
        file_name=file.filename,
        content=file_content,
        uploaded_at=datetime.utcnow()
    )
    db.add(user_file)
    db.commit()
    logger.info(f"Stored file content in database for user {username}, file: {file.filename}, length: {len(file_content)}")
    
    return {
        "message": f"File '{file.filename}' uploaded successfully",
        "username": username,
        "filename": file.filename,
        "upload_time": datetime.utcnow().isoformat()
    }

@app.post("/chat")
async def chat(
    chat_request: ChatRequest,
    mode: str = Query(default="default", enum=["default", "reason"]),
    username: str = Query(...),
    password: str = Query(...),
    db: Session = Depends(get_db)
):
    user = authenticate_user(db, username, password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    query = chat_request.message
    session_id = chat_request.session_id

    if session_id:
        session = db.get(ChatSession, session_id)
        if not session or session.user_id != user.id:
            raise HTTPException(status_code=404, detail="Session not found")
    else:
        session = ChatSession(user_id=user.id, title=query[:50], created_at=datetime.utcnow())
        db.add(session)
        db.commit()
        db.refresh(session)
        session_id = session.id

    messages = db.exec(
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.timestamp)
    ).all()
    chat_history = [{"role": msg.role, "content": msg.content, "timestamp": msg.timestamp.isoformat()} for msg in messages]
    chat_history_str = "\n".join([f"{msg['role']}: {msg['content']}" for msg in chat_history]) if chat_history else "No previous conversation."

    latest_file = db.exec(
        select(UserFiles)
        .where(UserFiles.user_id == user.id)
        .order_by(UserFiles.uploaded_at.desc())
    ).first()
    file_content = latest_file.content if latest_file and is_file_relevant(query) else ""
    file_context = file_content if file_content else "No relevant file content available."
    logger.info(f"Query: '{query}', File content used: {bool(file_content)}, Length: {len(file_content)}")

    logger.info(f"Processing query '{query}' in mode '{mode}'")
    current_time = datetime.utcnow().isoformat()

    if mode == "reason":
        conceptual_analyst = Agent(
            llm='groq/gemma2-9b-it',
            role='Conceptual Analyst',
            goal="Analyze the query theoretically, using file content only if relevant.",
            backstory="Expert in breaking down complex queries into core concepts.",
            verbose=True,
        )
        practical_synthesizer = Agent(
            llm='groq/mixtral-8x7b-32768',
            role='Practical Synthesizer',
            goal="Provide practical insights based on the query, using file content only if relevant.",
            backstory="Skilled at applying theory to real-world scenarios.",
            verbose=True,
        )
        solution_architect = Agent(
            llm='groq/deepseek-r1-distill-llama-70b',
            role='Solution Architect',
            goal="Synthesize a comprehensive response, using file content only if relevant.",
            backstory="Expert in crafting polished responses.",
            verbose=True,
        )

        tasks = [
            Task(
                description=f"""
                Analyze '{query}' theoretically with context:
                - Time: {current_time}
                - History: {chat_history_str}
                - File content: {file_context}
                
                Instructions:
                1. If file content is provided and relevant to the query (e.g., query asks about the file), use it as the primary source.
                2. Otherwise, base your analysis on the query and chat history alone.
                3. Provide a structured theoretical analysis.
                """,
                agent=conceptual_analyst,
                expected_output="Theoretical analysis of the query."
            ),
            Task(
                description=f"""
                Provide practical insights for '{query}' with context:
                - Time: {current_time}
                - History: {chat_history_str}
                - File content: {file_context}
                
                Instructions:
                1. If file content is provided and relevant, use it to inform your insights.
                2. Otherwise, focus on the query and chat history.
                3. Include actionable steps or recommendations.
                """,
                agent=practical_synthesizer,
                expected_output="Practical insights based on the query."
            ),
            Task(
                description=f"""
                Synthesize a response for '{query}' with context:
                - Time: {current_time}
                - History: {chat_history_str}
                - File content: {file_context}
                
                Instructions:
                1. Integrate analysis and insights, using file content only if relevant.
                2. Structure the response to be clear and actionable.
                """,
                agent=solution_architect,
                expected_output="Comprehensive response."
            )
        ]
        crew = Crew(
            agents=[conceptual_analyst, practical_synthesizer, solution_architect],
            tasks=tasks,
            process=Process.sequential,
            verbose=True
        )
    else:
        expert_assistant = Agent(
            llm='groq/gemma2-9b-it',
            role='Expert Assistant',
            goal="Provide a helpful and accurate response, using file content only if relevant.",
            backstory="MultiAgentChatbot, a friendly AI assistant.",
            verbose=True,
        )

        task = Task(
            description=f"""
            Answer the query: '{query}'
            
            Context:
            - Current time: {current_time}
            - Chat history: {chat_history_str}
            - File content: {file_context}
            
            Instructions:
            1. If file content is provided and the query explicitly relates to it (e.g., 'summarize the file'), use it as the primary source.
            2. Otherwise, respond based on the query and chat history alone.
            3. Provide a clear and helpful response.
            """,
            agent=expert_assistant,
            expected_output="A clear, helpful response."
        )
        crew = Crew(
            agents=[expert_assistant],
            tasks=[task],
            process=Process.sequential,
            verbose=True
        )

    result = crew.kickoff()
    response = result.raw if hasattr(result, 'raw') else str(result)
    logger.info(f"Agent response: {response[:100]}...")

    user_msg = ChatMessage(session_id=session_id, role="user", content=query, timestamp=datetime.utcnow())
    ai_msg = ChatMessage(session_id=session_id, role="assistant", content=response, timestamp=datetime.utcnow())
    db.add(user_msg)
    db.add(ai_msg)
    db.commit()

    return {
        "response": response,
        "session_id": session_id,
        "messages": [{"role": "user", "content": query}, {"role": "assistant", "content": response}]
    }

@app.get("/sessions")
def get_sessions(username: str = Query(...), password: str = Query(...), db: Session = Depends(get_db)):
    user = authenticate_user(db, username, password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    sessions = db.exec(select(ChatSession).where(ChatSession.user_id == user.id).order_by(ChatSession.created_at.desc())).all()
    return [{"id": s.id, "title": s.title, "created_at": s.created_at.isoformat()} for s in sessions]

@app.get("/session/{session_id}")
def get_session_messages(session_id: int, username: str = Query(...), password: str = Query(...), db: Session = Depends(get_db)):
    user = authenticate_user(db, username, password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    session = db.get(ChatSession, session_id)
    if not session or session.user_id != user.id:
        raise HTTPException(status_code=404, detail="Session not found")
    
    messages = db.exec(select(ChatMessage).where(ChatMessage.session_id == session_id).order_by(ChatMessage.timestamp)).all()
    return [{"role": m.role, "content": m.content, "timestamp": m.timestamp.isoformat()} for m in messages]

@app.get("/all_chats")
def get_all_chats(username: str = Query(...), password: str = Query(...), db: Session = Depends(get_db)):
    user = authenticate_user(db, username, password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    # Fetch all messages across all sessions for the user
    messages = db.exec(
        select(ChatMessage)
        .join(ChatSession)
        .where(ChatSession.user_id == user.id)
        .order_by(ChatMessage.timestamp)
    ).all()
    return [{"role": m.role, "content": m.content, "timestamp": m.timestamp.isoformat(), "session_id": m.session_id} for m in messages]
