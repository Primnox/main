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
  const [error, setError] = useState('');

  if (!isOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!content.trim()) return;

    setIsSubmitting(true);
    setError('');
    try {
      const res = await fetch('http://127.0.0.1:4009/api/feedback', {
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
      } else {
        setError('Failed to send — backend returned an error. Try again.');
      }
    } catch {
      setError('Could not reach backend. Make sure Primnox is running.');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-surface/60 backdrop-blur-sm">
      <div className="w-[480px] rounded-2xl bg-surface border border-on-surface/10 shadow-2xl overflow-hidden flex flex-col">
        <div className="flex items-center justify-between p-4 border-b border-on-surface/5 bg-on-surface/5">
          <div className="flex items-center gap-2">
            <MessageSquare className="w-5 h-5 text-primary" />
            <h2 className="text-sm font-medium text-on-surface/90">Send Feedback</h2>
          </div>
          <button onClick={onClose} className="p-1 rounded-md hover:bg-on-surface/10 text-on-surface/50 hover:text-on-surface/90 transition-colors">
            <X className="w-4 h-4" />
          </button>
        </div>
        
        {success ? (
          <div className="p-12 flex flex-col items-center justify-center text-center gap-4">
            <div className="w-12 h-12 rounded-full bg-success/20 flex items-center justify-center">
              <Send className="w-6 h-6 text-success ml-1" />
            </div>
            <div>
              <h3 className="text-on-surface/90 font-medium">Feedback Sent!</h3>
              <p className="text-on-surface/50 text-sm mt-1">Thank you for helping improve Primnox.</p>
            </div>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="p-5 flex flex-col gap-4">
            <div className="flex gap-2 p-1 bg-surface/40 rounded-lg border border-on-surface/5">
              {(['General', 'Bug', 'Feature'] as const).map(cat => (
                <button
                  key={cat}
                  type="button"
                  onClick={() => setCategory(cat)}
                  className={`flex-1 py-1.5 text-xs font-medium rounded-md transition-all ${
                    category === cat 
                      ? 'bg-primary text-on-surface shadow-md' 
                      : 'text-on-surface/60 hover:text-on-surface/70 hover:bg-on-surface/5'
                  }`}
                >
                  {cat}
                </button>
              ))}
            </div>

            <div className="flex flex-col gap-1.5">
              <label className="text-xs font-medium text-on-surface/50 uppercase tracking-wider pl-1">Details</label>
              <textarea
                value={content}
                onChange={(e) => setContent(e.target.value)}
                placeholder="What's on your mind?"
                className="w-full h-32 bg-surface/40 border border-on-surface/10 rounded-xl p-3 text-sm text-on-surface/90 placeholder:text-on-surface/48 resize-none focus:outline-none focus:border-primary/50 transition-colors"
                autoFocus
              />
            </div>

            <div className="flex flex-col gap-1.5">
              <label className="text-xs font-medium text-on-surface/50 uppercase tracking-wider pl-1">Contact (Optional)</label>
              <input
                type="text"
                value={contact}
                onChange={(e) => setContact(e.target.value)}
                placeholder="Email or Discord tag"
                className="w-full bg-surface/40 border border-on-surface/10 rounded-xl px-3 py-2.5 text-sm text-on-surface/90 placeholder:text-on-surface/48 focus:outline-none focus:border-primary/50 transition-colors"
              />
            </div>

            {error && (
              <p className="text-xs text-error/80 text-center -mt-1">{error}</p>
            )}
            <button
              type="submit"
              disabled={isSubmitting || !content.trim()}
              className="mt-2 w-full flex items-center justify-center gap-2 bg-primary hover:bg-primary/90 disabled:opacity-50 disabled:hover:bg-primary text-on-surface py-2.5 rounded-xl text-sm font-medium transition-all"
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
