import streamlit as st
import requests
from datetime import datetime
from typing import Optional, Dict, Any, List

API_BASE_URL = "http://localhost:8000"

# Set page configuration
st.set_page_config(
    page_title="Zia Assistants",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Initialize session state
if "messages" not in st.session_state:
    st.session_state.messages = []
if "current_session_id" not in st.session_state:
    st.session_state.current_session_id = None
if "mode" not in st.session_state:
    st.session_state.mode = "default"
if "username" not in st.session_state:
    st.session_state.username = None
if "password" not in st.session_state:
    st.session_state.password = None
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

# Custom CSS for layout
st.markdown("""
<style>
    .main .block-container { padding-top: 2rem; }
    .input-container { position: fixed; bottom: 0; left: 0; right: 0; background: white; padding: 1rem; border-top: 1px solid #eee; z-index: 100; }
    .stRadio > div { flex-direction: row !important; gap: 1rem !important; }
    .stRadio label { margin-bottom: 0 !important; padding: 0.2rem 0.5rem !important; }
    .chat-container { max-height: 60vh; overflow-y: auto; }
    .message { padding: 1rem; margin: 0.5rem 0; border-radius: 0.5rem; max-width: 80%; }
    .user-message { border: 1px solid #333; float: right; clear: both; }
    .bot-message { border: 1px solid #333; float: left; clear: both; }
</style>
""", unsafe_allow_html=True)

# API Functions
def register(username: str, email: str, password: str) -> tuple[bool, str]:
    """Register a new user."""
    try:
        data = {"username": username, "email": email, "password": password}
        response = requests.post(f"{API_BASE_URL}/register", json=data)
        if response.status_code == 200:
            return True, "Registration successful! Please log in."
        return False, response.json().get("detail", "Registration failed")
    except requests.RequestException as e:
        return False, f"Connection error: {str(e)}"

def chat(query: str, mode: str, session_id: Optional[int], username: str, password: str) -> Optional[Dict[str, Any]]:
    """Send a query to the chat endpoint and return the response."""
    try:
        params = {"username": username, "password": password, "mode": mode}
        data = {"message": query}
        if session_id:
            data["session_id"] = session_id
        response = requests.post(f"{API_BASE_URL}/chat", params=params, json=data)
        if response.status_code == 200:
            return response.json()
        else:
            st.error(f"Error: {response.json().get('detail', 'Unknown error')}")
            return None
    except requests.RequestException as e:
        st.error(f"Connection error: {str(e)}")
        return None

def get_sessions(username: str, password: str) -> List[Dict[str, Any]]:
    """Fetch all chat sessions for the user."""
    try:
        response = requests.get(f"{API_BASE_URL}/sessions", params={"username": username, "password": password})
        return response.json() if response.status_code == 200 else []
    except requests.RequestException:
        return []

def get_all_chats(username: str, password: str) -> List[Dict[str, Any]]:
    """Fetch all chat messages across all sessions for the user."""
    try:
        response = requests.get(f"{API_BASE_URL}/all_chats", params={"username": username, "password": password})
        return response.json() if response.status_code == 200 else []
    except requests.RequestException:
        return []

def upload_file(file, username: str, password: str) -> tuple[bool, str]:
    """Upload a file to the backend."""
    try:
        file.seek(0)
        file_content = file.read()
        files = {"file": (file.name, file_content, file.type)}
        params = {"username": username, "password": password}
        response = requests.post(f"{API_BASE_URL}/upload_file", files=files, params=params)
        if response.status_code == 200:
            return True, "File uploaded successfully!"
        else:
            return False, response.json().get("detail", "Upload failed")
    except requests.RequestException as e:
        return False, f"Connection error: {str(e)}"

# Display chat function
def display_chat():
    with chat_container:
        # Fetch all chats for the user
        if st.session_state.logged_in:
            all_messages = get_all_chats(st.session_state.username, st.session_state.password)
            st.session_state.messages = all_messages  # Update state with all messages
        
        # Display all messages without timestamp
        for msg in st.session_state.messages:
            div_class = "user-message" if msg["role"] == "user" else "bot-message"
            st.markdown(
                f"<div class='message {div_class}'><strong>{msg['role'].title()}:</strong> {msg['content']}</div>",
                unsafe_allow_html=True
            )

# Authentication Interface
if not st.session_state.logged_in:
    st.title("🔑 Zia Assistant Authentication")
    tab1, tab2 = st.tabs(["Login", "Register"])

    with tab1:
        with st.form("login_form"):
            login_username = st.text_input("Username", key="login_username")
            login_password = st.text_input("Password", type="password", key="login_password")
            if st.form_submit_button("Login"):
                test_response = requests.get(f"{API_BASE_URL}/sessions", params={"username": login_username, "password": login_password})
                if test_response.status_code == 200:
                    st.session_state.logged_in = True
                    st.session_state.username = login_username
                    st.session_state.password = login_password
                    st.success("Logged in successfully!")
                    st.rerun()
                else:
                    st.error("Invalid username or password")

    with tab2:
        with st.form("register_form"):
            reg_username = st.text_input("Username", key="reg_username")
            reg_email = st.text_input("Email", key="reg_email")
            reg_password = st.text_input("Password", type="password", key="reg_password")
            if st.form_submit_button("Register"):
                success, message = register(reg_username, reg_email, reg_password)
                if success:
                    st.success(message)
                else:
                    st.error(message)
else:
    # Sidebar
    with st.sidebar:
        st.header("Chat Sessions")
        if st.button("New Chat", type="primary"):
            st.session_state.current_session_id = None
            # Do not clear messages; we want to keep all chats visible

        sessions = get_sessions(st.session_state.username, st.session_state.password)
        session_options = ["New Session"] + [f"{s['title']} ({s['created_at'][:10]})" for s in sessions]
        selected_session = st.selectbox("Select Session to Continue", session_options, index=0)
        
        if selected_session != "New Session":
            session_id = next(s["id"] for s in sessions if f"{s['title']} ({s['created_at'][:10]})" == selected_session)
            if st.session_state.current_session_id != session_id:
                st.session_state.current_session_id = session_id
        elif selected_session == "New Session" and st.session_state.current_session_id is not None:
            st.session_state.current_session_id = None

        st.header("Upload Files")
        uploaded_file = st.file_uploader("Choose a file (TXT or PDF)", type=["txt", "pdf"])
        if uploaded_file and st.button("Upload"):
            success, message = upload_file(uploaded_file, st.session_state.username, st.session_state.password)
            if success:
                st.success(message)
            else:
                st.error(message)

    # Main Chat Area
    st.header("Zia Assistant - All Chats")
    chat_container = st.container()

    # Input Area
    with st.container():
        st.markdown('<div class="input-container">', unsafe_allow_html=True)
        user_input = st.chat_input("Message Zia...")
        mode = st.radio("Select Mode:", ["default", "reason"], horizontal=True, key="mode_radio")
        st.session_state.mode = mode
        st.markdown('</div>', unsafe_allow_html=True)

        if user_input:
            with st.spinner("Generating response..."):
                result = chat(user_input, st.session_state.mode, st.session_state.current_session_id, st.session_state.username, st.session_state.password)
                if result:
                    st.session_state.current_session_id = result["session_id"]
                    all_messages = get_all_chats(st.session_state.username, st.session_state.password)
                    st.session_state.messages = all_messages

    # Display all messages
    display_chat()