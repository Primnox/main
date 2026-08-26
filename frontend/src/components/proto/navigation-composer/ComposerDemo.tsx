/**
 * Navigation & Composer Demo
 *
 * Full-page demo showing:
 * - Left rail navigation
 * - Conversation list
 * - Transcript area
 * - Bottom glass composer with all states
 */

import { useState } from 'react';
import { Composer, type Attachment } from './Composer';
import { NavigationRail, type RailSection } from './NavigationRail';
import { ConversationList, type ConversationListItem } from './ConversationList';

const DEMO_CONVERSATIONS: ConversationListItem[] = [
  {
    id: '1',
    title: 'How to build a todo app',
    pinned_at: true,
    turn_count: 8,
    created_at: Date.now() - 1000 * 60 * 60,
  },
  {
    id: '2',
    title: 'React patterns and best practices',
    pinned_at: true,
    turn_count: 12,
    created_at: Date.now() - 1000 * 60 * 60 * 2,
  },
  {
    id: '3',
    title: 'Explaining TypeScript generics',
    turn_count: 5,
    created_at: Date.now() - 1000 * 60 * 60 * 24,
  },
  {
    id: '4',
    title: 'Debugging a memory leak',
    turn_count: 7,
    created_at: Date.now() - 1000 * 60 * 60 * 24 * 2,
  },
  {
    id: '5',
    title: 'Incognito: testing something',
    incognito: true,
    turn_count: 3,
    created_at: Date.now(),
  },
];

const DEMO_FOLDERS = [
  { id: 'f1', name: 'Work' },
  { id: 'f2', name: 'Learning' },
  { id: 'f3', name: 'Ideas' },
];

