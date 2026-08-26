import React, { useState } from 'react';
import { ExecutionCard } from './ExecutionCard';
import { CodeCard } from './CodeCard';
import { ErrorCard } from './ErrorCard';
import { TableCard } from './TableCard';

/**
 * ArtifactCardsShowcase
 *
 * Live demonstration of all artifact card types:
 * - ExecutionCard: Tool execution results
 * - CodeCard: Code snippets
 * - ErrorCard: Error messages with recovery
 * - TableCard: Tabular data
 *
 * Usage: Navigate to /artifact-cards to see this
 */

export const ArtifactCardsShowcase: React.FC<{ isMobile?: boolean }> = ({ isMobile = false }) => {
  const [retryCount, setRetryCount] = useState(0);

  const pythonCode = `def fibonacci(n: int) -> list[int]:
    """Generate Fibonacci sequence up to n terms."""
    if n <= 0:
        return []
    elif n == 1:
        return [0]

    fib = [0, 1]
    for i in range(2, n):
        fib.append(fib[-1] + fib[-2])

    return fib[:n]

# Test
print(fibonacci(10))`;

  const outputLog = `Parsing input: Fibonacci sequence
Running with n=10
Generating sequence...
[0, 1, 1, 2, 3, 5, 8, 13, 21, 34]
Execution completed in 2.3ms
✓ Success`;

  const sampleTableData = {
    headers: ['User', 'Email', 'Status', 'Joined', 'Posts'],
    rows: [
      ['Alice Chen', 'alice@example.com', 'active', '2024-01-15', 42],
      ['Bob Smith', 'bob@example.com', 'active', '2024-02-20', 18],
      ['Carol Jones', 'carol@example.com', 'inactive', '2024-01-30', 7],
      ['David Lee', 'david@example.com', 'active', '2024-03-10', 156],
      ['Eve Wilson', 'eve@example.com', 'active', '2024-02-05', 89],
    ],
  };

  return (
    <div className="w-full max-w-4xl mx-auto px-4 py-8 space-y-8">
      <header className="space-y-2">
        <h1 className="text-2xl font-bold text-on-surface">Artifact Cards Prototype</h1>
        <p className="text-on-surface/70">
          Unified card system for displaying context-rich results: execution logs, code, errors, and tables.
        </p>
      </header>

      {/* Section: Execution Card */}
      <section className="space-y-4">
        <div>
          <h2 className="text-lg font-semibold text-on-surface mb-2">ExecutionCard</h2>
          <p className="text-sm text-on-surface/70">
            Shows tool/script execution results with status, runtime, file changes, and retry.
          </p>
        </div>

        <ExecutionCard
          id="exec-1"
          title="Python (fibonacci.py)"
          status="success"
          runtime={2.3}
          outputLog={outputLog}
          fileChanges={{
            created: ['result.txt', 'output.json'],
            modified: ['fibonacci.py'],
            deleted: [],
          }}
          artifactCount={2}
          onRetry={() => setRetryCount(retryCount + 1)}
          onDownloadLog={() => console.log('Download log')}
          isMobile={isMobile}
        />

        {/* Error execution */}
        <ExecutionCard
          id="exec-2"
          title="Node.js (build)"
          status="error"
          runtime={1245}
          errorMessage="Cannot find module 'lodash'"
          outputLog={`Building project...
Resolving dependencies...
Error: Cannot find module 'lodash'
  at Module._load (internal/modules/cjs/loader.js:219:25)`}
          fileChanges={{
            created: [],
            modified: [],
            deleted: [],
          }}
          onRetry={() => console.log('Retry build')}
          isMobile={isMobile}
        />
      </section>

      {/* Section: Code Card */}
      <section className="space-y-4">
        <div>
          <h2 className="text-lg font-semibold text-on-surface mb-2">CodeCard</h2>
          <p className="text-sm text-on-surface/70">
            Display code snippets with syntax highlighting, copy, and download.
          </p>
        </div>

        <CodeCard
          id="code-1"
          title="fibonacci.py"
          code={pythonCode}
          language="python"
          fileName="fibonacci.py"
          onCopy={(code) => console.log('Copied:', code.slice(0, 30))}
          onDownload={(_code, name) => console.log('Downloading:', name)}
          isMobile={isMobile}
        />

        {/* TypeScript example */}
        <CodeCard
          id="code-2"
          title="useAsync.ts"
          code={`import { useState, useEffect } from 'react';

export function useAsync<T>(
  fn: () => Promise<T>,
  deps?: React.DependencyList
) {
  const [state, setState] = useState<T | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  useEffect(() => {
    let mounted = true;
    setLoading(true);

    fn()
      .then(data => mounted && setState(data))
      .catch(err => mounted && setError(err))
      .finally(() => mounted && setLoading(false));

    return () => { mounted = false; };
  }, deps);

  return { data: state, loading, error };
}`}
          language="typescript"
          fileName="useAsync.ts"
          isMobile={isMobile}
        />
      </section>

      {/* Section: Error Card */}
      <section className="space-y-4">
        <div>
          <h2 className="text-lg font-semibold text-on-surface mb-2">ErrorCard</h2>
          <p className="text-sm text-on-surface/70">
            Surface errors with context, stack traces, and recovery options.
          </p>
        </div>

        <ErrorCard
          id="err-1"
          title="API Request Failed"
          errorMessage="Request timed out after 30 seconds"
          errorType="TimeoutError"
          stackTrace={`at Timeout._onTimeout [as _callback] (/app/api/client.js:145:23)
at listOnTimeout (internal/timers.js:549:40)
at processTimers.js:21:34`}
          context={{
            tool: 'fetch-data',
            input: 'GET /api/users?limit=100&offset=0',
            timestamp: Date.now() - 5000,
          }}
          onRetry={() => console.log('Retry API request')}
          isMobile={isMobile}
        />

        {/* Validation error */}
        <ErrorCard
          id="err-2"
          title="Validation Error"
          errorMessage="Invalid email format in user_email field"
          errorType="ValidationError"
          context={{
            tool: 'validate-schema',
            input: JSON.stringify({ user_email: 'not-an-email' }, null, 2),
            timestamp: Date.now(),
          }}
          onRetry={() => console.log('Retry validation')}
          isMobile={isMobile}
        />
      </section>

      {/* Section: Table Card */}
      <section className="space-y-4">
        <div>
          <h2 className="text-lg font-semibold text-on-surface mb-2">TableCard</h2>
          <p className="text-sm text-on-surface/70">
            Display tabular data with export options (CSV, JSON).
          </p>
        </div>

        <TableCard
          id="table-1"
          title="Users"
          headers={sampleTableData.headers}
          rows={sampleTableData.rows}
          onExportCSV={(data) => console.log('CSV:', data.slice(0, 50))}
          onExportJSON={(data) => console.log('JSON:', data.slice(0, 50))}
          isMobile={isMobile}
        />

        {/* Product catalog */}
        <TableCard
          id="table-2"
          title="Product Catalog"
          headers={['ID', 'Name', 'Category', 'Price', 'Stock']}
          rows={[
            [1, 'Laptop Pro', 'Electronics', 1299.99, 45],
            [2, 'Wireless Mouse', 'Accessories', 29.99, 120],
            [3, 'USB-C Cable', 'Cables', 12.99, 340],
            [4, 'Monitor 4K', 'Displays', 499.99, 18],
            [5, 'Keyboard Mechanical', 'Accessories', 149.99, 67],
          ]}
          isMobile={isMobile}
        />
      </section>

      {/* Footer */}
      <footer className="border-t border-on-surface/[0.09] pt-8 text-center text-sm text-on-surface/60">
        <p>Artifact Cards Prototype · Based on Progressive Disclosure Framework</p>
        <p className="mt-2">
          Retry count: {retryCount} · Mobile: {isMobile ? 'yes' : 'no'}
        </p>
      </footer>
    </div>
  );
};

export default ArtifactCardsShowcase;
