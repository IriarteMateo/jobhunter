"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import type { Job } from "@/lib/types";
import { JobCard } from "@/components/JobCard";
import { SORT_RECIENTES, SortControl, type Sort, sortToQuery } from "@/components/SortControl";

/** Cada chip es una consulta lista: la usuaria no arma filtros, elige un ángulo. */
const ATAJOS = [
  { key: "todos", label: "Todo lo encontrado", params: "" },
  { key: "hoy", label: "🆕 Nuevos hoy", params: "new_only=true" },
  { key: "recomendados", label: "⭐ Recomendados", params: "min_score=70" },
  { key: "sin_exp", label: "🎓 Sin experiencia", params: "max_experience=0" },
  { key: "graduate", label: "🎓 Graduate / Trainee", params: "graduate_only=true" },
  { key: "internship", label: "📘 Pasantías", params: "internship_only=true" },
  { key: "aleman", label: "🇩🇪 Con alemán", params: "german_only=true" },
  { key: "objetivo", label: "🏢 Empresas objetivo", params: "target_only=true" },
  { key: "remoto", label: "🏠 Remoto", params: "remote_type=remote" },
  { key: "zona_norte", label: "📍 Zona Norte", params: "location=san isidro" },
  { key: "product", label: "💻 Product / Tech", params: "role_family=product" },
  { key: "business", label: "📊 Business / Strategy", params: "role_family=business" },
  { key: "data", label: "📈 Data / Analytics", params: "role_family=data" },
  { key: "marketing", label: "🚀 Marketing / Growth", params: "role_family=marketing" },
  { key: "finance", label: "💰 Finance / Fintech", params: "role_family=finance" },
  { key: "consulting", label: "🧭 Consultoría", params: "role_family=consulting" },
] as const;

function diaDe(iso: string): string {
  const fecha = new Date(iso);
  const hoy = new Date();
  const ayer = new Date();
  ayer.setDate(hoy.getDate() - 1);
  const igual = (a: Date, b: Date) => a.toDateString() === b.toDateString();
  if (igual(fecha, hoy)) return "Hoy";
  if (igual(fecha, ayer)) return "Ayer";
  return fecha.toLocaleDateString("es-AR", { weekday: "long", day: "numeric", month: "long" });
}

export default function RecientesPage() {
  const [atajo, setAtajo] = useState<string>("todos");
  const [busqueda, setBusqueda] = useState("");
  const [jobs, setJobs] = useState<Job[]>([]);
  const [total, setTotal] = useState(0);
  const [cargando, setCargando] = useState(true);
  const [sort, setSort] = useState<Sort>(SORT_RECIENTES);

  const load = useCallback(async () => {
    setCargando(true);
    const elegido = ATAJOS.find((a) => a.key === atajo);
    const params = new URLSearchParams(elegido?.params || "");
    sortToQuery(sort).split("&").forEach((kv) => { const [k, v] = kv.split("="); params.set(k, v); });
    params.set("page_size", "60");
    // Este feed muestra lo que ENTRÓ, no sólo lo recomendado: por eso el umbral
    // arranca en 0 salvo que el atajo pida otra cosa.
    if (!params.has("min_score")) params.set("min_score", "0");
    if (busqueda) params.set("q", busqueda);
    const data = await api.get<{ items: Job[]; total: number }>(`/api/jobs?${params}`);
    setJobs(data.items);
    setTotal(data.total);
    setCargando(false);
  }, [atajo, busqueda, sort]);

  useEffect(() => {
    const t = setTimeout(() => void load(), busqueda ? 350 : 0);
    return () => clearTimeout(t);
  }, [load, busqueda]);

  const agrupar = sort.field === "date";
  const grupos = useMemo(() => {
    if (!agrupar) return [["", jobs]] as [string, Job[]][];
    const mapa = new Map<string, Job[]>();
    for (const job of jobs) {
      const dia = diaDe(job.first_seen_date);
      if (!mapa.has(dia)) mapa.set(dia, []);
      mapa.get(dia)!.push(job);
    }
    return [...mapa.entries()];
  }, [jobs, agrupar]);

  return (
    <div className="space-y-5">
      <header>
        <h1 className="text-2xl font-bold tracking-tight">Recientes</h1>
        <p className="mt-1 text-sm text-ink-500">
          Todo lo que fue encontrando el sistema, del más nuevo al más viejo.
          Incluye lo que no llega al umbral, para que puedas ver el panorama completo.
        </p>
      </header>

      <div className="space-y-3">
        <input
          className="input"
          placeholder="Buscar por cargo, empresa o palabra clave…"
          value={busqueda}
          onChange={(e) => setBusqueda(e.target.value)}
        />
        <div className="flex flex-wrap gap-1.5">
          {ATAJOS.map((a) => (
            <button
              key={a.key}
              onClick={() => setAtajo(a.key)}
              className={`chip transition-colors ${
                atajo === a.key
                  ? "border-ink-900 bg-ink-900 text-white dark:border-white dark:bg-white dark:text-ink-950"
                  : "border-ink-200 bg-white text-ink-600 hover:bg-ink-100 dark:border-ink-800 dark:bg-ink-950 dark:text-ink-300"
              }`}
            >
              {a.label}
            </button>
          ))}
        </div>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="text-xs text-ink-500">
            {cargando ? "Buscando…" : `${total} aviso${total === 1 ? "" : "s"}`}
          </p>
          <SortControl sort={sort} onChange={setSort} compact />
        </div>
      </div>

      {!cargando && jobs.length === 0 && (
        <div className="card p-8 text-center text-sm text-ink-500">
          Nada con ese filtro. Probá con «Todo lo encontrado».
        </div>
      )}

      {grupos.map(([dia, items]) => (
        <section key={dia || "todos"} className="space-y-3">
          {dia && (
            <div className="flex items-center gap-3">
              <h2 className="text-sm font-semibold uppercase tracking-wide text-ink-500">{dia}</h2>
              <span className="text-xs text-ink-400">{items.length}</span>
              <div className="h-px flex-1 bg-ink-200 dark:bg-ink-800" />
            </div>
          )}
          <div className="space-y-4">
            {items.map((job) => (
              <JobCard key={job.id} job={job} onChange={() => void load()} />
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}
