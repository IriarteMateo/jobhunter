"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { Job } from "@/lib/types";
import { JobCard } from "@/components/JobCard";
import { SortControl, type Sort, sortToQuery } from "@/components/SortControl";

const TABS = [
  { key: "SAVED", label: "Guardados" },
  { key: "APPLIED", label: "Aplicados" },
  { key: "INTERVIEW", label: "Entrevistas" },
  { key: "REJECTED", label: "Rechazados" },
  { key: "DISCARDED", label: "Descartados" },
  { key: "SEEN", label: "Vistos" },
];

export default function HistoryPage() {
  const [tab, setTab] = useState("SAVED");
  const [jobs, setJobs] = useState<Job[]>([]);
  const [loading, setLoading] = useState(true);
  const [sort, setSort] = useState<Sort>({ field: "date", dir: "desc" });

  const load = useCallback(async () => {
    setLoading(true);
    const data = await api.get<{ items: Job[] }>(
      `/api/jobs?status=${tab}&min_score=0&include_not_eligible=true&page_size=60&${sortToQuery(sort)}`,
    );
    setJobs(data.items);
    setLoading(false);
  }, [tab, sort]);

  useEffect(() => { void load(); }, [load]);

  return (
    <div className="space-y-5">
      <header>
        <h1 className="text-2xl font-bold tracking-tight">Historial</h1>
        <p className="mt-1 text-sm text-ink-500">
          Todo lo que pasó por el sistema y en qué estado quedó.
        </p>
      </header>

      <div className="flex flex-wrap gap-1.5">
        {TABS.map((item) => (
          <button
            key={item.key}
            onClick={() => setTab(item.key)}
            className={`chip transition-colors ${
              tab === item.key
                ? "border-ink-900 bg-ink-900 text-white dark:border-white dark:bg-white dark:text-ink-950"
                : "border-ink-200 bg-white text-ink-600 hover:bg-ink-100 dark:border-ink-800 dark:bg-ink-950 dark:text-ink-300"
            }`}
          >
            {item.label}
          </button>
        ))}
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-xs text-ink-500">
          {loading ? "Buscando…" : `${jobs.length} aviso${jobs.length === 1 ? "" : "s"}`}
        </p>
        <SortControl sort={sort} onChange={setSort} compact />
      </div>

      {loading && <p className="text-sm text-ink-500">Cargando…</p>}
      {!loading && jobs.length === 0 && (
        <div className="card p-8 text-center text-sm text-ink-500">Nada en esta categoría todavía.</div>
      )}
      <div className="space-y-4">
        {jobs.map((job) => <JobCard key={job.id} job={job} onChange={() => void load()} />)}
      </div>
    </div>
  );
}
