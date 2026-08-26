import { useState } from 'react';
import { Copy, RotateCcw, Menu, Settings, LogOut, Send, Paperclip, Mic, StopCircle, ChevronDown } from 'lucide-react';
import './mainstream.css';

/**
 * Mainstream Assistants UI Showcase
 *
 * Demonstrates standard patterns found across ChatGPT, Gemini, Copilot, and Claude,
 * adapted to Primnox's Tactical Telemetry aesthetic (dark, red accent, monospace).
 *
 * Key patterns demonstrated:
 * - Left sidebar navigation
 * - Standard message layout (user right, assistant left)
 * - Message actions (Copy, Regenerate)
 * - Input field with suggested prompts
 * - Stop button during generation
 * - Model selector in top bar
 * - Empty state with suggested prompts
 */

interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
  isStreaming?: boolean;
  canRegenerate?: boolean;
}

interface Conversation {
  id: string;
  title: string;
  timestamp: Date;
}

const suggestedPrompts = [
  {
    title: 'Analyze code',
    description: 'Review and improve code quality'
  },
  {
    title: 'Write tutorial',
    description: 'Create a step-by-step guide'
  },
  {
    title: 'Brainstorm ideas',
    description: 'Generate creative concepts'
  },
  {
    title: 'Summarize text',
    description: 'Extract key points'
  },
];

const mockConversations: Conversation[] = [
  { id: '1', title: 'UI Pattern Research', timestamp: new Date(Date.now() - 3600000) },
  { id: '2', title: 'Dead Reckoning Design', timestamp: new Date(Date.now() - 86400000) },
  { id: '3', title: 'Tactical Telemetry System', timestamp: new Date(Date.now() - 172800000) },
];

const initialMessages: Message[] = [
  {
    id: '1',
    role: 'user',
    content: 'What are the standard UI patterns in mainstream AI assistants?',
    timestamp: new Date(Date.now() - 600000),
  },
  {
    id: '2',
    role: 'assistant',
    content: `All mainstream assistants (ChatGPT, Gemini, Copilot, Claude) converge on a similar layout:

1. Left sidebar navigation with chat history
2. Center conversation transcript
3. Bottom input field
4. Message actions (Copy, Regenerate) on responses
5. Model selector in top bar
6. Settings in top-right corner

The key differences are in:
- Navigation paradigm (tree vs. flat list)
- Accent color (green, blue, red)
- Typography choices
- Empty state guidance`,
    timestamp: new Date(Date.now() - 300000),
    canRegenerate: true,
  },
];

