# backend/tools.py
import os
import re
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


# === WEB REACH: give the assistant eyes on specific pages, not just search ===
# Modeled after https://github.com/Panniantong/agent-reach's "zero-config"
# channels (web/YouTube/GitHub/RSS) plus the two login-gated channels
# (Twitter/Reddit) that actually have stable public read paths not requiring
# any cookie/session at all. Full Twitter search/timeline and
# Instagram/Facebook need reverse-engineered private GraphQL APIs + session
# cookies that change without notice — deliberately not built here; see the
# implementation plan for the settings/keyring plumbing to add if that's
# ever wanted. Same idiom as research_engine.py's _fetch_page and
# skills/calendar_providers/ical_provider.py: explicit timeout, custom
# User-Agent, degrade to a clean string on failure, never raise.

def fetch_webpage(url: str) -> str:
    """Read a webpage's main content via Jina Reader (r.jina.ai) — a free,
    zero-config reader service that strips nav/ads/boilerplate server-side
    and returns clean text, so no local HTML parsing is needed here."""
    url = (url or "").strip()
    if not url:
        return "Error: no URL provided."
    if not url.startswith(("http://", "https://")):
        url = f"https://{url}"
    log.info(f"Fetching webpage via Jina Reader: {url}")
    try:
        resp = requests.get(f"https://r.jina.ai/{url}", timeout=15, headers={"User-Agent": "Primnox/1.0"})
        resp.raise_for_status()
        text = resp.text.strip()
        return text[:8000] if text else "The page appears to be empty."
    except requests.exceptions.Timeout:
        return f"Timed out reading {url}."
    except requests.exceptions.RequestException as e:
        return f"Could not read {url}: {e}"


def _extract_youtube_id(url_or_id: str) -> str:
    s = (url_or_id or "").strip()
    if not s:
        return ""
    m = re.search(r'(?:v=|youtu\.be/|shorts/)([A-Za-z0-9_-]{11})', s)
    if m:
        return m.group(1)
    if re.fullmatch(r'[A-Za-z0-9_-]{11}', s):
        return s
    return ""


def fetch_youtube_transcript(url_or_id: str) -> str:
    """Extract a YouTube video's transcript via youtube-transcript-api — hits
    YouTube's own timedtext endpoint over plain HTTP, no yt-dlp binary or
    subprocess needed."""
    video_id = _extract_youtube_id(url_or_id)
    if not video_id:
        return "Error: could not find a YouTube video ID in that input."
    log.info(f"Fetching YouTube transcript for video: {video_id}")
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        transcript = YouTubeTranscriptApi().fetch(video_id)
        text = " ".join(snippet.text for snippet in transcript)
        return text[:8000] if text.strip() else "Transcript is empty."
    except ImportError:
        return "youtube-transcript-api is not installed on this machine."
    except Exception as e:
        return f"Could not fetch transcript for video {video_id}: {e}"


def _extract_github_repo(s: str) -> str:
    s = (s or "").strip()
    if not s:
        return ""
    m = re.search(r'github\.com/([\w.-]+/[\w.-]+)', s)
    if m:
        return re.sub(r'\.git$', '', m.group(1))
    if re.fullmatch(r'[\w.-]+/[\w.-]+', s):
        return s
    return ""


def fetch_github_repo_info(repo: str) -> str:
    """Fetch a public GitHub repo's metadata + open issues via the REST API
    directly — no `gh` CLI needed, works even if the user never installed or
    authenticated it."""
    repo = _extract_github_repo(repo)
    if not repo:
        return "Error: could not find an owner/repo in that input."
    log.info(f"Fetching GitHub repo info: {repo}")
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "Primnox/1.0"}
    try:
        resp = requests.get(f"https://api.github.com/repos/{repo}", timeout=10, headers=headers)
        if resp.status_code == 404:
            return f"Repo '{repo}' not found (private, or doesn't exist)."
        resp.raise_for_status()
        data = resp.json()
        issues_resp = requests.get(
            f"https://api.github.com/repos/{repo}/issues", params={"state": "open", "per_page": 5},
            timeout=10, headers=headers,
        )
        issues = issues_resp.json() if issues_resp.ok else []
        issue_lines = "\n".join(f"- #{i['number']} {i['title']}" for i in issues if "pull_request" not in i)
        return (
            f"{data.get('full_name')}: {data.get('description') or 'no description'}\n"
            f"Stars: {data.get('stargazers_count', 0)} | Language: {data.get('language') or 'unknown'}\n"
            f"Open issues:\n{issue_lines or 'none'}"
        )
    except requests.exceptions.Timeout:
        return f"Timed out reaching GitHub for {repo}."
    except requests.exceptions.RequestException as e:
        return f"Could not fetch GitHub repo {repo}: {e}"


