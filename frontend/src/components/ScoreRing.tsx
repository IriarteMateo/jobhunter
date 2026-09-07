import { scoreTone } from "@/lib/api";

export function ScoreRing({ score, size = 56, label }: { score: number; size?: number; label?: string }) {
  const radius = (size - 6) / 2;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference * (1 - Math.max(0, Math.min(100, score)) / 100);
  const tone = scoreTone(score);
  return (
    <div className="relative shrink-0" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        <circle cx={size / 2} cy={size / 2} r={radius} strokeWidth={5} fill="none"
                className="stroke-ink-200 dark:stroke-ink-800" />
        <circle cx={size / 2} cy={size / 2} r={radius} strokeWidth={5} fill="none"
                strokeLinecap="round" strokeDasharray={circumference} strokeDashoffset={offset}
                className={`${tone.ring} stroke-current transition-all duration-500`} />
      </svg>
      <div className="absolute inset-0 grid place-items-center">
        <span className="text-sm font-bold tabular-nums">{Math.round(score)}</span>
      </div>
      {label && <p className="mt-1 text-center text-[10px] uppercase tracking-wide text-ink-500">{label}</p>}
    </div>
  );
}
