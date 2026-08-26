export function Wordmark({ className = "" }: { className?: string }) {
  return (
    <span className={`font-semibold tracking-tight ${className}`}>
      <span className="text-cotton">Médico</span>
      <span className="text-brand">360</span>
    </span>
  );
}
