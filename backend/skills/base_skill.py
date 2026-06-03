# skills/base_skill.py
class BaseSkill:
    name = ""
    supported_extensions = []
    trigger_words = []
    REQUIRES_SYSTEM = []
    REQUIRES_PIP = []
    def execute(self, file_path, user_message=None):
        raise NotImplementedError
