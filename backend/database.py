from datetime import datetime
from typing import Optional
from sqlmodel import Field, SQLModel, create_engine
from config import settings

class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    username: str = Field(index=True, unique=True)
    email: str
    hashed_password: str
    created_at: datetime = Field(default_factory=datetime.utcnow)

class ChatSession(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id")
    title: str
    created_at: datetime = Field(default_factory=datetime.utcnow)

class ChatMessage(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    session_id: int = Field(foreign_key="chatsession.id")
    role: str
    content: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)

class UserFiles(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id")
    file_name: str
    content: str
    uploaded_at: datetime = Field(default_factory=datetime.utcnow)

engine = create_engine(settings.DEV_DB_URL)

def create_db_and_tables():
    SQLModel.metadata.create_all(engine)

create_db_and_tables()    