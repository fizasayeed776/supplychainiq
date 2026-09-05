export default function PageHeader({ eyebrow, title, action }) {
  return (
    <div className="flex items-end justify-between px-8 pt-8 pb-6 border-b border-line">
      <div>
        {eyebrow && <div className="text-xs text-ledgerLight font-mono mb-1">{eyebrow}</div>}
        <h1 className="font-display text-3xl text-ink">{title}</h1>
      </div>
      {action}
    </div>
  );
}
