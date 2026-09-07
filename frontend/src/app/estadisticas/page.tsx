"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";

type Stats = {
  encontrados_semana: number; recomendados_semana: number; aplicaciones: number;
  entrevistas: number; guardados: number; descartados: number; conversion_rate: number;
  promedio_fit: number; ofertas_con_aleman: number;
  top_empresas: { company: string; count: number }[];
  por_seniority: { seniority: string; count: number }[];
  por_recomendacion: { recommendation: string; count: number }[];
};

export default function StatsPage() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [personalization, setPersonalization] = useState<{ ajustes: { texto: string }[]; nota: string } | null>(null);

  useEffect(() => {
    void (async () => {
      setStats(await api.get<Stats>("/api/dashboard/stats"));
      setPersonalization(await api.get("/api/config/personalization"));
    })();
  }, []);

  if (!stats) return <p className="text-sm text-ink-500">Cargando…</p>;

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold tracking-tight">Métricas</h1>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Stat label="Encontrados (7 días)" value={stats.encontrados_semana} />
        <Stat label="Recomendados (7 días)" value={stats.recomendados_semana} />
        <Stat label="Aplicaciones" value={stats.aplicaciones} />
        <Stat label="Entrevistas" value={stats.entrevistas} />
        <Stat label="Guardados" value={stats.guardados} />
        <Stat label="Descartados" value={stats.descartados} />
        <Stat label="Conversión" value={`${stats.conversion_rate}%`} />
        <Stat label="Fit promedio" value={stats.promedio_fit} />
      </div>

      <div className="grid gap-5 sm:grid-cols-2">
        <Panel title="Empresas con más oportunidades" rows={stats.top_empresas.map((r) => [r.company, r.count])} />
        <Panel title="Por seniority" rows={stats.por_seniority.map((r) => [r.seniority, r.count])} />
        <Panel title="Por recomendación" rows={stats.por_recomendacion.map((r) => [r.recommendation, r.count])} />
        <div className="card p-4">
          <h2 className="mb-3 text-sm font-semibold">Ofertas donde el alemán suma</h2>
          <p className="text-4xl font-bold tabular-nums">{stats.ofertas_con_aleman}</p>
        </div>
      </div>

      <section className="card p-4">
        <h2 className="text-sm font-semibold">Personalización activa</h2>
        <p className="mt-1 text-xs text-ink-500">{personalization?.nota}</p>
        <ul className="mt-3 space-y-1 text-sm">
          {personalization?.ajustes.length === 0 && (
            <li className="text-ink-500">Ningún ajuste todavía: guardá o descartá avisos para que aprenda.</li>
          )}
          {personalization?.ajustes.map((item, i) => <li key={i}>· {item.texto}</li>)}
        </ul>
      </section>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="card p-4">
      <p className="text-2xl font-bold tabular-nums">{value}</p>
      <p className="text-xs text-ink-500">{label}</p>
    </div>
  );
}

function Panel({ title, rows }: { title: string; rows: [string, number][] }) {
  const max = Math.max(1, ...rows.map((r) => r[1]));
  return (
    <div className="card p-4">
      <h2 className="mb-3 text-sm font-semibold">{title}</h2>
      {rows.length === 0 && <p className="text-sm text-ink-500">Sin datos todavía.</p>}
      <div className="space-y-2">
        {rows.map(([label, count]) => (
          <div key={label} className="flex items-center gap-3 text-xs">
            <span className="w-40 shrink-0 truncate text-ink-600 dark:text-ink-300">{label}</span>
            <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-ink-200 dark:bg-ink-800">
              <div className="h-full rounded-full bg-ink-700 dark:bg-ink-300"
                   style={{ width: `${(count / max) * 100}%` }} />
            </div>
            <span className="w-6 text-right tabular-nums">{count}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
