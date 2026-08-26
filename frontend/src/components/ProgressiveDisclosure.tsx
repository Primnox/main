/**
 * ProgressiveDisclosure Component
 *
 * Five-level disclosure pattern for Primnox UI.
 * Reveals information/options based on user expertise and context.
 *
 * Usage:
 * <ProgressiveDisclosure level="2-common" title="More options">
 *   <div>Advanced settings...</div>
 * </ProgressiveDisclosure>
 */

import React, { useState, useCallback, useEffect } from 'react';
import { ChevronDown, ChevronUp, AlertCircle } from 'lucide-react';

export type DisclosureLevel = '1-core' | '2-common' | '3-advanced' | '4-expert' | '5-debug';
export type UserExpertise = 'novice' | 'intermediate' | 'expert' | 'developer';
export type TriggerMode = 'click' | 'hover' | 'auto-on-error' | 'always';

interface ProgressiveDisclosureProps {
  /** Level of disclosure (1-5) */
  level: DisclosureLevel;

  /** Trigger text ("More", "Advanced", "Details", etc.) */
  title?: string;

  /** Children to reveal */
  children: React.ReactNode;

  /** User expertise (optional; uses localStorage or infers) */
  userExpertise?: UserExpertise;

  /** How to trigger reveal */
  triggerMode?: TriggerMode;

  /** Auto-expand on error? */
  expandOnError?: boolean;

  /** Error context (if provided, may auto-expand) */
  errorContext?: string | null;

  /** CSS class prefix */
  className?: string;

  /** Callback when opened */
  onOpen?: () => void;

  /** Callback when closed */
  onClose?: () => void;

  /** Icon to display (default: ChevronDown) */
  icon?: React.ReactNode;

  /** Optional description shown in collapsed state */
  collapsedDescription?: string;

  /** Always show this level, even if it exceeds user expertise */
  forceVisible?: boolean;

  /** Render as a card (Level 3+) or inline (Level 1-2) */
  cardStyle?: boolean;
}

/**
 * Determine if a level should be visible based on user expertise
 */
function shouldShowLevel(level: DisclosureLevel, expertise: UserExpertise): boolean {
  const levelMap = {
    '1-core': ['novice', 'intermediate', 'expert', 'developer'],
    '2-common': ['novice', 'intermediate', 'expert', 'developer'],
    '3-advanced': ['intermediate', 'expert', 'developer'],
    '4-expert': ['expert', 'developer'],
    '5-debug': ['developer'],
  };

  return levelMap[level].includes(expertise);
}

/**
 * Infer user expertise from localStorage or conversational data
 */
function inferExpertise(): UserExpertise {
  if (typeof window === 'undefined') return 'intermediate';

  const stored = localStorage.getItem('primnox:user-expertise');
  if (stored) return stored as UserExpertise;

  // Heuristic: infer from conversation count
  const conversationCount = parseInt(
    localStorage.getItem('primnox:conversation-count') || '0',
    10
  );

  if (conversationCount < 5) return 'novice';
  if (conversationCount < 50) return 'intermediate';
  return 'expert';
}

/**
 * ProgressiveDisclosure: Main component
 */
