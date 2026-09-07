"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { Job } from "@/lib/types";
import { JobCard } from "@/components/JobCard";
import { SortControl, type Sort, sortToQuery } from "@/components/SortControl";

export default function GermanPage() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [loading, setLoading] = useState(true);
  const [sort, setSort] = useState<Sort>({ field: "german", dir: "desc" });

  const load = useCallback(async () => {
    setLoading(true);
    const data = await api.get<{ items: Job[] }>(
      `/api/jobs?german_only=true&min_score=0&page_size=60&${sortToQuery(sort)}`,
    );
    setJobs(data.items);
    setLoading(false);
  }, [sort]);

  useEffect(() => { void load(); }, [load]);

  return (
    <div className="space-y-5">
      <header>
        <h1 className="text-2xl font-bold tracking-tight">🇩🇪 German Advantage</h1>
        <p className="mt-1 max-w-2xl text-sm text-ink-500">
          Búsquedas donde el alemán es requisito, es valorado o representa una ventaja clara.
          No se limita a empresas alemanas: una compañía estadounidense también puede necesitar
          un German speaker.
        </p>
      </header>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-xs text-ink-500">
          {loading ? "Buscando…" : `${jobs.length} aviso${jobs.length === 1 ? "" : "s"}`}
        </p>
        <SortControl sort={sort} onChange={setSort} compact />
      </div>

      {loading && <p className="text-sm text-ink-500">Cargando…</p>}
      {!loading && jobs.length === 0 && (
        <div className="card p-8 text-center text-sm text-ink-500">
          Ninguna búsqueda activa menciona el alemán. Se revisa en cada corrida diaria.
        </div>
      )}
      <div className="space-y-4">
        {jobs.map((job) => <JobCard key={job.id} job={job} onChange={() => void load()} />)}
      </div>
    </div>
  );
}
