/* An open/close reveal for content whose height is not known in advance.
 *
 * `grid-template-rows: 0fr -> 1fr` rather than animating `height` to a
 * measured pixel value: the content is a document or a file preview, so its
 * height is whatever it turns out to be, and a JS measure pass would have to
 * re-run on every image load, font swap and sheet switch inside it. The grid
 * technique needs no measurement and animates one property.
 *
 * It is honestly a layout animation, which §5 of the audit playbook otherwise
 * rules out. The exemption is frequency: opening an artifact is an occasional,
 * deliberate action on one small element, not something that fires while
 * tokens stream. A transform-only reveal cannot make its parent give up the
 * space, which is the whole job here.
 *
 * A transition and not a keyframe, so an artifact toggled twice quickly
 * retargets from wherever it currently is instead of snapping back to zero
 * and starting again.
 *
 * The inner element carries the opacity and the small lift, so the content
 * arrives slightly after the box that holds it - the box makes room, then the
 * content settles into it.
 */
export function Reveal({ open, children }: { open: boolean; children: React.ReactNode }) {
  return (
    <div
      className="grid transition-[grid-template-rows] duration-200 ease-[cubic-bezier(0.23,1,0.32,1)]"
      style={{ gridTemplateRows: open ? '1fr' : '0fr' }}
    >
      <div className="overflow-hidden">
        <div
          className="transition-[opacity,transform] duration-200 ease-[cubic-bezier(0.23,1,0.32,1)]"
          style={{
            opacity: open ? 1 : 0,
            transform: open ? 'translate3d(0,0,0)' : 'translate3d(0,-4px,0)',
          }}
        >
          {children}
        </div>
      </div>
    </div>
  );
}