def fetch_rss_feed(url: str) -> str:
    """Read an RSS/Atom feed via feedparser — handles the real-world format
    quirks a hand-rolled XML parser would trip on."""
    url = (url or "").strip()
    if not url:
        return "Error: no feed URL provided."
    log.info(f"Fetching RSS feed: {url}")
    try:
        import feedparser
        parsed = feedparser.parse(url)
        if parsed.bozo and not parsed.entries:
            return f"Could not parse a feed at {url}."
        entries = parsed.entries[:10]
        if not entries:
            return "Feed has no entries."
        lines = [f"- {e.get('title', 'untitled')} ({e.get('link', '')})" for e in entries]
        return f"{parsed.feed.get('title', url)}:\n" + "\n".join(lines)
    except ImportError:
        return "feedparser is not installed on this machine."
    except Exception as e:
        return f"Could not fetch RSS feed {url}: {e}"


def fetch_reddit_thread(url: str) -> str:
    """Read a Reddit thread via Reddit's own public JSON API (append .json
    to any public thread URL) — despite common belief there's no zero-config
    path, this needs no login/cookies for public subreddits."""
    url = (url or "").strip()
    if not url:
        return "Error: no Reddit URL provided."
    if "reddit.com" not in url:
        return "Error: that doesn't look like a reddit.com URL."
    json_url = url.split("?")[0].rstrip("/") + ".json"
    log.info(f"Fetching Reddit thread: {json_url}")
    try:
        resp = requests.get(json_url, timeout=10, headers={"User-Agent": "Primnox/1.0 (by /u/primnox)"})
        resp.raise_for_status()
        data = resp.json()
        post = data[0]["data"]["children"][0]["data"]
        comments = data[1]["data"]["children"][:5]
        comment_lines = [f"- {c['data'].get('body', '')[:200]}" for c in comments if c.get("kind") == "t1"]
        return (
            f"{post.get('title')}\n{post.get('selftext', '')[:1000]}\n\n"
            f"Top comments:\n" + ("\n".join(comment_lines) or "none")
        )
    except requests.exceptions.Timeout:
        return f"Timed out reaching Reddit for {url}."
    except requests.exceptions.RequestException as e:
        return f"Could not fetch Reddit thread {url}: {e}"
    except (KeyError, IndexError, ValueError):
        return f"Could not parse Reddit's response for {url}."


def _extract_tweet_id(s: str) -> str:
    s = (s or "").strip()
    if not s:
        return ""
    m = re.search(r'status/(\d+)', s)
    if m:
        return m.group(1)
    if s.isdigit():
        return s
    return ""


