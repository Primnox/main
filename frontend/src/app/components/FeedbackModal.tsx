import React, { useState } from 'react';
import { X, MessageSquare, Send, Loader2 } from 'lucide-react';

interface FeedbackModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export const FeedbackModal = ({ isOpen, onClose }: FeedbackModalProps) => {
  const [category, setCategory] = useState<'General' | 'Bug' | 'Feature'>('General');
  const [content, setContent] = useState('');
  const [contact, setContact] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [success, setSuccess] = useState(false);

  if (!isOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!content.trim()) return;

    setIsSubmitting(true);
    try {
      const res = await fetch('http://127.0.0.1:8000/api/feedback', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ category, content, contact })
      });
      if (res.ok) {
        setSuccess(true);
        setTimeout(() => {
          setSuccess(false);
          setContent('');
          setContact('');
          setCategory('General');
          onClose();
        }, 2000);
      }
    } catch (error) {
      console.error('Failed to submit feedback:', error);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="w-[480px] rounded-2xl bg-zinc-950 border border-white/10 shadow-2xl overflow-hidden flex flex-col">
        <div className="flex items-center justify-between p-4 border-b border-white/5 bg-white/5">
          <div className="flex items-center gap-2">
            <MessageSquare className="w-5 h-5 text-primary" />
            <h2 className="text-sm font-medium text-white/90">Send Feedback</h2>
          </div>
          <button onClick={onClose} className="p-1 rounded-md hover:bg-white/10 text-white/50 hover:text-white/90 transition-colors">
            <X className="w-4 h-4" />
          </button>
        </div>
        
        {success ? (
          <div className="p-12 flex flex-col items-center justify-center text-center gap-4">
            <div className="w-12 h-12 rounded-full bg-green-500/20 flex items-center justify-center">
              <Send className="w-6 h-6 text-green-400 ml-1" />
            </div>
            <div>
              <h3 className="text-white/90 font-medium">Feedback Sent!</h3>
              <p className="text-white/50 text-sm mt-1">Thank you for helping improve Primnox.</p>
            </div>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="p-5 flex flex-col gap-4">
            <div className="flex gap-2 p-1 bg-black/40 rounded-lg border border-white/5">
              {(['General', 'Bug', 'Feature'] as const).map(cat => (
                <button
                  key={cat}
                  type="button"
                  onClick={() => setCategory(cat)}
                  className={`flex-1 py-1.5 text-xs font-medium rounded-md transition-all ${
                    category === cat 
                      ? 'bg-primary text-white shadow-md' 
                      : 'text-white/40 hover:text-white/70 hover:bg-white/5'
                  }`}
                >
                  {cat}
                </button>
              ))}
            </div>

            <div className="flex flex-col gap-1.5">
              <label className="text-xs font-medium text-white/50 uppercase tracking-wider pl-1">Details</label>
              <textarea
                value={content}
                onChange={(e) => setContent(e.target.value)}
                placeholder="What's on your mind?"
                className="w-full h-32 bg-black/40 border border-white/10 rounded-xl p-3 text-sm text-white/90 placeholder:text-white/20 resize-none focus:outline-none focus:border-primary/50 transition-colors"
                autoFocus
              />
            </div>

            <div className="flex flex-col gap-1.5">
              <label className="text-xs font-medium text-white/50 uppercase tracking-wider pl-1">Contact (Optional)</label>
              <input
                type="text"
                value={contact}
                onChange={(e) => setContact(e.target.value)}
                placeholder="Email or Discord tag"
                className="w-full bg-black/40 border border-white/10 rounded-xl px-3 py-2.5 text-sm text-white/90 placeholder:text-white/20 focus:outline-none focus:border-primary/50 transition-colors"
              />
            </div>

            <button
              type="submit"
              disabled={isSubmitting || !content.trim()}
              className="mt-2 w-full flex items-center justify-center gap-2 bg-primary hover:bg-primary/90 disabled:opacity-50 disabled:hover:bg-primary text-white py-2.5 rounded-xl text-sm font-medium transition-all"
            >
              {isSubmitting ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <>
                  <Send className="w-4 h-4" />
                  <span>Submit Feedback</span>
                </>
              )}
            </button>
          </form>
        )}
      </div>
    </div>
  );
};
