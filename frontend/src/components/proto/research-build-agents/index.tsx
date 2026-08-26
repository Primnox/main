/**
 * Research & Build Agents Prototype
 *
 * Demonstrates a unified UI for displaying research results, code generation,
 * and execution traces with transparent source attribution.
 *
 * Features:
 * - Citation tracking with inline markers
 * - Source panel with reliability signals
 * - Execution traces for tool outputs
 * - Search progress UI
 * - TTL-based refresh prompts
 *
 * Run at: http://localhost:5303
 * (Or append ?proto=research-build-agents to main dev server)
 */

export { ResearchPanel } from './ResearchPanel';
export { ResultBlock } from './ResultBlock';
export { SourcePanel } from './SourcePanel';
export { CitationInline } from './CitationInline';
export { ExecutionBlock } from './ExecutionBlock';