def fetch_tweet(url_or_id: str) -> str:
    """Read a single tweet's text via Twitter's public syndication endpoint
    (the same one Twitter's own embed widgets use) — no cookies/login
    needed. Covers "what does this tweet say," not search/timeline browsing
    (those need reverse-engineered private APIs + session cookies)."""
    tweet_id = _extract_tweet_id(url_or_id)
    if not tweet_id:
        return "Error: could not find a tweet ID in that input."
    log.info(f"Fetching tweet: {tweet_id}")
    try:
        resp = requests.get(
            "https://cdn.syndication.twimg.com/tweet-result",
            params={"id": tweet_id, "token": "a"}, timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        if "text" not in data:
            return f"Tweet {tweet_id} not found or is private."
        user = data.get("user", {})
        return f"@{user.get('screen_name', '?')} ({user.get('name', 'unknown')}): {data['text']}"
    except requests.exceptions.Timeout:
        return f"Timed out fetching tweet {tweet_id}."
    except requests.exceptions.RequestException as e:
        return f"Could not fetch tweet {tweet_id}: {e}"
    except (KeyError, ValueError):
        return f"Could not parse the tweet response for {tweet_id}."


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
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_webpage",
            "description": "Read the full text content of a specific webpage URL. Use when the user gives you a link and asks what it says, to summarize it, or to answer a question about its content — unlike web_search, this reads one specific page in full.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "The full URL of the webpage to read."}
                },
                "required": ["url"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_youtube_transcript",
            "description": "Get the transcript/captions of a YouTube video. Use when the user shares a YouTube link and asks what it's about, to summarize it, or to answer questions about its content.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "The YouTube video URL or video ID."}
                },
                "required": ["url"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_github_repo_info",
            "description": "Look up a public GitHub repository's description, stats, and open issues. Use when the user asks what a GitHub repo/project does or references a github.com link.",
            "parameters": {
                "type": "object",
                "properties": {
                    "repo": {"type": "string", "description": "The repo as 'owner/name' or a full github.com URL."}
                },
                "required": ["repo"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_rss_feed",
            "description": "Read the latest entries from an RSS or Atom feed URL. Use when the user asks to check a feed or 'what's new' on a site that has one.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "The RSS/Atom feed URL."}
                },
                "required": ["url"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_reddit_thread",
            "description": "Read a Reddit thread's post and top comments. Use when the user shares a reddit.com link and asks what people are saying about it.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "The full URL of the Reddit thread."}
                },
                "required": ["url"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_tweet",
            "description": "Read the text of a single tweet/X post. Use when the user shares a twitter.com or x.com status link and asks what it says.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "The tweet URL or tweet ID."}
                },
                "required": ["url"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "delete_memory",
            "description": "Permanently delete a stored memory. Use only when the user explicitly asks to forget/delete/remove something they previously told you to remember. Requires the user's confirmation before it takes effect.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Text describing the memory to delete (matched against stored memories)."
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "delete_note",
            "description": "Permanently delete a saved note. Use only when the user explicitly asks to delete/remove a note. Requires the user's confirmation before it takes effect.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Text describing the note to delete (matched by title/content)."
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_skills",
            "description": "List the specialized capabilities (skills) available beyond your built-in tools — e.g. PDF generation, presentation building, meeting summaries. Use this when a request needs a capability that doesn't match any of your other tools, to check whether a dedicated skill can handle it.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "use_skill",
            "description": "Invoke a specific skill by name to handle a task (see list_skills for available names).",
            "parameters": {
                "type": "object",
                "properties": {
                    "skill_name": {"type": "string", "description": "The exact skill name, from list_skills."},
                    "query": {"type": "string", "description": "The user's request to hand to the skill."}
                },
                "required": ["skill_name", "query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "run_python",
            "description": "Run Python code in a sandboxed environment (a separate, isolated Windows account with no access to the user's files, credentials, or network) and return its output. Use for real computation or data processing the user asked for — not as a first resort. Requires the user's explicit confirmation before it runs, and only works if sandboxed execution is enabled in Settings.",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "The Python code to run."}
                },
                "required": ["code"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "run_shell",
            "description": "Run a shell command in a sandboxed environment (a separate, isolated Windows account with no access to the user's files, credentials, or network) and return its output. Use only when the user explicitly wants a command run. Requires the user's explicit confirmation before it runs, and only works if sandboxed execution is enabled in Settings.",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "The shell command to run."}
                },
                "required": ["code"]
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
            # The model only calls this tool because the user asked it to
            # remember something — that's a direct statement, not a guess.
            success = add_memory(text, category=category, session_id=session_id, provenance="explicit")
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
            try:
                task_id = int(arguments.get("task_id", 0))
            except (TypeError, ValueError):
                return "Invalid task_id — use list_tasks to get numeric IDs first."
            success = _complete_task(task_id)
            if success:
                if _broadcast_cb:
                    _broadcast_cb("task_added", {})  # refresh frontend task list
                return f"Task {task_id} marked as complete."
            return f"Could not find task {task_id}."

        elif name == "fetch_webpage":
            return fetch_webpage(arguments.get("url", ""))

        elif name == "fetch_youtube_transcript":
            return fetch_youtube_transcript(arguments.get("url", ""))

        elif name == "fetch_github_repo_info":
            return fetch_github_repo_info(arguments.get("repo", ""))

        elif name == "fetch_rss_feed":
            return fetch_rss_feed(arguments.get("url", ""))

        elif name == "fetch_reddit_thread":
            return fetch_reddit_thread(arguments.get("url", ""))

        elif name == "fetch_tweet":
            return fetch_tweet(arguments.get("url", ""))

        elif name == "delete_memory":
            from memory import search_memories, delete_memory as _delete_memory
            from permission_manager import request_permission
            query = arguments.get("query", "")
            matches = search_memories(query, limit=1)
            if not matches:
                return f"Couldn't find a memory matching \"{query}\"."
            target = matches[0]
            allowed = request_permission(
                action="delete_memory",
                description=f"Delete this memory: \"{target['text']}\"?",
                session_id=session_id or "",
            )
            if not allowed:
                return "Deletion cancelled — the user did not approve it."
            _delete_memory(target["key"])
            return f"Deleted memory: \"{target['text']}\""

        elif name == "delete_note":
            from notes_manager import search_notes, delete_note as _delete_note
            from permission_manager import request_permission
            query = arguments.get("query", "")
            matches = search_notes(query, limit=1)
            if not matches:
                return f"Couldn't find a note matching \"{query}\"."
            target = matches[0]
            allowed = request_permission(
                action="delete_note",
                description=f"Delete this note: \"{target['title']}\"?",
                session_id=session_id or "",
            )
            if not allowed:
                return "Deletion cancelled — the user did not approve it."
            _delete_note(target["id"])
            if _broadcast_cb:
                _broadcast_cb("note_added", {})  # refresh frontend note list
            return f"Deleted note: \"{target['title']}\""

        elif name == "list_skills":
            from skills.skill_router import list_skills as _list_skills
            registry = _list_skills()
            if not registry:
                return "No skills currently registered."
            lines = [f"- {s['name']}: {s.get('description', '')}" for s in registry]
            return "Available skills:\n" + "\n".join(lines)

        elif name == "use_skill":
            from skills.skill_router import route_skill
            skill_name_arg = arguments.get("skill_name", "")
            query = arguments.get("query", "")
            res = route_skill(user_message=query, session_id=session_id, skill_name=skill_name_arg)
            if not res.get("success"):
                return res.get("error", f"Skill '{skill_name_arg}' failed.")
            return res.get("output_text", f"Skill '{skill_name_arg}' did not return output.")

        elif name in ("run_python", "run_shell"):
            import code_exec
            code = arguments.get("code", "")
            runner = code_exec.run_python if name == "run_python" else code_exec.run_shell
            result = runner(code, session_id=session_id or "")
            if "error" in result:
                return result["error"]
            lines = [f"exit code: {result['return_code']}"]
            if result.get("timed_out"):
                lines.append("(execution timed out and was terminated)")
            if result.get("stdout"):
                lines.append(f"stdout:\n{result['stdout']}")
            if result.get("stderr"):
                lines.append(f"stderr:\n{result['stderr']}")
            if result.get("files_created"):
                lines.append(f"files created: {', '.join(result['files_created'])}")
            return "\n".join(lines)

        else:
            return f"Error: Tool '{name}' not found."
    except Exception as e:
        log.error(f"Error executing tool {name}: {e}")
        return f"Error executing tool: {e}"

if __name__ == "__main__":
    print(web_search("latest AI news"))
