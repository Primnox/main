import json
import re

new_think_stream = """
def think_stream(prompt, context=None):
    \"\"\"
    Primnox Agentic Thinking Engine (Streaming)
    Supports Tool Calling for OpenAI and Groq.
    \"\"\"
    log.info(f"Streaming thoughts about: {prompt[:50]}...")
    
    try:
        from settings_manager import load_settings
        settings = load_settings()
        active_model = settings.get("active_model", "Groq_Llama_3")
    except Exception:
        active_model = "Groq_Llama_3"
        settings = {}

    system_content = get_adaptive_system_prompt(settings)
    user_content = f"Context:\\n{context}\\n\\nUser: {prompt}" if context else prompt

    messages = [
        {"role": "system", "content": system_content},
        {"role": "user", "content": user_content}
    ]

    api_key = ""
    url = ""
    model_name = ""
    headers = {}
    
    if active_model == "OpenAI_GPT_4o":
        api_key = get_api_key("openai")
        url = "https://api.openai.com/v1/chat/completions"
        model_name = "gpt-4o"
        headers = {"Authorization": f"Bearer {api_key}"}
    elif active_model == "Anthropic_Claude_3":
        # Anthropic tool calling is different, we'll skip for now and fallback
        api_key = get_api_key("anthropic")
        url = "https://api.anthropic.com/v1/messages"
        model_name = "claude-3-5-sonnet-20241022"
        headers = {"x-api-key": api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"}
    else:
        api_key = get_api_key("groq")
        url = "https://api.groq.com/openai/v1/chat/completions"
        model_name = "llama-3.3-70b-versatile"
        headers = {"Authorization": f"Bearer {api_key}"}

    if not api_key:
        yield f"{active_model} API key not set."
        return

    try:
        if active_model in ["OpenAI_GPT_4o", "Groq_Llama_3"]:
            # Step 1: Initial call with tools (Non-streaming to catch tools easily)
            resp = requests.post(
                url,
                headers=headers,
                json={
                    "model": model_name,
                    "messages": messages,
                    "tools": TOOL_DEFINITIONS,
                    "tool_choice": "auto"
                },
                timeout=30
            )
            
            if resp.status_code != 200:
                yield f"[API ERROR {resp.status_code}]: {resp.text}"
                return
                
            res_data = resp.json()
            response_msg = res_data.get("choices", [{}])[0].get("message", {})
            
            # Step 2: Handle tool calls
            tool_calls = response_msg.get("tool_calls")
            if tool_calls:
                log.info(f"LLM decided to use {len(tool_calls)} tools.")
                # Append the assistant's tool call message
                messages.append(response_msg)
                
                for tool_call in tool_calls:
                    func_name = tool_call.get("function", {}).get("name")
                    try:
                        args = json.loads(tool_call.get("function", {}).get("arguments", "{}"))
                    except Exception:
                        args = {}
                        
                    log.info(f"Executing tool {func_name}...")
                    result = execute_tool(func_name, args)
                    
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.get("id"),
                        "name": func_name,
                        "content": str(result)
                    })
                    
                # Step 3: Stream the final response after tools
                resp_stream = requests.post(
                    url,
                    headers=headers,
                    json={
                        "model": model_name,
                        "messages": messages,
                        "stream": True
                    },
                    stream=True,
                    timeout=30
                )
                
                for line in resp_stream.iter_lines():
                    if line:
                        decoded = line.decode('utf-8')
                        if decoded.startswith("data: "):
                            data_str = decoded[6:]
                            if data_str.strip() == "[DONE]":
                                break
                            try:
                                chunk = json.loads(data_str)
                                token = chunk.get("choices", [{}])[0].get("delta", {}).get("content", "")
                                if token:
                                    yield token
                            except Exception:
                                pass
            else:
                # No tools called, we already have the full text response.
                # To keep it streaming to the UI, we just yield it in chunks.
                content = response_msg.get("content", "")
                for word in content.split(" "):
                    yield word + " "
                    
        else:
            # Fallback for Anthropic
            resp = requests.post(
                url,
                headers=headers,
                json={
                    "model": model_name,
                    "messages": [{"role": "user", "content": user_content}],
                    "system": system_content,
                    "stream": True,
                    "max_tokens": 1024
                },
                stream=True,
                timeout=30
            )
            for line in resp.iter_lines():
                if line:
                    decoded = line.decode('utf-8')
                    if decoded.startswith("data: "):
                        data_str = decoded[6:]
                        try:
                            chunk = json.loads(data_str)
                            if chunk.get("type") == "content_block_delta":
                                token = chunk.get("delta", {}).get("text", "")
                                if token:
                                    yield token
                        except Exception:
                            pass

    except Exception as e:
        log.error(f"Streaming thinking crash: {e}", exc_info=True)
        yield f"error thinking: {e}"
"""

with open('C:/Users/aniketh/Projects/Primnox/backend/brain.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Replace the old think_stream
content = re.sub(r'def think_stream\(prompt, context=None\):.*?if __name__ == "__main__":', new_think_stream + '\nif __name__ == "__main__":', content, flags=re.DOTALL)

with open('C:/Users/aniketh/Projects/Primnox/backend/brain.py', 'w', encoding='utf-8') as f:
    f.write(content)
print('Updated think_stream.')
