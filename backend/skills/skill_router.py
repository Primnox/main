import os
import importlib
import inspect
from pathlib import Path
from skills.base_skill import BaseSkill
from logger import get_logger

log = get_logger("skills")

SKILL_REGISTRY = {}
TRIGGER_MAP = {}

def register_skill(skill_cls):
    skill = skill_cls()
    log.info(f"Registering skill: {skill.name}")
    for ext in skill.supported_extensions:
        SKILL_REGISTRY[ext.lower()] = skill_cls
    for word in skill.trigger_words:
        TRIGGER_MAP[word.lower()] = skill_cls

def discover_skills():
    """Auto-discover all skill classes in the skills/ directory."""
    skills_dir = Path(__file__).parent
    
    for file_path in skills_dir.glob("*_skill.py"):
        if file_path.name == "base_skill.py":
            continue
            
        module_name = f"skills.{file_path.stem}"
        try:
            module = importlib.import_module(module_name)
            for name, obj in inspect.getmembers(module, inspect.isclass):
                if issubclass(obj, BaseSkill) and obj is not BaseSkill:
                    register_skill(obj)
        except Exception as e:
            log.error(f"Failed to load skill module {module_name}: {e}")

# Import and register skills dynamically
discover_skills()

def get_skill_for_extension(ext):
    return SKILL_REGISTRY.get(ext.lower())

def get_skill_for_trigger(text):
    if not text:
        return None
    text = text.lower()
    for trigger, skill_cls in TRIGGER_MAP.items():
        if trigger in text:
            return skill_cls
    return None

def route_skill(file_path=None, user_message=None):
    log.info(f"Routing skill for path={file_path}, message='{user_message}'")
    skill_cls = None
    if file_path:
        ext = Path(file_path).suffix.lstrip('.').lower()
        skill_cls = get_skill_for_extension(ext)
    else:
        skill_cls = get_skill_for_trigger(user_message)

    if not skill_cls:
        log.warning("No matching skill found for input.")
        return {"error": "No matching skill found."}
    
    skill = skill_cls()
    log.info(f"Executing skill: {skill.name}")
    return skill.execute(file_path, user_message)
