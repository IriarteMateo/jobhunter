"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { Job } from "@/lib/types";
import { JobCard } from "@/components/JobCard";
import { SORT_DEFAULT, SortControl, type Sort, sortToQuery } from "@/components/SortControl";

type Bucket = { key: string; label: string; count: number; items: Job[] };

export default function TopPicksPage() {
  const [buckets, setBuckets] = useState<Bucket[]>([]);
  const [loading, setLoading] = useState(true);
  const [sort, setSort] = useState<Sort>(SORT_DEFAULT);

  const load = useCallback(async () => {
    setLoading(true);
    const data = await api.get<{ buckets: Bucket[] }>(`/api/jobs/top-picks?${sortToQuery(sort)}`);
    setBuckets(data.buckets);
    setLoading(false);
  }, [sort]);

  useEffect(() => { void load(); }, [load]);

  const filled = buckets.filter((b) => b.count > 0);

  return (
    <div className="space-y-8">
      <header>
        <h1 className="text-2xl font-bold tracking-tight">Top Picks</h1>
        <p className="mt-1 text-sm text-ink-500">
          Sólo lo mejor de lo encontrado, agrupado por tipo de oportunidad.
        </p>
      </header>

      <div className="flex justify-end">
        <SortControl sort={sort} onChange={setSort} compact />
      </div>

      {loading && <p className="text-sm text-ink-500">Cargando…</p>}
      {!loading && filled.length === 0 && (
        <div className="card p-8 text-center text-sm text-ink-500">
          Todavía no hay nada que destacar. Ejecutá una búsqueda desde la home.
        </div>
      )}

      {filled.map((bucket) => (
        <section key={bucket.key} className="space-y-3">
          <h2 className="text-lg font-semibold tracking-tight">
            {bucket.label} <span className="text-sm font-normal text-ink-500">({bucket.count})</span>
          </h2>
          <div className="space-y-4">
            {bucket.items.map((job) => (
              <JobCard key={`${bucket.key}-${job.id}`} job={job} onChange={() => void load()} />
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}
