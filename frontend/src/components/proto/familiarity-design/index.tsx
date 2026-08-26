import { useState } from 'react';

export function FamiliarityDesignProto() {
  const [theme, setTheme] = useState<'tactical' | 'tactical-light'>('tactical');

  const isLight = theme === 'tactical-light';

  return (
    <div className="min-h-screen overflow-auto" data-theme={theme}>
      {/* Theme Toggle */}
      <div className="fixed top-4 right-4 z-50">
        <button
          onClick={() => setTheme(isLight ? 'tactical' : 'tactical-light')}
          className="px-4 py-2 border border-outline bg-surface hover:bg-surface-container text-on-surface font-mono text-sm uppercase tracking-wide"
        >
          {isLight ? '▲ Dark Mode' : '▼ Light Mode'}
        </button>
      </div>

      {/* Main Demo */}
      <div className="mx-auto max-w-4xl p-8 space-y-16">
        {/* Header */}
        <div className="space-y-4">
          <h1 className="text-3xl font-display uppercase text-on-surface">
            Familiarity & Design System
          </h1>
          <p className="font-prose text-on-surface-variant text-base max-w-prose">
            Unit 12: Exploring the three design choices under scrutiny—border radius, monospace typography, and dark/light substrates. This prototype demonstrates the current Tactical Telemetry design and the proposed light variant for accessibility.
          </p>
        </div>

        {/* Current State Card */}
        <div className="space-y-6">
          <div className="border border-outline p-6 bg-surface">
            <h2 className="font-mono text-sm uppercase tracking-wider text-primary mb-4">
              Current: Tactical Telemetry (Dark)
            </h2>
            <div className="space-y-3 font-mono text-on-surface">
              <div className="text-xs">
                <span className="text-on-surface-variant">● Substrate:</span> #0A0A0A (deactivated CRT)
              </div>
              <div className="text-xs">
                <span className="text-on-surface-variant">● Text:</span> #EAEAEA (white phosphor)
              </div>
              <div className="text-xs">
                <span className="text-on-surface-variant">● Radius:</span> 0px (no rounding, hard angles)
              </div>
              <div className="text-xs">
                <span className="text-on-surface-variant">● Typography:</span> JetBrains Mono by default
              </div>
              <div className="text-xs">
                <span className="text-on-surface-variant">● Accent:</span> #E61919 (hazard red, one only)
              </div>
            </div>
          </div>

          {/* Component Showcase - Dark */}
          <div className="space-y-4">
            <div className="font-mono text-xs uppercase text-on-surface-variant tracking-wider">
              Components in Current Theme
            </div>

            {/* Buttons */}
            <div className="grid grid-cols-3 gap-3">
              <button className="px-4 py-2 border border-outline bg-surface hover:bg-surface-container text-on-surface font-mono text-sm">
                Button
              </button>
              <button className="px-4 py-2 bg-primary text-on-primary font-mono text-sm">
                Primary
              </button>
              <button className="px-4 py-2 border border-primary text-primary font-mono text-sm">
                Outlined
              </button>
            </div>

            {/* Input */}
            <input
              type="text"
              placeholder="Input field"
              className="w-full px-3 py-2 border border-outline bg-surface text-on-surface font-mono text-sm placeholder:text-on-surface-variant"
            />

            {/* Card/Panel */}
            <div className="border border-outline p-4 bg-surface-container">
              <div className="font-mono text-sm text-on-surface mb-2">Panel Example</div>
              <div className="text-xs text-on-surface-variant">
                This is a panel with a hairline border. No soft shadows, no rounded corners, no elevation. Sharp 90-degree geometry.
              </div>
            </div>

            {/* Data Table */}
            <div className="space-y-2 font-mono text-xs">
              <div className="border border-outline p-2 bg-surface-container">
                <div className="text-on-surface">[ ] DESIGN.md</div>
                <div className="text-on-surface-variant text-xs">Updated 2026-08-26</div>
              </div>
              <div className="border border-outline p-2 bg-surface-container">
                <div className="text-on-surface">[ ] Proto Component</div>
                <div className="text-on-surface-variant text-xs">In progress</div>
              </div>
            </div>

            {/* Alert */}
            <div className="border border-primary bg-primary/5 p-3">
              <div className="font-mono text-sm text-primary">⚠ ALERT</div>
              <div className="text-xs text-on-surface mt-1">
                Hazard red (#E61919) is the one accent color. Rationed strictly.
              </div>
            </div>
          </div>
        </div>

        {/* Proposed Light Variant */}
        <div className="space-y-6 border-t border-outline pt-16">
          <div className="space-y-4">
            <div className="border border-outline p-6 bg-surface">
              <h2 className="font-mono text-sm uppercase tracking-wider text-primary mb-4">
                Proposed: Tactical Telemetry Light (Accessibility)
              </h2>
              <div className="space-y-3 font-mono text-on-surface">
                <div className="text-xs">
                  <span className="text-on-surface-variant">● Substrate:</span> #F5F5F5 (light, inverted)
                </div>
                <div className="text-xs">
                  <span className="text-on-surface-variant">● Text:</span> #1A1A1A (dark, inverted)
                </div>
                <div className="text-xs">
                  <span className="text-on-surface-variant">● Radius:</span> 0px (unchanged—hard angles preserved)
                </div>
                <div className="text-xs">
                  <span className="text-on-surface-variant">● Typography:</span> JetBrains Mono (unchanged)
                </div>
                <div className="text-xs">
                  <span className="text-on-surface-variant">● Accent:</span> #E61919 (unchanged—one only)
                </div>
                <div className="text-xs mt-3 text-primary">
                  ✓ WCAG AA: #F5F5F5 on #1A1A1A = 15.23:1 contrast ratio
                </div>
              </div>
            </div>

            <div className="font-prose text-on-surface-variant text-sm max-w-prose bg-surface-container border border-outline-variant p-4">
              <strong>Why this change?</strong> Users with photophobia, migraines, or low vision need light UI for medical reasons. Claiming WCAG AA compliance while excluding them is a compliance gap. This is an accessibility accommodation, not a style choice. The archetype is preserved: still monospace, still zero radius, still one accent.
            </div>
          </div>

          {/* Implementation Preview */}
          <div className="space-y-4">
            <div className="font-mono text-xs uppercase text-on-surface-variant tracking-wider">
              How to Enable (in Development)
            </div>

            <div className="bg-surface-container border border-outline p-4 font-mono text-xs">
              <div className="text-on-surface">
                {`<html data-theme="tactical-light">`}
                <br />
                {`  <!-- Content renders in light theme -->`}
                <br />
                {`</html>`}
              </div>
            </div>

            <div className="text-xs text-on-surface-variant">
              Or toggle programmatically:
              <br />
              <code className="text-primary">document.documentElement.setAttribute('data-theme', 'tactical-light')</code>
            </div>
          </div>
        </div>

        {/* Summary Table */}
        <div className="space-y-4 border-t border-outline pt-16">
          <h2 className="font-mono text-sm uppercase tracking-wider text-on-surface">
            Design Verdicts
          </h2>

          <div className="space-y-3">
            {[
              {
                choice: 'Border Radius',
                verdict: 'KEEP',
                reason: 'Zero radius is core to the archetype. Decorative, not functional. Learning burden negligible.'
              },
              {
                choice: 'Monospace by Default',
                verdict: 'KEEP',
                reason: 'Essential to data-focused identity. Reduces font-switching. Improves accuracy over familiarity.'
              },
              {
                choice: 'Dark-Only',
                verdict: 'CHANGE',
                reason: 'Light variant needed for accessibility. Medical accommodation, not style preference.'
              }
            ].map(({ choice, verdict, reason }) => (
              <div key={choice} className="border border-outline p-4 bg-surface">
                <div className="flex items-start gap-4">
                  <div className="flex-shrink-0">
                    <div className={`font-mono text-sm font-bold tracking-wider ${
                      verdict === 'KEEP' ? 'text-green-500' : 'text-primary'
                    }`}>
                      {verdict}
                    </div>
                  </div>
                  <div className="flex-1">
                    <div className="font-mono text-sm text-on-surface font-semibold">
                      {choice}
                    </div>
                    <div className="text-xs text-on-surface-variant mt-1">
                      {reason}
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Contrast Verification */}
        <div className="space-y-4 border-t border-outline pt-16">
          <h2 className="font-mono text-sm uppercase tracking-wider text-on-surface">
            Contrast Verification
          </h2>

          <div className="grid grid-cols-2 gap-4">
            <div className="border border-outline p-4 bg-surface">
              <div className="font-mono text-xs text-on-surface-variant mb-3">
                Dark Theme
              </div>
              <div className="space-y-2 text-xs font-mono">
                <div>
                  <span className="text-on-surface-variant">#0A0A0A on #EAEAEA</span>
                  <br />
                  <span className="text-on-surface">Ratio: 16.46:1</span>
                </div>
                <div>
                  <span className="text-on-surface-variant">Text failures: 0</span>
                </div>
              </div>
            </div>

            <div className="border border-outline p-4 bg-surface">
              <div className="font-mono text-xs text-on-surface-variant mb-3">
                Light Theme (Proposed)
              </div>
              <div className="space-y-2 text-xs font-mono">
                <div>
                  <span className="text-on-surface-variant">#F5F5F5 on #1A1A1A</span>
                  <br />
                  <span className="text-on-surface">Ratio: 15.23:1</span>
                </div>
                <div>
                  <span className="text-on-surface-variant">Predicted: 0 failures</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="border-t border-outline pt-8 text-xs text-on-surface-variant font-mono">
          <div>UNIT 12 — Familiarity & Design System</div>
          <div>Research: docs/ui-research/12-familiarity-design-system.md</div>
          <div>Styles: frontend/src/styles/themes.css (tactical-light, tactical-light-dim)</div>
        </div>
      </div>
    </div>
  );
}

export default FamiliarityDesignProto;
