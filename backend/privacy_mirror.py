# backend/privacy_mirror.py
import re
from logger import get_logger

log = get_logger("privacy")

# Patterns for common PII
PATTERNS = {
    "email": r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}',
    "ipv4": r'\b(?:\d{1,3}\.){3}\d{1,3}\b',
    "credit_card": r'\b(?:\d{4}[-\s]?){3}\d{4}\b',
    "api_key": r'(?:api_key|secret|password|token|key)["\']?\s*[:=]\s*["\']?([a-zA-Z0-9_\-\.]{16,})["\']?',
    "generic_key": r'\b[a-zA-Z0-9]{32,}\b' # Catch-all for long hex/alphanumeric strings
}

def redact_text(text: str) -> str:
    """Redacts PII from the given text using regex patterns."""
    if not text:
        return text
    
    redacted_count = 0
    original_text = text
    
    for label, pattern in PATTERNS.items():
        matches = re.findall(pattern, text)
        if matches:
            redacted_count += len(matches)
            # For API keys, we want to redact the group 1 if it exists
            if label == "api_key":
                text = re.sub(pattern, lambda m: m.group(0).replace(m.group(1), "[REDACTED]"), text)
            else:
                text = re.sub(pattern, f"[REDACTED_{label.upper()}]", text)
                
    if redacted_count > 0:
        log.info(f"Redacted {redacted_count} PII items from text.")
        
    return text

if __name__ == "__main__":
    test_text = "My email is test@example.com, my IP is 192.168.1.1, and my secret key is 'sk_live_51abcdef1234567890'. Oh, and my card is 1234-5678-9012-3456."
    print(f"Original: {test_text}")
    print(f"Redacted: {redact_text(test_text)}")
