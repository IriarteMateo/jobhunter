"use client";

import { useState } from "react";
import { MODALITY, api, scoreTone, timeAgo } from "@/lib/api";
import type { Job, JobDetail } from "@/lib/types";
import { ScoreRing } from "./ScoreRing";
import { JobAnalysisPanel } from "./JobAnalysisPanel";

const STATUS_LABEL: Record<string, string> = {
  NEW: "Nuevo", SEEN: "Visto", SAVED: "Guardado", APPLIED: "Aplicado",
  INTERVIEW: "Entrevista", REJECTED: "Rechazado", DISCARDED: "Descartado", CLOSED: "Cerrado",
};

export function JobCard({ job, onChange }: { job: Job; onChange?: (job: Job) => void }) {
  const [open, setOpen] = useState(false);
  const [detail, setDetail] = useState<JobDetail | null>(null);
  const [current, setCurrent] = useState<Job>(job);
  const [busy, setBusy] = useState(false);

  const analysis = current.analysis;
  const score = analysis?.final_score ?? 0;
  const tone = scoreTone(score);

  async function toggleDetail() {
    if (!open && !detail) {
      const data = await api.get<JobDetail>(`/api/jobs/${current.id}`);
      setDetail(data);
      setCurrent((prev) => ({ ...prev, status: data.status }));
    }
    setOpen((value) => !value);
  }

  async function setStatus(status: string, reason?: string) {
    setBusy(true);
    try {
      const updated = await api.post<JobDetail>(`/api/jobs/${current.id}/status`, { status, reason });
      setCurrent(updated);
      setDetail(updated);
      onChange?.(updated);
    } finally {
      setBusy(false);
    }
  }

  return (
    <article className="card overflow-hidden">
      <div className="flex gap-4 p-4 sm:p-5">
        <div className="hidden sm:block">
          <ScoreRing score={score} />
        </div>

        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className={`chip ${tone.chip}`}>
              {current.category_emoji} {current.category_label}
            </span>
            {current.is_new_today && (
              <span className="chip border-sky-200 bg-sky-50 text-sky-700 dark:border-sky-900 dark:bg-sky-950/40 dark:text-sky-300">
                Encontrado hoy
              </span>
            )}
            {current.is_target_company && <span className="chip-neutral">⭐ Empresa objetivo</span>}
            {(analysis?.german_advantage_score ?? 0) >= 50 && (
              <span className="chip border-amber-200 bg-amber-50 text-amber-800 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-300">
                🇩🇪 Alemán suma
              </span>
            )}
            {current.is_repost && <span className="chip-neutral">Republicado</span>}
            {current.status !== "NEW" && (
              <span className="chip-neutral">{STATUS_LABEL[current.status] ?? current.status}</span>
            )}
          </div>

          <h3 className="mt-2 text-base font-semibold leading-snug sm:text-lg">
            {current.job_title}
          </h3>
          <p className="text-sm text-ink-600 dark:text-ink-300">
            {current.company}
            {current.company_quality_confidence === "LOW" && (
              <span className="ml-2 text-xs text-ink-400" title="Poca información verificable sobre la empresa">
                · info limitada
              </span>
            )}
          </p>

          <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-xs text-ink-500">
            <span>📍 {current.location || "Sin ubicación"}</span>
            <span>🏢 {MODALITY[current.remote_type] ?? current.remote_type}</span>
            <span>🎯 {current.seniority}</span>
            <span>⏳ {current.experience_label}</span>
            <span>🗓️ {current.publication_date ? `Publicado ${timeAgo(current.publication_date)}` : `Encontrado ${timeAgo(current.first_seen_date)}`}</span>
            <span>🔗 {current.sources.join(", ")}</span>
            {current.salary_is_published && (
              <span className="font-medium text-accent-700 dark:text-accent-400">
                💰 {current.salary_min?.toLocaleString("es-AR")}
                {current.salary_max ? `–${current.salary_max.toLocaleString("es-AR")}` : ""} {current.salary_currency} (publicado)
              </span>
            )}
          </div>

          {analysis && (
            <div className="mt-3 grid grid-cols-3 gap-2 sm:max-w-md">
              <MiniScore label="Fit" value={analysis.fit_score} />
              <MiniScore label="Empresa" value={analysis.company_quality_score} />
              <MiniScore label="Carrera" value={analysis.career_value_score} />
            </div>
          )}

          {analysis?.why_apply && (
            <p className="mt-3 text-sm text-ink-700 dark:text-ink-200">{analysis.why_apply}</p>
          )}

          <div className="mt-4 flex flex-wrap items-center gap-2">
            <a
              href={current.apply_url || current.url}
              target="_blank"
              rel="noopener noreferrer"
              className="btn-accent"
            >
              Aplicar ↗
            </a>
            <button className="btn-ghost" onClick={toggleDetail}>
              {open ? "Ocultar análisis" : "Ver análisis"}
            </button>
            <button className="btn-ghost" disabled={busy} onClick={() => setStatus("SAVED")}>
              Guardar
            </button>
            <button className="btn-ghost" disabled={busy} onClick={() => setStatus("APPLIED")}>
              Ya apliqué
            </button>
            <button
              className="btn-ghost text-ink-500"
              disabled={busy}
              onClick={() => setStatus("DISCARDED", "no me interesa")}
            >
              Descartar
            </button>
          </div>
        </div>
      </div>

      {open && (
        <div className="border-t border-ink-200/70 bg-ink-50/60 p-4 dark:border-ink-800 dark:bg-ink-950/40 sm:p-5">
          <JobAnalysisPanel job={detail ?? current} />
        </div>
      )}
    </article>
  );
}

function MiniScore({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-lg border border-ink-200/70 bg-ink-50 px-2 py-1.5 text-center dark:border-ink-800 dark:bg-ink-950">
      <p className="text-[10px] uppercase tracking-wide text-ink-500">{label}</p>
      <p className="text-sm font-bold tabular-nums">{Math.round(value)}</p>
    </div>
  );
}
