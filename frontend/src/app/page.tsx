"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import type { Job, RunResult, TodaySummary } from "@/lib/types";
import { JobCard } from "@/components/JobCard";
import { SORT_DEFAULT, SortControl, type Sort, sortToQuery } from "@/components/SortControl";

function greeting() {
  const hour = new Date().getHours();
  if (hour < 6) return "Buenas noches";
  if (hour < 13) return "Buen día";
  if (hour < 20) return "Buenas tardes";
  return "Buenas noches";
}

export default function HomePage() {
  const [summary, setSummary] = useState<TodaySummary | null>(null);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [run, setRun] = useState<RunResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);
  const [progreso, setProgreso] = useState<string | null>(null);
  const [sort, setSort] = useState<Sort>(SORT_DEFAULT);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [today, list] = await Promise.all([
        api.get<TodaySummary>("/api/dashboard/today"),
        api.get<{ items: Job[] }>(`/api/jobs?page_size=8&${sortToQuery(sort)}`),
      ]);
      setSummary(today);
      setJobs(list.items);
    } catch (e) {
      setError(e instanceof Error ? e.message : "error desconocido");
    } finally {
      setLoading(false);
    }
  }, [sort]);

  useEffect(() => { void load(); }, [load]);

  /** La corrida tarda varios minutos: se arranca y se sigue por polling.
   *  Esperarla dentro de la request la hacía caer por timeout del proxy. */
  async function searchNow() {
    setRunning(true);
    setError(null);
    setAviso(null);
    setRun(null);
    setProgreso("Arrancando…");
    try {
      const inicio = await api.post<{ run_id: number | null; mensaje: string }>(
        "/api/runs", { notify: true },
      );
      setProgreso(inicio.mensaje);
      if (inicio.run_id == null) return;

      // Se consulta el estado cada 3 segundos hasta que termina
      for (let i = 0; i < 200; i++) {
        await new Promise((r) => setTimeout(r, 3000));
        const estado = await api.get<
          RunResult & { status: string; stats?: Partial<RunResult> }
        >(`/api/runs/${inicio.run_id}`);
        if (estado.status !== "running") {
          // GET /api/runs/{id} anida el detalle por fuente dentro de `stats`;
          // el panel lo espera plano, como lo devolvía el POST antes.
          setRun({ ...estado, ...(estado.stats ?? {}) });
          setProgreso(null);
          await load();
          return;
        }
        setProgreso(
          estado.raw_jobs
            ? `Revisando avisos… ${estado.raw_jobs} leídos de ${estado.sources_queried} fuentes`
            : "Consultando fuentes…",
        );
      }
      setProgreso(null);
      setAviso("La búsqueda sigue corriendo. Recargá en un rato para ver el resultado.");
    } catch (e) {
      const texto = e instanceof Error ? e.message : "la búsqueda falló";
      setProgreso(null);
      if (texto.startsWith("409")) {
        const m = texto.match(/"detail":"(.*?)"/);
        setAviso(m ? m[1] : "Ya hay una búsqueda en curso. Esperá a que termine.");
      } else {
        setError(texto);
      }
    } finally {
      setRunning(false);
    }
  }

  return (
    <div className="space-y-6">
      <section className="card p-5 sm:p-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-sm font-medium uppercase tracking-wide text-ink-500">{greeting()}</p>
            <h1 className="mt-1 text-2xl font-bold tracking-tight sm:text-3xl">
              {summary
                ? summary.nuevas_hoy > 0
                  ? `Encontré ${summary.nuevas_hoy} oportunidades nuevas desde ayer.`
                  : "Sin oportunidades nuevas todavía."
                : "Cargando…"}
            </h1>
            {summary && summary.nuevas_hoy > 0 && (
              <p className="mt-1 text-ink-600 dark:text-ink-300">
                {summary.recomendadas === 0
                  ? "Ninguna supera tu umbral de relevancia hoy."
                  : `${summary.recomendadas} realmente ${summary.recomendadas === 1 ? "vale" : "valen"} la pena.`}
              </p>
            )}
          </div>
          <div className="text-right">
            <button className="btn-primary" onClick={searchNow} disabled={running}>
              {running ? "Buscando…" : "Buscar nuevos empleos ahora"}
            </button>
            {progreso && (
              <p className="mt-2 max-w-56 text-xs text-ink-500">{progreso}</p>
            )}
          </div>
        </div>

        {summary && (
          <div className="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-5">
            <Stat label="Nuevas hoy" value={summary.nuevas_hoy} />
            <Stat label="Recomendadas" value={summary.recomendadas} accent />
            <Stat label="Aplicar ya" value={summary.aplicar_ya} accent />
            <Stat label="Empresas objetivo" value={summary.empresas_objetivo} />
            <Stat label="Con alemán" value={summary.con_aleman} />
          </div>
        )}

        {summary?.ultima_corrida && (
          <p className="mt-4 text-xs text-ink-500">
            Última búsqueda: {summary.ultima_corrida.raw_jobs} avisos revisados ·{" "}
            {summary.ultima_corrida.filtered_out} descartados por ubicación o nivel ·{" "}
            {summary.ultima_corrida.new_jobs} nuevos guardados · {(summary.ultima_corrida.duration_ms / 1000).toFixed(1)}s
          </p>
        )}
      </section>

      {aviso && (
        <div className="card border-amber-200 bg-amber-50 p-4 text-sm text-amber-900 dark:border-amber-900 dark:bg-amber-950/30 dark:text-amber-200">
          {aviso}
          <p className="mt-1 text-xs opacity-80">
            Puede ser la corrida automática de las 07:30, u otra pestaña. Una corrida
            completa tarda alrededor de dos minutos.
          </p>
        </div>
      )}

      {error && (
        <div className="card border-red-200 p-4 text-sm text-red-700 dark:border-red-900 dark:text-red-300">
          {error}
          <p className="mt-1 text-xs text-ink-500">
            ¿Está corriendo el backend en http://127.0.0.1:8080?
          </p>
        </div>
      )}

      {run && <RunReport run={run} />}

      <section className="space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-lg font-semibold tracking-tight">Tus mejores oportunidades</h2>
          <div className="flex flex-wrap items-center gap-3">
            <SortControl sort={sort} onChange={setSort} compact />
            <Link href="/empleos" className="text-sm font-medium text-ink-600 hover:underline dark:text-ink-300">
              Ver todas →
            </Link>
          </div>
        </div>

        {loading && <p className="text-sm text-ink-500">Cargando…</p>}
        {!loading && jobs.length === 0 && (
          <div className="card p-8 text-center">
            <p className="font-medium">Todavía no hay empleos que superen tu umbral.</p>
            <p className="mt-1 text-sm text-ink-500">
              Ejecutá una búsqueda, o bajá el umbral mínimo desde Config.
            </p>
          </div>
        )}
        {jobs.map((job) => <JobCard key={job.id} job={job} onChange={() => void load()} />)}
      </section>
    </div>
  );
}

