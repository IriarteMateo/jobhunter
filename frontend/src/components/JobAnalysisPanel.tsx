"use client";

import type { Job, JobDetail } from "@/lib/types";

const BREAKDOWN_LABEL: Record<string, string> = {
  role: "Rol",
  seniority: "Seniority / experiencia",
  education: "Formación",
  language: "Idiomas",
  skills: "Skills",
  location: "Ubicación",
  other: "Otros",
  role_gate: "Compuerta de rol",
};

export function JobAnalysisPanel({ job }: { job: Job | JobDetail }) {
  const analysis = job.analysis;
  if (!analysis) return <p className="text-sm text-ink-500">Este aviso todavía no fue analizado.</p>;
  const detail = job as JobDetail;

  return (
    <div className="space-y-5">
      <div>
        <p className="text-2xl font-bold">
          {Math.round(analysis.final_score)}% MATCH
          <span className="ml-2 align-middle text-xs font-medium text-ink-500">
            confianza {Math.round(analysis.confidence * 100)}% · analizado por {analysis.analyzer}
          </span>
        </p>
        {analysis.summary && <p className="mt-1 text-sm text-ink-600 dark:text-ink-300">{analysis.summary}</p>}
      </div>

      {detail.resumen && (
        <section className="rounded-xl border border-ink-200 bg-white p-4 dark:border-ink-800 dark:bg-ink-900">
          <div className="mb-2 flex flex-wrap items-baseline justify-between gap-2">
            <h4 className="text-sm font-semibold">Resumen del aviso</h4>
            <span className="text-xs text-ink-500">
              {detail.resumen.lectura_min} min de lectura
              {detail.resumen.cobertura === "parcial" && " · extracto parcial"}
            </span>
          </div>
          {detail.resumen.overview && (
            <p className="text-sm leading-relaxed text-ink-700 dark:text-ink-200">
              {detail.resumen.overview}
            </p>
          )}
          <div className="mt-3 grid gap-4 sm:grid-cols-2">
            <ResumenBloque titulo="Qué harías" items={detail.resumen.responsabilidades} />
            <ResumenBloque titulo="Qué piden" items={detail.resumen.requisitos} />
            <ResumenBloque titulo="Deseable" items={detail.resumen.deseables} />
            <ResumenBloque titulo="Qué ofrecen" items={detail.resumen.beneficios} />
          </div>
          <p className="mt-3 text-[11px] text-ink-400">
            Extraído textualmente del aviso, sin reescribir: nada de esto está inventado.
          </p>
        </section>
      )}

      {!analysis.eligible && analysis.not_eligible_reason && (
        <div className="rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-800 dark:border-red-900 dark:bg-red-950/40 dark:text-red-300">
          <strong>No elegible:</strong> {analysis.not_eligible_reason}
        </div>
      )}

      <div className="grid gap-5 sm:grid-cols-2">
        <section>
          <h4 className="label">Por qué encaja</h4>
          <ul className="space-y-1 text-sm">
            {analysis.match_reasons.map((reason, i) => (
              <li key={i} className="flex gap-2">
                <span className="text-accent-600">✓</span>
                <span>{reason}</span>
              </li>
            ))}
            {analysis.match_reasons.length === 0 && <li className="text-ink-500">Sin coincidencias destacadas.</li>}
          </ul>
        </section>

        <section>
          <h4 className="label">Faltantes</h4>
          <ul className="space-y-1 text-sm">
            {analysis.gaps.map((gap, i) => (
              <li key={i} className="flex gap-2">
                <span className="text-amber-500">⚠</span>
                <span>{gap}</span>
              </li>
            ))}
            {analysis.gaps.length === 0 && <li className="text-ink-500">Ninguno relevante.</li>}
          </ul>
          {analysis.hard_blockers.length > 0 && (
            <>
              <h4 className="label mt-4">Bloqueos</h4>
              <ul className="space-y-1 text-sm">
                {analysis.hard_blockers.map((blocker, i) => (
                  <li key={i} className="flex gap-2">
                    <span className="text-red-500">✕</span>
                    <span>{blocker}</span>
                  </li>
                ))}
              </ul>
            </>
          )}
        </section>
      </div>

      {analysis.why_apply && (
        <div className="rounded-xl border border-ink-200 bg-white p-3 text-sm dark:border-ink-800 dark:bg-ink-900">
          <span className="font-semibold">Recomendación: </span>
          {analysis.why_apply}
        </div>
      )}

      <section>
        <h4 className="label">Desglose del fit</h4>
        <div className="space-y-1.5">
          {Object.entries(analysis.fit_breakdown).map(([key, value]) => (
            <div key={key} className="flex items-center gap-3 text-xs">
              <span className="w-40 shrink-0 text-ink-600 dark:text-ink-300">
                {BREAKDOWN_LABEL[key] ?? key}
                {value.weight > 0 && <span className="text-ink-400"> ({value.weight}%)</span>}
              </span>
              <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-ink-200 dark:bg-ink-800">
                <div className="h-full rounded-full bg-ink-700 dark:bg-ink-300"
                     style={{ width: `${Math.max(0, Math.min(100, value.score))}%` }} />
              </div>
              <span className="w-8 text-right tabular-nums">{Math.round(value.score)}</span>
            </div>
          ))}
        </div>
      </section>

      {(analysis.boosts.length > 0 || analysis.penalties.length > 0) && (
        <section className="flex flex-wrap gap-2">
          {analysis.boosts.map((boost) => (
            <span key={boost.key} className="chip border-accent-200 bg-accent-50 text-accent-700 dark:border-accent-700 dark:bg-accent-700/20 dark:text-accent-400">
              +{boost.points} {boost.label}
            </span>
          ))}
          {analysis.penalties.map((penalty) => (
            <span key={penalty.key} className="chip border-red-200 bg-red-50 text-red-700 dark:border-red-900 dark:bg-red-950/40 dark:text-red-300">
              −{penalty.points} {penalty.label}
            </span>
          ))}
        </section>
      )}

      {detail.requirements?.length > 0 && (
        <div className="grid gap-5 sm:grid-cols-2">
          <section>
            <h4 className="label">Requisitos detectados</h4>
            <ul className="list-disc space-y-1 pl-4 text-sm text-ink-600 dark:text-ink-300">
              {detail.requirements.slice(0, 8).map((item, i) => <li key={i}>{item}</li>)}
            </ul>
          </section>
          {detail.preferred_requirements?.length > 0 && (
            <section>
              <h4 className="label">Deseables (no excluyentes)</h4>
              <ul className="list-disc space-y-1 pl-4 text-sm text-ink-600 dark:text-ink-300">
                {detail.preferred_requirements.slice(0, 8).map((item, i) => <li key={i}>{item}</li>)}
              </ul>
            </section>
          )}
        </div>
      )}

      {detail.occurrences?.length > 1 && (
        <section>
          <h4 className="label">También publicado en</h4>
          <div className="flex flex-wrap gap-2">
            {detail.occurrences.map((occurrence) => (
              <a key={occurrence.url} href={occurrence.url} target="_blank" rel="noopener noreferrer"
                 className="chip-neutral hover:underline">
                {occurrence.source} ↗
              </a>
            ))}
          </div>
        </section>
      )}

      {detail.description && (
        <details className="text-sm">
          <summary className="cursor-pointer font-semibold text-ink-700 dark:text-ink-200">
            Ver descripción completa del aviso
          </summary>
          <pre className="mt-2 max-h-96 overflow-auto whitespace-pre-wrap rounded-xl border border-ink-200 bg-white p-3 font-sans text-xs leading-relaxed text-ink-700 dark:border-ink-800 dark:bg-ink-900 dark:text-ink-300">
            {detail.description}
          </pre>
        </details>
      )}
    </div>
  );
}

function ResumenBloque({ titulo, items }: { titulo: string; items: string[] }) {
  if (!items || items.length === 0) return null;
  return (
    <div>
      <p className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-ink-500">
        {titulo}
      </p>
      <ul className="space-y-1 text-sm text-ink-600 dark:text-ink-300">
        {items.map((item, i) => (
          <li key={i} className="flex gap-2">
            <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-ink-400" />
            <span>{item}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
