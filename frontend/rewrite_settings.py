import re

file_path = 'C:/Users/aniketh/Projects/Primnox/frontend/src/app/components/SettingsView.tsx'
with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

new_signature = """import { useStore } from '../../store/useStore';

export const IslandSettings = ({ onSync }: { onSync: () => void }) => {
  const settings = useStore(s => s.settings);
  const updateSettings = () => {}; // TODO: map this to the real setter if needed
  
  const [activeModel, setActiveModel] = useState(settings?.active_model || 'Groq_Llama_3');
  const [vadSensitivity, setVadSensitivity] = useState(settings?.vad_sensitivity || 0.5);
  const [operatorAlias, setOperatorAlias] = useState(settings?.operator_alias || 'ANIKETH_P_01');
  const [aiCodename, setAiCodename] = useState(settings?.ai_codename || 'PRIMNOX');
  const [apiKey, setApiKey] = useState(settings?.groq_api_key || '');
  const [openaiApiKey, setOpenaiApiKey] = useState(settings?.openai_api_key || '');
  const [anthropicApiKey, setAnthropicApiKey] = useState(settings?.anthropic_api_key || '');
  const [wakeWord, setWakeWord] = useState(settings?.wake_word || 'hey primnox');
  const [wakeWordEnabled, setWakeWordEnabled] = useState(settings?.wake_word_enabled ?? true);
"""

content = re.sub(r'export const IslandSettings = \({.*?}\) => {', new_signature, content, flags=re.DOTALL)

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)