export const ProgressiveDisclosure: React.FC<ProgressiveDisclosureProps> = ({
  level,
  title = 'More',
  children,
  userExpertise,
  triggerMode = 'click',
  expandOnError = true,
  errorContext = null,
  className = '',
  onOpen,
  onClose,
  icon,
  collapsedDescription,
  forceVisible = false,
  cardStyle = false,
}) => {
  const [isOpen, setIsOpen] = useState(false);
  const expertise = userExpertise || inferExpertise();

  // Check if this level should be shown at all
  const shouldShow = forceVisible || shouldShowLevel(level, expertise);

  // Auto-expand on error
  useEffect(() => {
    if (expandOnError && errorContext && !isOpen) {
      setIsOpen(true);
      onOpen?.();
    }
  }, [errorContext, expandOnError, isOpen, onOpen]);

  // Handle different trigger modes
  const handleTrigger = useCallback(() => {
    const newState = !isOpen;
    setIsOpen(newState);
    if (newState) {
      onOpen?.();
    } else {
      onClose?.();
    }
  }, [isOpen, onOpen, onClose]);

  const handleHover = useCallback((entering: boolean) => {
    if (triggerMode === 'hover' && !isOpen) {
      if (entering) {
        setIsOpen(true);
        onOpen?.();
      }
    }
  }, [triggerMode, isOpen, onOpen]);

  // Don't render if below user expertise level (unless forced)
  if (!shouldShow && !forceVisible) {
    return null;
  }

  // Level 1 (Core): Always shown, no trigger needed
  if (level === '1-core') {
    return (
      <div className={`disclosure-level-1 ${className}`}>
        {children}
      </div>
    );
  }

  // Level 2 (Common): Inline button, no card
  if (level === '2-common') {
    return (
      <div className={`disclosure-level-2 ${className}`}>
        <button
          onClick={handleTrigger}
          onMouseEnter={() => handleHover(true)}
          className="disclosure-trigger-common"
          aria-expanded={isOpen}
          aria-label={`Toggle ${title}`}
        >
          {title}
          <span className="disclosure-icon">
            {icon || (isOpen ? <ChevronUp size={16} /> : <ChevronDown size={16} />)}
          </span>
        </button>

        {isOpen && (
          <div className="disclosure-content-inline">
            {collapsedDescription && (
              <p className="disclosure-description">{collapsedDescription}</p>
            )}
            {children}
          </div>
        )}
      </div>
    );
  }

  // Level 3+ (Advanced/Expert/Debug): Card-style or expandable section
  return (
    <div
      className={`disclosure-level-${level.split('-')[0]} disclosure-card ${className} ${
        cardStyle ? 'card-style' : ''
      }`}
      onMouseEnter={() => handleHover(true)}
    >
      <button
        onClick={handleTrigger}
        className={`disclosure-trigger-advanced ${isOpen ? 'open' : ''}`}
        aria-expanded={isOpen}
        aria-label={`Toggle ${title}`}
      >
        {errorContext && <AlertCircle size={16} className="error-indicator" />}
        <span className="disclosure-title">{title}</span>
        <span className="disclosure-icon">
          {icon || (isOpen ? <ChevronUp size={16} /> : <ChevronDown size={16} />)}
        </span>
      </button>

      {isOpen && (
        <div className="disclosure-content-card">
          {collapsedDescription && (
            <p className="disclosure-description">{collapsedDescription}</p>
          )}
          {children}
        </div>
      )}
    </div>
  );
};

/**
 * ProgressiveDisclosureGroup: For multiple disclosure items (e.g., in a settings panel)
 */
interface ProgressiveDisclosureGroupProps {
  level: DisclosureLevel;
  title?: string;
  children: React.ReactNode;
  userExpertise?: UserExpertise;
  className?: string;
}

export const ProgressiveDisclosureGroup: React.FC<ProgressiveDisclosureGroupProps> = ({
  level,
  title,
  children,
  userExpertise,
  className = '',
}) => {
  const expertise = userExpertise || inferExpertise();
  const shouldShow = shouldShowLevel(level, expertise);

  if (!shouldShow) return null;

  return (
    <div className={`disclosure-group disclosure-group-${level} ${className}`}>
      {title && <h3 className="disclosure-group-title">{title}</h3>}
      <div className="disclosure-group-content">{children}</div>
    </div>
  );
};

/**
 * Hook to get current user expertise and allow updates
 */
export const useUserExpertise = () => {
  const [expertise, setExpertise] = React.useState<UserExpertise>(() =>
    inferExpertise()
  );

  const updateExpertise = useCallback((newExpertise: UserExpertise) => {
    setExpertise(newExpertise);
    if (typeof window !== 'undefined') {
      localStorage.setItem('primnox:user-expertise', newExpertise);
    }
  }, []);

  return { expertise, updateExpertise };
};

/**
 * Hook for auto-expanding disclosures on error
 */
export const useErrorContext = () => {
  const [errorContext, setErrorContext] = React.useState<string | null>(null);

  const triggerExpand = useCallback((error: string) => {
    setErrorContext(error);
    // Clear after 5 seconds or manual close
    setTimeout(() => setErrorContext(null), 5000);
  }, []);

  const clearError = useCallback(() => {
    setErrorContext(null);
  }, []);

  return { errorContext, triggerExpand, clearError };
};

/**
 * Disclosure Level Indicator (visual badge showing level)
 */
interface DisclosureLevelBadgeProps {
  level: DisclosureLevel;
  className?: string;
}

export const DisclosureLevelBadge: React.FC<DisclosureLevelBadgeProps> = ({
  level,
  className = '',
}) => {
  const badges = {
    '1-core': { label: 'Core', color: 'bg-blue-500' },
    '2-common': { label: 'Common', color: 'bg-green-500' },
    '3-advanced': { label: 'Advanced', color: 'bg-yellow-500' },
    '4-expert': { label: 'Expert', color: 'bg-orange-500' },
    '5-debug': { label: 'Debug', color: 'bg-red-500' },
  };

  const badge = badges[level];

  return (
    <span className={`disclosure-badge ${badge.color} ${className}`}>
      {badge.label}
    </span>
  );
};