export function ComposerDemo() {
  const [section, setSection] = useState<RailSection>('chat');
  const [draft, setDraft] = useState('');
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const [activeConversation, setActiveConversation] = useState('1');
  const [demoState, setDemoState] = useState<
    'empty' | 'typing' | 'attachments' | 'incognito' | 'offline' | 'sending'
  >('empty');

  // Simulate sending
  const handleSend = async () => {
    if (!draft.trim()) return;
    setDemoState('sending');
    setTimeout(() => {
      setDraft('');
      setAttachments([]);
      setDemoState('empty');
    }, 1500);
  };

  // Simulate attachment
  const handleAttachClick = () => {
    setDemoState('attachments');
    setAttachments([
      { id: '1', name: 'example.pdf', status: 'ingesting' },
      { id: '2', name: 'data.json', status: 'ready' },
    ]);
    setDraft('I've attached the files for you to review.');
  };

  // Get demo props
  const getComposerProps = () => {
    const baseProps = {
      draft,
      onDraftChange: setDraft,
      attachments,
      onRemoveAttachment: (id: string) =>
        setAttachments(a => a.filter(x => x.id !== id)),
      onAttachClick: handleAttachClick,
      onSend: handleSend,
      sendDisabled: !draft.trim() || demoState === 'offline',
    };

    switch (demoState) {
      case 'typing':
        return {
          ...baseProps,
          draft: 'How do I optimize my React component rendering?',
          modelInfo: { model: 'claude-opus', local: false },
        };
      case 'attachments':
        return {
          ...baseProps,
          attachments,
          modelInfo: { model: 'claude-opus', local: false },
        };
      case 'incognito':
        return {
          ...baseProps,
          draft: 'Testing in incognito mode',
          conversationIncognito: true,
          attachmentDisabled: true,
          attachmentDisabledReason: 'Attachments are not available in incognito mode',
          modelInfo: { model: 'claude-opus', local: false },
        };
      case 'offline':
        return {
          ...baseProps,
          conversationGone: true,
          connectionStatus: 'offline' as const,
          sendDisabled: true,
          modelInfo: undefined,
        };
      case 'sending':
        return {
          ...baseProps,
          draft: 'Help me understand TypeScript generics',
          sendDisabled: true,
          liveTurnId: 'turn-123',
          onStop: () => console.log('stop'),
          modelInfo: { model: 'claude-opus', local: false },
        };
      default:
        return {
          ...baseProps,
          modelInfo: { model: 'claude-opus', local: false },
        };
    }
  };

  return (
    <div className="flex h-screen w-full bg-surface text-on-surface font-sans">
      {/* Rail */}
      <NavigationRail
        section={section}
        onSection={setSection}
        connected={demoState !== 'offline'}
        synced={true}
        showKnowledge={false}
      />

      {section === 'chat' ? (
        <>
          {/* Sidebar */}
          <div className="w-72 flex flex-col border-r border-on-surface/[0.07] bg-[var(--nav-bg)]">
            <ConversationList
              conversations={DEMO_CONVERSATIONS}
              folders={DEMO_FOLDERS}
              activeId={activeConversation}
              onOpenConversation={setActiveConversation}
            />
          </div>

          {/* Main area */}
          <main className="relative flex-1 flex flex-col min-w-0">
            {/* Header */}
            <header className="h-14 shrink-0 flex items-center justify-between gap-3 px-8 border-b border-on-surface/[0.07]">
              <span className="px-eyebrow block text-[11px] text-on-surface/60">Conversation</span>
              <h1 className="font-display font-bold text-[14px] uppercase tracking-[0.02em] text-on-surface/85">
                {DEMO_CONVERSATIONS.find(c => c.id === activeConversation)?.title || 'New Chat'}
              </h1>
              <div className="flex-1" />
            </header>

            {/* Transcript area with demo content */}
            <div className="flex-1 overflow-y-auto px-8 py-8">
              <div className="mx-auto w-full max-w-2xl">
                <p className="text-on-surface/60 text-sm mb-4">
                  This is a demo of the navigation and composer architecture.
                </p>
                <p className="text-on-surface/60 text-sm mb-6">
                  Try the different demo states using the buttons below to see how the composer responds
                  to various conditions (empty, typing, attachments, sending, incognito, offline).
                </p>

                {/* Demo state selector */}
                <div className="bg-on-surface/[0.05] rounded-lg p-4 mb-6">
                  <p className="text-[12px] font-medium text-on-surface/70 mb-3">Demo State:</p>
                  <div className="flex flex-wrap gap-2">
                    {(['empty', 'typing', 'attachments', 'incognito', 'offline', 'sending'] as const).map(
                      (state) => (
                        <button
                          key={state}
                          onClick={() => {
                            setDemoState(state);
                            setDraft('');
                            setAttachments([]);
                          }}
                          className={`px-3 py-1.5 rounded-lg text-[12px] font-medium transition duration-150 ${
                            demoState === state
                              ? 'bg-primary text-surface'
                              : 'bg-on-surface/[0.08] text-on-surface hover:bg-on-surface/[0.12]'
                          }`}
                        >
                          {state}
                        </button>
                      ),
                    )}
                  </div>
                </div>

                {/* Info about current state */}
                <div className="bg-on-surface/[0.05] rounded-lg p-4 text-[12px] text-on-surface/70">
                  {demoState === 'empty' && (
                    <p>Composer is empty and ready. Try typing or clicking "Attachments".</p>
                  )}
                  {demoState === 'typing' && (
                    <p>Shows composer with text in it, ready to send. Press Enter or click the send button.</p>
                  )}
                  {demoState === 'attachments' && (
                    <p>Shows attachment chips above the textarea. One is "ingesting" (spinner), one is "ready".</p>
                  )}
                  {demoState === 'incognito' && (
                    <p>Incognito mode: attachment button is disabled with explanation tooltip.</p>
                  )}
                  {demoState === 'offline' && (
                    <p>Offline: composer is disabled, shows "offline" status, send button is greyed out.</p>
                  )}
                  {demoState === 'sending' && (
                    <p>Showing: stop button (red square), send button is disabled. Model shows as "local" or "cloud".</p>
                  )}
                </div>
              </div>
            </div>

            {/* Composer */}
            <Composer {...getComposerProps()} />
          </main>
        </>
      ) : (
        <div className="flex-1 flex items-center justify-center">
          <p className="text-on-surface/50">
            {section === 'memory' && 'Memory section (not implemented in demo)'}
            {section === 'settings' && 'Settings section (not implemented in demo)'}
          </p>
        </div>
      )}
    </div>
  );
}
