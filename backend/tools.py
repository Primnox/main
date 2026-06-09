# backend/tools.py
import os
import requests
from dotenv import load_dotenv
from logger import get_logger

log = get_logger("tools")
load_dotenv()

# Optional broadcast callback — set by core.py so tool actions can notify the frontend
_broadcast_cb = None

def set_broadcast_callback(cb):
    global _broadcast_cb
    _broadcast_cb = cb

def web_search(query):
    """
    Primnox's Web Search Tool.
    Uses duckduckgo-search (DDGS) for unlimited, free web search.
    """
    log.info(f"Performing web search via DuckDuckGo: {query}")
    try:
        from ddgs import DDGS
        
        ddgs = DDGS()
        results = list(ddgs.text(query, max_results=10))
            
        if not results:
            log.info("No search results found.")
            return "no results found."
        
        log.info(f"Found {len(results)} results.")
        formatted = "\n".join([f"- {r.get('title', 'No Title')}: {r.get('href', '')}\n  {r.get('body', '')}...\n" for r in results])
        return formatted
    except Exception as e:
        log.error(f"Search API crash: {e}")
        return f"error during search: {str(e)}"

# === TOOL SCHEMAS FOR LLM FUNCTION CALLING ===

TOOL_DEFINITIONS = [

    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Perform a web search to find current information, news, or answers to questions.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query."
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_screen",
            "description": "Read the text currently visible on the user's screen or active window.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "describe_screen_vision",
            "description": "Take a screenshot of the user's screen and use Vision AI to describe what is happening visually.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_memory",
            "description": "Search the user's long-term memory for past conversations, facts, or preferences.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query to look up in memory."
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "save_note",
            "description": "Save a note for the user. Use this when the user asks you to remember something, take a note, or save information.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "A short title for the note."
                    },
                    "text": {
                        "type": "string",
                        "description": "The full note content."
                    }
                },
                "required": ["title", "text"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "add_task",
            "description": "Add a task or to-do item for the user. Use when the user says they need to do something or asks you to track a task.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "The task description."
                    },
                    "priority": {
                        "type": "string",
                        "description": "Priority level: 'urgent', 'normal', or 'low'.",
                        "enum": ["urgent", "normal", "low"]
                    }
                },
                "required": ["text"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "save_memory",
            "description": "Save an important fact or preference to long-term memory. Use when the user shares personal preferences, important facts, or things they want you to always remember.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "The memory to store."
                    },
                    "category": {
                        "type": "string",
                        "description": "Category: 'work', 'personal', 'project', or 'session'.",
                        "enum": ["work", "personal", "project", "session"]
                    }
                },
                "required": ["text"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_notes",
            "description": "Search the user's notes for information, previously captured content, or saved documents.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query to look up in notes."
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "set_reminder",
            "description": "Set a reminder for the user. Use when the user asks to be reminded about something after a delay.",
            "parameters": {
                "type": "object",
                "properties": {
                    "message": {
                        "type": "string",
                        "description": "What to remind the user about."
                    },
                    "delay_seconds": {
                        "type": "integer",
                        "description": "Number of seconds until the reminder fires (e.g. 300 = 5 minutes, 3600 = 1 hour)."
                    }
                },
                "required": ["message", "delay_seconds"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_tasks",
            "description": "List the user's current pending tasks and to-dos.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "complete_task",
            "description": "Mark a task as completed. Use when the user says they finished or completed a task.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {
                        "type": "integer",
                        "description": "The ID of the task to mark as complete (from list_tasks)."
                    }
                },
                "required": ["task_id"]
            }
        }
    }
]

def execute_tool(name: str, arguments: dict, session_id: str = None) -> str:
    """Executes a tool by name and returns the string result."""
    log.info(f"Executing tool: {name} with args: {arguments}")
    
    try:
        if name == "web_search":
            return web_search(arguments.get("query", ""))
            
        elif name == "read_screen":
            from screen_reader import read_screen
            res = read_screen()
            visible_elements = res.get('visible_texts', [])[:20]
            return f"Active Window: {res.get('window_title')}\nVisible Text: {', '.join(visible_elements)}"
            
        elif name == "describe_screen_vision":
            from sensor_vision import describe_screen
            res = describe_screen()
            return res.get("description", "Vision failed to analyze screen.")
            
        elif name == "search_memory":
            from memory import search_memories
            results = search_memories(arguments.get("query", ""))
            if not results:
                return "No relevant memories found."
            return "\n".join([f"- {m.get('text')}" for m in results])
            

            
        elif name == "save_note":
            from notes_manager import add_note
            title = arguments.get("title", "Untitled")
            text = arguments.get("text", "")
            add_note(text, title=title)
            if _broadcast_cb:
                _broadcast_cb("note_added", {"title": title})
            return f"Note saved: {title}"

        elif name == "add_task":
            from notes_manager import add_task
            text = arguments.get("text", "")
            priority = arguments.get("priority", "normal")
            add_task(text, priority=priority)
            if _broadcast_cb:
                _broadcast_cb("task_added", {"text": text})
            return f"Task added: {text}"

        elif name == "save_memory":
            from memory import add_memory
            text = arguments.get("text", "")
            category = arguments.get("category", "session")
            success = add_memory(text, category=category, session_id=session_id)
            if success and _broadcast_cb:
                _broadcast_cb("memory_updated", {"text": text[:60]})
            return f"Memory saved: {text[:50]}" if success else "Memory already exists (duplicate)."
            
        elif name == "search_notes":
            from notes_manager import search_notes
            query = arguments.get("query", "")
            results = search_notes(query, limit=5)
            if not results:
                return "No notes found matching that query."
            lines = [f"- **{r['title']}** ({r.get('project','General')}): {r['text'][:150]}" for r in results]
            return f"Found {len(results)} note(s):\n" + "\n".join(lines)

        elif name == "set_reminder":
            from reminder_manager import add_reminder
            message = arguments.get("message", "reminder")
            delay = int(arguments.get("delay_seconds", 300))
            add_reminder(message, delay)
            mins = delay // 60
            secs = delay % 60
            time_str = f"{mins}m {secs}s" if mins else f"{secs}s"
            return f"Reminder set: '{message}' in {time_str}"

        elif name == "list_tasks":
            from notes_manager import get_tasks
            tasks = get_tasks()
            pending = [t for t in tasks if not t.get("completed") and not t.get("is_complete")]
            if not pending:
                return "No pending tasks."
            lines = [f"- [ID:{t['id']}] {t['text']} (priority: {t.get('priority','normal')})" for t in pending]
            return f"Pending tasks ({len(pending)}):\n" + "\n".join(lines)

        elif name == "complete_task":
            from notes_manager import complete_task as _complete_task
            task_id = int(arguments.get("task_id", 0))
            success = _complete_task(task_id)
            if success:
                if _broadcast_cb:
                    _broadcast_cb("task_added", {})  # refresh frontend task list
                return f"Task {task_id} marked as complete."
            return f"Could not find task {task_id}."

        else:
            return f"Error: Tool '{name}' not found."
    except Exception as e:
        log.error(f"Error executing tool {name}: {e}")
        return f"Error executing tool: {e}"

if __name__ == "__main__":
    print(web_search("latest AI news"))