function Stat({ label, value, accent }: { label: string; value: number; accent?: boolean }) {
  return (
    <div className={`rounded-xl border p-3 ${
      accent
        ? "border-accent-200 bg-accent-50 dark:border-accent-700/50 dark:bg-accent-700/10"
        : "border-ink-200 bg-ink-50 dark:border-ink-800 dark:bg-ink-950"
    }`}>
      <p className="text-2xl font-bold tabular-nums">{value}</p>
      <p className="text-xs text-ink-500">{label}</p>
    </div>
  );
}

function RunReport({ run }: { run: RunResult }) {
  const failed = (run.sources ?? []).filter((s) => s.status !== "ok");
  return (
    <section className="card p-4 text-sm">
      <h3 className="font-semibold">Resultado de la búsqueda</h3>
      <div className="mt-2 grid grid-cols-2 gap-2 text-xs sm:grid-cols-6">
        <Metric label="Fuentes" value={run.sources_queried} />
        <Metric label="Avisos crudos" value={run.raw_jobs} />
        <Metric label="Nuevos" value={run.new_jobs} />
        <Metric label="Duplicados" value={run.duplicates} />
        <Metric label="Filtrados" value={run.filtered_out} />
        <Metric label="Segundos" value={Number((run.duration_ms / 1000).toFixed(1))} />
      </div>
      {Object.keys(run.filter_reasons || {}).length > 0 && (
        <p className="mt-3 text-xs text-ink-500">
          Motivos de descarte:{" "}
          {Object.entries(run.filter_reasons ?? {}).map(([reason, count]) => `${reason} (${count})`).join(" · ")}
        </p>
      )}
      {failed.length > 0 && (
        <details className="mt-3">
          <summary className="cursor-pointer text-xs font-medium text-red-600 dark:text-red-400">
            {failed.length} fuente(s) con error
          </summary>
          <ul className="mt-1 space-y-1 text-xs text-ink-500">
            {failed.map((s, i) => <li key={i}>{s.source} · {s.target}: {s.error}</li>)}
          </ul>
        </details>
      )}
    </section>
  );
}

function Metric({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-lg border border-ink-200 px-2 py-1.5 dark:border-ink-800">
      <p className="font-bold tabular-nums">{value}</p>
      <p className="text-ink-500">{label}</p>
    </div>
  );
}