export default function MainstreamShowcase() {
  const [messages, setMessages] = useState<Message[]>(initialMessages);
  const [input, setInput] = useState('');
  const [isGenerating, setIsGenerating] = useState(false);
  const [selectedConversation, setSelectedConversation] = useState(mockConversations[0]);
  const [selectedModel] = useState('Claude 3.5 Sonnet');
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [showEmptyState] = useState(false);

  const handleSend = () => {
    if (!input.trim()) return;

    const userMessage: Message = {
      id: Date.now().toString(),
      role: 'user',
      content: input,
      timestamp: new Date(),
    };

    setMessages(prev => [...prev, userMessage]);
    setInput('');
    setIsGenerating(true);

    // Simulate assistant response
    setTimeout(() => {
      const assistantMessage: Message = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: 'This is a simulated response. In a real application, the assistant would generate a thoughtful reply based on your input.',
        timestamp: new Date(),
        canRegenerate: true,
      };
      setMessages(prev => [...prev, assistantMessage]);
      setIsGenerating(false);
    }, 1500);
  };

  const handleCopy = (messageId: string, content: string) => {
    navigator.clipboard.writeText(content);
    setCopiedId(messageId);
    setTimeout(() => setCopiedId(null), 2000);
  };

  const handleRegenerate = (messageId: string) => {
    setIsGenerating(true);
    // Simulate regeneration
    setTimeout(() => {
      setMessages(prev =>
        prev.map(msg =>
          msg.id === messageId
            ? { ...msg, content: 'Regenerated response content...' }
            : msg
        )
      );
      setIsGenerating(false);
    }, 1500);
  };

  const handleSuggestedPrompt = (prompt: string) => {
    setInput(prompt);
  };

  return (
    <div className="mainstream-container">
      {/* Top Bar */}
      <div className="mainstream-topbar">
        <div className="mainstream-topbar-left">
          <button className="mainstream-icon-button" aria-label="Menu">
            <Menu size={18} />
          </button>
          <div className="mainstream-model-selector">
            <span>{selectedModel}</span>
            <ChevronDown size={16} />
          </div>
        </div>
        <div className="mainstream-topbar-right">
          <button className="mainstream-icon-button" aria-label="Settings">
            <Settings size={18} />
          </button>
          <button className="mainstream-icon-button" aria-label="Log out">
            <LogOut size={18} />
          </button>
        </div>
      </div>

      <div className="mainstream-layout">
        {/* Left Sidebar */}
        <aside className="mainstream-sidebar">
          <button className="mainstream-new-chat-button">
            <span>+ NEW CHAT</span>
          </button>

          <div className="mainstream-chat-history">
            <div className="mainstream-history-label">RECENT</div>
            {mockConversations.map(conv => (
              <button
                key={conv.id}
                className={`mainstream-chat-item ${selectedConversation.id === conv.id ? 'active' : ''}`}
                onClick={() => setSelectedConversation(conv)}
              >
                <span className="mainstream-chat-title">{conv.title}</span>
                <span className="mainstream-chat-time">
                  {conv.timestamp.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}
                </span>
              </button>
            ))}
          </div>
        </aside>

        {/* Main Conversation Area */}
        <main className="mainstream-main">
          {messages.length === 0 || showEmptyState ? (
            // Empty State
            <div className="mainstream-empty-state">
              <div className="mainstream-empty-icon">✦</div>
              <h1>What are you working on?</h1>
              <p>Start a conversation or explore capabilities</p>

              <div className="mainstream-suggested-prompts">
                {suggestedPrompts.map((prompt, idx) => (
                  <button
                    key={idx}
                    className="mainstream-prompt-card"
                    onClick={() => handleSuggestedPrompt(prompt.title)}
                  >
                    <div className="mainstream-prompt-title">{prompt.title}</div>
                    <div className="mainstream-prompt-description">{prompt.description}</div>
                  </button>
                ))}
              </div>
            </div>
          ) : (
            // Conversation
            <div className="mainstream-transcript">
              {messages.map(message => (
                <div
                  key={message.id}
                  className={`mainstream-message ${message.role === 'user' ? 'user' : 'assistant'}`}
                >
                  <div className="mainstream-message-content">
                    {message.role === 'assistant' && <div className="mainstream-avatar">✦</div>}
                    <div className="mainstream-message-text">{message.content}</div>
                    {message.role === 'user' && <div className="mainstream-avatar">YOU</div>}
                  </div>

                  {message.role === 'assistant' && (
                    <div className="mainstream-message-actions">
                      <button
                        className={`mainstream-action-button ${copiedId === message.id ? 'copied' : ''}`}
                        onClick={() => handleCopy(message.id, message.content)}
                        aria-label="Copy message"
                        title="Copy to clipboard"
                      >
                        <Copy size={16} />
                        <span>{copiedId === message.id ? 'COPIED' : 'COPY'}</span>
                      </button>
                      {message.canRegenerate && !isGenerating && (
                        <button
                          className="mainstream-action-button"
                          onClick={() => handleRegenerate(message.id)}
                          aria-label="Regenerate response"
                          title="Regenerate response"
                        >
                          <RotateCcw size={16} />
                          <span>REGENERATE</span>
                        </button>
                      )}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </main>
      </div>

      {/* Input Area */}
      <div className="mainstream-input-area">
        <div className="mainstream-input-wrapper">
          <textarea
            className="mainstream-input-field"
            placeholder="Ask me anything..."
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                handleSend();
              }
            }}
            disabled={isGenerating}
          />
          <div className="mainstream-input-actions">
            <button className="mainstream-icon-button" aria-label="Attach file" title="Attach file">
              <Paperclip size={18} />
            </button>
            <button className="mainstream-icon-button" aria-label="Voice input" title="Voice input">
              <Mic size={18} />
            </button>
            {isGenerating ? (
              <button
                className="mainstream-send-button generating"
                aria-label="Stop generation"
                onClick={() => setIsGenerating(false)}
                title="Stop generation"
              >
                <StopCircle size={18} />
                <span>STOP</span>
              </button>
            ) : (
              <button
                className="mainstream-send-button"
                onClick={handleSend}
                disabled={!input.trim()}
                aria-label="Send message"
                title="Send message (Enter)"
              >
                <Send size={18} />
                <span>SEND</span>
              </button>
            )}
          </div>
        </div>
        <div className="mainstream-input-hint">
          Shift + Enter for new line. Attach files for analysis.
        </div>
      </div>
    </div>
  );
}
