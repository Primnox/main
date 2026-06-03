import re

file_path = 'C:/Users/aniketh/Projects/Primnox/frontend/src/app/App.tsx'
with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Remove old imports and add CommandCenter
content = content.replace("import { ChatExpandedSidebar } from './components/ChatView';", "import { CommandCenter } from './components/CommandCenter';")
content = content.replace("import { NotesIconSidebar } from './components/NotesView';", "")
content = content.replace("import { SummariesExpanded, SummariesSidebarHidden, SummariesEmptyState, SummariesIconSidebar } from './components/SummaryViews';", "")

# Replace the giant renderScreen function
old_render_screen = """  const renderScreen = () => {
    // Navigate based on mode ONLY if we are on a generic summary screen
    let targetScreen = currentScreen;
    if (currentScreen.includes('summaries')) {
       if (appMode === 'notes') targetScreen = 'notes_icon_sidebar';
       if (appMode === 'chat') targetScreen = 'chat_expanded_sidebar';
       if (appMode === 'research') targetScreen = 'research_workspace';
    }

    if (settings && settings.onboarding_completed === false) {
      return <OnboardingView onComplete={() => setCurrentScreen('summaries_expanded')} />;
    }

    switch (targetScreen) {
      case 'chat_expanded_sidebar':
        return <ChatExpandedSidebar aiName={aiCodename} userName={operatorAlias} setStatus={setStatus} />;
      case 'notes_icon_sidebar':
        return <NotesIconSidebar notes={notes} onExport={exportNotes} sendMessage={sendMessage} />;
      case 'summaries_expanded':
        return <SummariesExpanded />;
      case 'summaries_sidebar_hidden':
        return <SummariesSidebarHidden onNavigate={setCurrentScreen} />;
      case 'summaries_empty_state':
        return <SummariesEmptyState />;
      case 'summaries_icon_sidebar':
        return <SummariesIconSidebar />;
      case 'island_settings':
        return <IslandSettings onSync={handleSync} onClose={() => setCurrentScreen('summaries_expanded')} />;
      case 'research_workspace':
        return <ResearchWorkspace />;
      case 'logs':
        return <LogsPage onClose={() => setCurrentScreen('summaries_expanded')} />;
      case 'archive':
        return <DataVaultPage onClose={() => setCurrentScreen('summaries_expanded')} />;
      case 'knowledge':
        return <KnowledgePage onClose={() => setCurrentScreen('summaries_expanded')} />;
      default:
        return <SummariesExpanded />;
    }
  };"""

new_render_screen = """  const renderScreen = () => {
    if (settings && settings.onboarding_completed === false) {
      return <OnboardingView onComplete={() => setCurrentScreen('command_center')} />;
    }

    // Modal Overlays
    if (currentScreen === 'island_settings') return <IslandSettings onSync={handleSync} onClose={() => setCurrentScreen('command_center')} />;
    if (currentScreen === 'logs') return <LogsPage onClose={() => setCurrentScreen('command_center')} />;
    if (currentScreen === 'archive') return <DataVaultPage onClose={() => setCurrentScreen('command_center')} />;
    if (currentScreen === 'knowledge') return <KnowledgePage onClose={() => setCurrentScreen('command_center')} />;

    // The core omnichannel UI
    return <CommandCenter aiName={aiCodename} userName={operatorAlias} setStatus={setStatus} />;
  };"""

content = content.replace(old_render_screen, new_render_screen)

# ScreenId Types
content = content.replace("  | 'summaries_expanded'", "  | 'command_center'\n  | 'summaries_expanded'")
content = content.replace("const [currentScreen, setCurrentScreen] = useState<ScreenId>('summaries_expanded');", "const [currentScreen, setCurrentScreen] = useState<ScreenId>('command_center');")
content = content.replace("setCurrentScreen('summaries_expanded')", "setCurrentScreen('command_center')")

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)

print("Updated App.tsx to use CommandCenter")
