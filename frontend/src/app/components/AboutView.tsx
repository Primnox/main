import { Shield, Cpu, Terminal, Eye, Zap } from 'lucide-react';

export const KnowledgePage = ({ activeModel = "llama-3.3-70b-versatile" }: { activeModel?: string }) => {
  return (
    <div className="flex-1 flex flex-col h-full bg-black animate-in fade-in slide-in-from-right-8 duration-1000 overflow-hidden text-left">
      <div className="p-8 lg:p-12 border-b border-white/5 bg-zinc-950 flex items-center justify-between">
        <div className="flex flex-col">
          <span className="font-mono text-primary text-[10px] uppercase tracking-[0.4em] mb-2 block font-bold">Information_Nexus</span>
          <h2 className="text-white text-xl font-bold tracking-tighter italic">system_knowledge.md</h2>
        </div>
        <div className="flex items-center gap-6">
          <div className="px-4 py-2 bg-primary/10 border border-primary/20 rounded-lg">
            <span className="font-mono text-[10px] text-primary font-bold">SOVEREIGN V2 ARCH</span>
          </div>
        </div>
      </div>
      
      <div className="flex-1 overflow-y-auto p-8 lg:p-12 custom-scrollbar">
        <div className="max-w-4xl w-full space-y-12 pb-24">
          <section className="space-y-4">
            <h3 className="text-white text-lg font-bold tracking-tight italic flex items-center gap-3">
              <Cpu size={18} className="text-primary" />
              Sovereign Brain Co-Processing
            </h3>
            <p className="text-sm text-white/60 leading-relaxed font-light">
              Primnox is designed around a dual compute model. Heavy reasoning is co-processed on the Groq hardware-accelerated cloud utilizing high-throughput Llama models. Capturing, local spatial calculations, and security filtering occur entirely on local silicon, minimizing local CPU/RAM overhead while guaranteeing total privacy.
            </p>
          </section>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div className="p-6 bg-zinc-950 border border-white/5 rounded-2xl space-y-4">
              <h4 className="font-mono text-xs text-white/80 uppercase tracking-widest flex items-center gap-2">
                <Terminal size={14} className="text-primary" />
                Active Model Pipeline
              </h4>
              <ul className="space-y-2 text-xs font-mono text-white/50">
                <li className="flex justify-between border-b border-white/5 pb-2">
                  <span>Reasoning Brain:</span>
                  <span className="text-white font-bold">{activeModel}</span>
                </li>
                <li className="flex justify-between border-b border-white/5 pb-2">
                  <span>Vision Analysis:</span>
                  <span className="text-white font-bold">Llama-3.2-11b-vision</span>
                </li>
                <li className="flex justify-between border-b border-white/5 pb-2">
                  <span>Voice Synthesis:</span>
                  <span className="text-white font-bold">Whisper-large-v3-turbo</span>
                </li>
                <li className="flex justify-between">
                  <span>Spatial Engine:</span>
                  <span className="text-white font-bold">YOLOv8 nano + EasyOCR</span>
                </li>
              </ul>
            </div>

            <div className="p-6 bg-zinc-950 border border-white/5 rounded-2xl space-y-4">
              <h4 className="font-mono text-xs text-white/80 uppercase tracking-widest flex items-center gap-2">
                <Shield size={14} className="text-primary" />
                Zero-Trust Firewall
              </h4>
              <p className="text-xs text-white/40 leading-relaxed">
                The local FastAPI server strictly accepts loopback connections from localhost (`127.0.0.1` and `::1`). External network ingress is dropped at the TCP layer. Build pipeline static checks scan source code to block outbound network requests outside of authorized model hosts.
              </p>
            </div>
          </div>

          <section className="space-y-4 border-t border-white/5 pt-10">
            <h3 className="text-white text-lg font-bold tracking-tight italic flex items-center gap-3">
              <Eye size={18} className="text-primary" />
              Local Privacy Mirror
            </h3>
            <p className="text-sm text-white/60 leading-relaxed font-light">
              All transcriptions, foreground text fields, active windows, and clipboard data are passed through a regex-based **PII Scrubbing Engine** locally. Personal identifiers (emails, credit cards, decryption keys, IP addresses) are redacted on local silicon *before* any text context is synchronized with cloud co-processors.
            </p>
          </section>

          <section className="space-y-4 border-t border-white/5 pt-10">
            <h3 className="text-white text-lg font-bold tracking-tight italic flex items-center gap-3">
              <Zap size={18} className="text-primary" />
              Dynamic Island Shortcuts
            </h3>
            <div className="p-6 bg-zinc-950 border border-white/5 rounded-2xl font-mono text-xs text-white/60 space-y-3">
              <div className="flex justify-between">
                <span>Copy Response:</span>
                <span className="text-white">Click "Copy" pill in Dynamic Island</span>
              </div>
              <div className="flex justify-between border-t border-white/5 pt-2">
                <span>Clear Clipboard:</span>
                <span className="text-white">Click "Clear" button in Dynamic Island</span>
              </div>
              <div className="flex justify-between border-t border-white/5 pt-2">
                <span>Toggle Sidebar:</span>
                <span className="text-white">Click Terminal Logo (top-left)</span>
              </div>
              <div className="flex justify-between border-t border-white/5 pt-2">
                <span>Audio Wave RMS:</span>
                <span className="text-white">Fluctuates dynamically to reflect voice amplitude</span>
              </div>
            </div>
          </section>
        </div>
      </div>
    </div>
  );
};
