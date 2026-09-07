"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { api, scoreTone } from "@/lib/api";
import type { CompanyOverview, Job } from "@/lib/types";
import { JobCard } from "@/components/JobCard";
import { SORT_DEFAULT, SortControl, type Sort, sortToQuery } from "@/components/SortControl";

type Radar = { sin_conector: { name: string; category: string | null }[] };

export default function EmpresasPage() {
  const [empresas, setEmpresas] = useState<CompanyOverview[]>([]);
  const [sinConector, setSinConector] = useState<Radar["sin_conector"]>([]);
  const [cargando, setCargando] = useState(true);
  const [busqueda, setBusqueda] = useState("");
  const [soloConAvisos, setSoloConAvisos] = useState(true);

  const [abierta, setAbierta] = useState<CompanyOverview | null>(null);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [cargandoJobs, setCargandoJobs] = useState(false);
  const [soloRelevantes, setSoloRelevantes] = useState(true);
  const [avisoFallback, setAvisoFallback] = useState(false);
  const [sort, setSort] = useState<Sort>(SORT_DEFAULT);

  const load = useCallback(async () => {
    setCargando(true);
    const [lista, radar] = await Promise.all([
      api.get<CompanyOverview[]>("/api/companies/overview"),
      api.get<Radar>("/api/companies/radar"),
    ]);
    setEmpresas(lista);
    setSinConector(radar.sin_conector);
    setCargando(false);
  }, []);

  useEffect(() => { void load(); }, [load]);

  // Al elegir una empresa, el detalle REEMPLAZA la grilla. Antes se renderizaba
  // debajo de las 56 tarjetas y tocar una empresa no producía ningún cambio
  // visible: los avisos quedaban nueve pantallas más abajo.
  useEffect(() => {
    if (abierta) window.scrollTo({ top: 0 });
  }, [abierta]);

  // Cambiar el orden recarga los avisos de la empresa abierta
  useEffect(() => {
    if (abierta) void cargarJobs(abierta, soloRelevantes);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sort]);

  const pedirJobs = useCallback(async (empresa: CompanyOverview, relevantes: boolean) => {
    const params = new URLSearchParams({
      company_id: String(empresa.company_id),
      page_size: "60",
      min_score: relevantes ? "70" : "0",
    });
    sortToQuery(sort).split("&").forEach((kv) => { const [k, v] = kv.split("="); params.set(k, v); });
    if (!relevantes) params.set("include_not_eligible", "true");
    const data = await api.get<{ items: Job[] }>(`/api/jobs?${params}`);
    return data.items;
  }, [sort]);

  const cargarJobs = useCallback(async (empresa: CompanyOverview, relevantes: boolean) => {
    setCargandoJobs(true);
    setAvisoFallback(false);
    let items = await pedirJobs(empresa, relevantes);
    // Si el umbral deja la lista vacía pero la empresa sí tiene avisos, se
    // muestran todos: una pantalla vacía no explica nada.
    if (items.length === 0 && relevantes && empresa.total_jobs > 0) {
      items = await pedirJobs(empresa, false);
      setAvisoFallback(items.length > 0);
    }
    setJobs(items);
    setCargandoJobs(false);
  }, [pedirJobs]);

  async function abrir(empresa: CompanyOverview) {
    setAbierta(empresa);
    setJobs([]);
    setCargandoJobs(true);   // el efecto de scroll ya lleva la vista al detalle
    await cargarJobs(empresa, soloRelevantes);
  }

  const visibles = useMemo(() => {
    const q = busqueda.trim().toLowerCase();
    return empresas.filter((e) => {
      if (soloConAvisos && e.total_jobs === 0) return false;
      if (!q) return true;
      return e.name.toLowerCase().includes(q)
        || (e.category || "").toLowerCase().includes(q)
        || (e.ats_label || "").toLowerCase().includes(q);
    });
  }, [empresas, busqueda, soloConAvisos]);

  function volver() {
    setAbierta(null);
    setJobs([]);
    setAvisoFallback(false);
    window.scrollTo({ top: 0 });
  }

  const conConector = empresas.filter((e) => e.ats_type).length;
  const totalAvisos = empresas.reduce((acc, e) => acc + e.total_jobs, 0);

  // ---------------------------- vista de una empresa ---------------------- #
  if (abierta) {
    return (
      <div className="space-y-5">
        <button className="btn-ghost px-3 py-1.5 text-sm" onClick={volver}>
          ← Todas las empresas
        </button>

        <header className="card p-5">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <h1 className="text-2xl font-bold tracking-tight">
                {abierta.name} {abierta.german_relevant && "🇩🇪"}
              </h1>
              <p className="mt-1 text-sm text-ink-500">
                {abierta.category || "Sin rubro"}
                {abierta.ats_label && ` · se consulta vía ${abierta.ats_label}`}
              </p>
            </div>
            {abierta.quality_score !== null && (
              <div className="text-right">
                <p className="text-2xl font-bold tabular-nums">
                  {Math.round(abierta.quality_score)}
                </p>
                <p className="text-xs text-ink-500">
                  calidad
                  {abierta.quality_confidence === "LOW" && " · info limitada"}
                </p>
              </div>
            )}
          </div>
          <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-4">
            <Metrica label="Avisos guardados" valor={abierta.total_jobs} />
            <Metrica label="Elegibles" valor={abierta.eligible_jobs} />
            <Metrica label="Recomendados" valor={abierta.recommended_jobs} destacado />
            <Metrica label="Nuevos hoy" valor={abierta.new_today} />
          </div>
        </header>

        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="text-sm text-ink-500">
            {cargandoJobs ? "Cargando avisos…" : `${jobs.length} avisos en pantalla`}
          </p>
          <div className="flex flex-wrap items-center gap-3">
          <SortControl sort={sort} onChange={setSort} compact />
          <label className="flex cursor-pointer items-center gap-2 text-sm">
            <input type="checkbox" className="h-4 w-4 accent-emerald-600"
                   checked={soloRelevantes}
                   onChange={async (e) => {
                     setSoloRelevantes(e.target.checked);
                     await cargarJobs(abierta, e.target.checked);
                   }} />
            Sólo relevantes
          </label>
          </div>
        </div>

        {avisoFallback && (
          <div className="rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900 dark:border-amber-900 dark:bg-amber-950/30 dark:text-amber-200">
            Ninguno de los {abierta.total_jobs} avisos de {abierta.name} supera el umbral
            de relevancia, así que te muestro todos.
          </div>
        )}

        {cargandoJobs && (
          <div className="card p-8 text-center text-sm text-ink-500">Cargando avisos…</div>
        )}
        {!cargandoJobs && jobs.length === 0 && (
          <div className="card p-8 text-center text-sm text-ink-500">
            No hay avisos guardados de {abierta.name} todavía.
            Aparecerán en la próxima corrida.
          </div>
        )}

        <div className="space-y-4">
          {jobs.map((job) => (
            <JobCard key={job.id} job={job}
                     onChange={() => void cargarJobs(abierta, soloRelevantes)} />
          ))}
        </div>
      </div>
    );
  }

  // ------------------------------ grilla de empresas ---------------------- #
  return (
    <div className="space-y-5">
      <header>
        <h1 className="text-2xl font-bold tracking-tight">Empresas</h1>
        <p className="mt-1 text-sm text-ink-500">
          {conConector} empresas se consultan en cada corrida, con {totalAvisos} avisos
          guardados. Tocá una para ver todas sus oportunidades.
        </p>
      </header>

      <div className="flex flex-wrap items-center gap-3">
        <input
          className="input flex-1 min-w-56"
          placeholder="Buscar empresa, rubro o sistema…"
          value={busqueda}
          onChange={(e) => setBusqueda(e.target.value)}
        />
        <label className="flex cursor-pointer items-center gap-2 text-sm">
          <input type="checkbox" className="h-4 w-4 accent-emerald-600"
                 checked={soloConAvisos} onChange={(e) => setSoloConAvisos(e.target.checked)} />
          Sólo con avisos
        </label>
      </div>

      {cargando && <p className="text-sm text-ink-500">Cargando…</p>}

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {visibles.map((empresa) => {
          const tone = scoreTone(empresa.best_score ?? 0);
          return (
            <button
              key={empresa.company_id}
              onClick={() => void abrir(empresa)}
              className="card p-4 text-left transition-all hover:-translate-y-0.5 hover:shadow-md"
            >
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <p className="truncate font-semibold">
                    {empresa.name} {empresa.german_relevant && "🇩🇪"}
                  </p>
                  <p className="truncate text-xs text-ink-500">
                    {empresa.category || "—"}
                    {empresa.ats_label && ` · ${empresa.ats_label}`}
                  </p>
                </div>
                {empresa.best_score !== null && (
                  <span className={`chip shrink-0 ${tone.chip}`}>
                    {Math.round(empresa.best_score)}
                  </span>
                )}
              </div>

              <div className="mt-3 flex flex-wrap gap-1.5 text-xs">
                <span className="chip-neutral">{empresa.total_jobs} avisos</span>
                {empresa.recommended_jobs > 0 && (
                  <span className="chip border-accent-200 bg-accent-50 text-accent-700 dark:border-accent-700 dark:bg-accent-700/15 dark:text-accent-400">
                    {empresa.recommended_jobs} recomendados
                  </span>
                )}
                {empresa.new_today > 0 && (
                  <span className="chip border-sky-200 bg-sky-50 text-sky-700 dark:border-sky-900 dark:bg-sky-950/40 dark:text-sky-300">
                    {empresa.new_today} nuevos hoy
                  </span>
                )}
                {!empresa.ats_type && <span className="chip-neutral">sin conector</span>}
              </div>

              <p className="mt-3 text-xs font-medium text-ink-500">Ver oportunidades →</p>
            </button>
          );
        })}
      </div>

      {sinConector.length > 0 && (
        <section className="card p-4">
          <h2 className="text-sm font-semibold">
            En tu lista pero sin conector ({sinConector.length})
          </h2>
          <p className="mt-1 text-xs text-ink-500">
            Su página de empleos no expone una API pública. Se pueden seguir con las alertas
            por email o importando avisos a mano. Probá también el detector en Config.
          </p>
          <div className="mt-3 flex flex-wrap gap-1.5">
            {sinConector.map((c) => (
              <span key={c.name} className="chip-neutral">{c.name}</span>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}

function Metrica({ label, valor, destacado }: {
  label: string; valor: number; destacado?: boolean;
}) {
  return (
    <div className={`rounded-xl border p-3 ${
      destacado
        ? "border-accent-200 bg-accent-50 dark:border-accent-700/50 dark:bg-accent-700/10"
        : "border-ink-200 bg-ink-50 dark:border-ink-800 dark:bg-ink-950"
    }`}>
      <p className="text-xl font-bold tabular-nums">{valor}</p>
      <p className="text-xs text-ink-500">{label}</p>
    </div>
  );
}
