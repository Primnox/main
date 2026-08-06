from pathlib import Path

# Was an absolute path on the original author's Windows machine: it leaked a
# username and the script could not run anywhere else.
_FRONTEND_DIR = Path(__file__).resolve().parent
import os

file_path = str(_FRONTEND_DIR / 'src/app/components/CommandCenter.tsx')

with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Rename the component
content = content.replace('export const ChatExpandedSidebar = ({', 'import { NotesIconSidebar } from "./NotesView";\n\nexport const CommandCenter = ({')

# The current structure ends with:
#       {/* RIGHT MAIN CHAT AREA */}
#       <div className="flex-1 flex flex-col h-full relative">
#        ...
#       </div>
#     </div>

# I need to add the Right Workspace Pane.
right_pane_code = """
      {/* RIGHT WORKSPACE PANE */}
      <div className="w-80 lg:w-96 border-l border-white/5 bg-zinc-950 flex flex-col h-full relative z-10 shrink-0">
        <NotesIconSidebar notes={useStore(s => s.notes)} onExport={() => {}} />
      </div>
    </div>
"""

# Replace the final closing div with the new right pane code
content = content.replace('      </div>\n    </div>', '      </div>\n' + right_pane_code)

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)

print("Updated CommandCenter.tsx")
