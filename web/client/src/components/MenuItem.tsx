

export function MenuItem({ icon, children, onClick, danger }: {
  icon: any; children: any; onClick: () => void; danger?: boolean;
}) {
  return (
    <button role="menuitem" onClick={onClick}
      className={`w-full text-left px-3 py-1.5 flex items-center gap-2 text-[12px] transition-colors duration-150
        ${danger ? 'text-error hover:bg-error/[0.10]' : 'text-on-surface/75 hover:bg-on-surface/[0.06]'}`}>
      {icon}{children}
    </button>
  );
}

