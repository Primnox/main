import uuid
import datetime
from database import (
    db_get_all_sessions,
    db_create_session,
    db_get_latest_session_id,
    db_get_session_messages,
    db_append_message,
    db_update_session,
    db_delete_session
)

def get_current_time():
    return datetime.datetime.now().isoformat()

def get_all_sessions():
    return db_get_all_sessions()

def create_session(title="New Chat"):
    new_id = str(uuid.uuid4())
    date = get_current_time()
    db_create_session(new_id, title, date)
    return {
        "id": new_id,
        "title": title,
        "date": date,
        "folderId": None,
        "isPinned": False
    }

def get_session_messages(session_id):
    if session_id == "current":
        latest_id = db_get_latest_session_id()
        if latest_id:
            session_id = latest_id
        else:
            session = create_session()
            session_id = session["id"]
            
    return db_get_session_messages(session_id)

def append_message_to_session(session_id, text, speaker):
    if session_id == "current":
        latest_id = db_get_latest_session_id()
        if latest_id:
            session_id = latest_id
        else:
            session = create_session()
            session_id = session["id"]
            
    msg_id = str(uuid.uuid4())
    timestamp = get_current_time()
    
    db_append_message(msg_id, session_id, text, speaker, timestamp)
    
    return {
        "text": text,
        "speaker": speaker,
        "timestamp": timestamp
    }

def update_session(session_id, title=None, is_pinned=None, folder_id=None):
    db_update_session(session_id, title, is_pinned, folder_id)
    return True

def delete_session(session_id):
    db_delete_session(session_id)
    try:
        from memory import delete_memories_by_session
        delete_memories_by_session(session_id)
    except Exception as e:
        print(f"Failed to delete memories for session {session_id}: {e}")
        
    return True
