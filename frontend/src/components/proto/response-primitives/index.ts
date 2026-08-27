/* Unit 4 — response primitives.
 *
 * `rule.ts` is the deliverable; everything else demonstrates it. The demo
 * takes no props and holds no network calls, so the gallery can mount it
 * directly. */
export { ResponsePrimitivesDemo } from './Demo';
export { PrimitiveRenderer } from './PrimitiveRenderer';
export {
  decide, explain, describeUnknown,
  INLINE_CEIL, SCROLLER_AT,
  type Level, type PrimitiveDescriptor, type Decision, type Floor, type Extent,
} from './rule';
export { BENCH } from './fixtures';
