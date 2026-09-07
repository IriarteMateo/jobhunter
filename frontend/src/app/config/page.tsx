"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { SourceHealth, TargetCompany } from "@/lib/types";

type Config = {
  preferences: Record<string, Record<string, number | boolean | string>>;
  ai_provider: string; ai_active: boolean; timezone: string;
  daily_run: string; scheduler_enabled: boolean; html_scraping_enabled: boolean;
  notificaciones: { escritorio: boolean; email: boolean; telegram: boolean };
  database: string; project_dir: string;
};
type Radar = {
  total_objetivos: number; empresas_consultadas: number;
  agregadores: string[]; agregador_objetivos: number;
  por_ats: { ats: string; label: string; count: number;
             companies: { name: string; jobs_found: number | null; status: string;
                          error: string | null }[] }[];
  sin_conector: { name: string; category: string | null; careers_url: string | null }[];
  ultima_corrida: { id: number; raw_jobs: number; new_jobs: number } | null;
};
type Suggestion = { company_id: number; name: string; matching_jobs: number; avg_score: number; texto: string };
type Detection = {
  detected: boolean; supported: boolean; ats_type: string | null; ats_label: string | null;
  ats_token: string | null; careers_url: string | null; verified: boolean;
  jobs_found: number | null; sample_titles: string[]; message: string;
};

const COMPLIANCE_LABEL: Record<string, string> = {
  official_api: "API oficial",
  public_ats_api: "API pública de ATS",
  rss_feed: "Feed RSS",
  public_html: "HTML público (robots.txt verificado)",
  restricted: "Restringida por términos del sitio",
};

export default function ConfigPage() {
  const [config, setConfig] = useState<Config | null>(null);
  const [sources, setSources] = useState<SourceHealth[]>([]);
  const [companies, setCompanies] = useState<TargetCompany[]>([]);
  const [suggestions, setSuggestions] = useState<Suggestion[]>([]);
  const [radar, setRadar] = useState<Radar | null>(null);
  const [showAllRadar, setShowAllRadar] = useState(false);
  const [links, setLinks] = useState<{ portal: string; query: string; url: string }[]>([]);
  const [message, setMessage] = useState<string | null>(null);
  const [newCompany, setNewCompany] = useState({ name: "", ats_type: "", ats_token: "", careers_url: "" });
  const [detectUrl, setDetectUrl] = useState("");
  const [detecting, setDetecting] = useState(false);
  const [detection, setDetection] = useState<Detection | null>(null);

  async function detectAts() {
    if (!detectUrl) return;
    setDetecting(true);
    setDetection(null);
    try {
      const result = await api.post<Detection>("/api/companies/detect", {
        careers_url: detectUrl, name: newCompany.name, verify: true,
      });
      setDetection(result);
      if (result.supported) {
        setNewCompany((prev) => ({
          ...prev,
          ats_type: result.ats_type ?? "",
          ats_token: result.ats_token ?? "",
          careers_url: result.careers_url ?? "",
        }));
      }
    } catch (e) {
      setDetection({
        detected: false, supported: false, ats_type: null, ats_label: null,
        ats_token: null, careers_url: null, verified: false, jobs_found: null,
        sample_titles: [], message: e instanceof Error ? e.message : "falló la detección",
      });
    } finally {
      setDetecting(false);
    }
  }

  const load = useCallback(async () => {
    const [cfg, health, comps, sugg, searchLinks, radarData] = await Promise.all([
      api.get<Config>("/api/config"),
      api.get<{ sources: SourceHealth[] }>("/api/sources/health"),
      api.get<TargetCompany[]>("/api/companies"),
      api.get<Suggestion[]>("/api/companies/suggestions"),
      api.get<{ links: { portal: string; query: string; url: string }[] }>("/api/sources/search-links"),
      api.get<Radar>("/api/companies/radar"),
    ]);
    setRadar(radarData);
    setConfig(cfg);
    setSources(health.sources);
    setCompanies(comps);
    setSuggestions(sugg);
    setLinks(searchLinks.links.slice(0, 18));
  }, []);

  useEffect(() => { void load(); }, [load]);
  if (!config) return <p className="text-sm text-ink-500">Cargando…</p>;

  async function saveDisplay(key: string, value: number | boolean) {
    const updated = await api.put<Record<string, Record<string, number | boolean>>>(
      "/api/config/display", { value: { [key]: value } },
    );
    setConfig((prev) => prev ? { ...prev, preferences: { ...prev.preferences, display: updated.display } } : prev);
  }

  async function saveWeight(group: string, key: string, value: number) {
    const updated = await api.put<Record<string, Record<string, number>>>(
      `/api/config/${group}`, { value: { [key]: value } },
    );
    setConfig((prev) => prev ? { ...prev, preferences: { ...prev.preferences, [group]: updated[group] } } : prev);
  }

  async function reanalyze() {
    setMessage("Recalculando…");
    const result = await api.post<{ analizados: number; recomendados: number }>("/api/runs/reanalyze");
    setMessage(`Listo: ${result.analizados} avisos recalculados, ${result.recomendados} recomendados.`);
    await load();
  }

  const fitWeights = (config.preferences.fit_weights ?? {}) as Record<string, number>;
  const totalWeight = Object.values(fitWeights).reduce((a, b) => a + Number(b), 0);

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-bold tracking-tight">Configuración</h1>
        <button className="btn-primary" onClick={reanalyze}>Recalcular scores</button>
      </header>
      {message && <div className="card p-3 text-sm">{message}</div>}

      <section className="card p-4">
        <h2 className="text-sm font-semibold">Sistema</h2>
        <dl className="mt-3 grid gap-2 text-sm sm:grid-cols-2">
          <Row label="Motor de IA" value={config.ai_active ? config.ai_provider : `${config.ai_provider} (reglas determinísticas)`} />
          <Row label="Corrida diaria" value={`${config.daily_run} · ${config.timezone}`} />
          <Row label="Scheduler" value={config.scheduler_enabled ? "activo" : "apagado"} />
          <Row label="Lectura de HTML público" value={config.html_scraping_enabled ? "habilitada" : "deshabilitada"} />
          <Row label="Aviso en pantalla"
               value={config.notificaciones?.escritorio ? "activado" : "apagado"} />
        </dl>
        {config.project_dir && (
          <p className="mt-2 truncate text-[11px] text-ink-400" title={config.project_dir}>
            Carpeta en uso: {config.project_dir}
          </p>
        )}
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <button className="btn-ghost px-3 py-1.5 text-xs"
                  onClick={async () => {
                    try {
                      const r = await api.post<{ mensaje: string }>("/api/notifications/test");
                      setMessage(r.mensaje);
                    } catch {
                      setMessage("No se pudo enviar la notificación de prueba.");
                    }
                  }}>
            Probar notificación
          </button>
          <span className="text-xs text-ink-500">
            Cuando aparecen oportunidades nuevas, macOS te muestra un aviso con la mejor
            de todas. Funciona también con la app cerrada, en la corrida diaria.
          </span>
        </div>
      </section>

      <section className="card space-y-3 p-4">
        <h2 className="text-sm font-semibold">Qué tan estricto con la experiencia</h2>
        <p className="text-xs text-ink-500">
          Define qué se descarta por pedir recorrido previo. Los avisos filtrados no
          desaparecen: se marcan como no elegibles con el motivo, y podés verlos tildando
          &laquo;Incluir no elegibles&raquo; en Empleos.
        </p>
        <div className="grid gap-2 sm:grid-cols-3">
          {([
            ["strict", "Sólo primer empleo",
             "Descarta Semi Senior en adelante y todo lo que pida 1+ año, aunque sea deseable."],
            ["balanced", "Equilibrado",
             "Tolera hasta 2 años deseables y 3 exigidos. Muestra más, con más ruido."],
            ["open", "Sin filtro",
             "Sólo descarta puestos de dirección. Para explorar el mercado completo."],
          ] as const).map(([value, label, help]) => {
            const active = (config.preferences.experience?.policy ?? "strict") === value;
            return (
              <button key={value}
                      onClick={async () => {
                        const updated = await api.put<Record<string, Record<string, string>>>(
                          "/api/config/experience", { value: { policy: value } },
                        );
                        setConfig((prev) => prev ? {
                          ...prev,
                          preferences: { ...prev.preferences, experience: updated.experience },
                        } : prev);
                        setMessage("Política guardada. Tocá «Recalcular scores» para aplicarla.");
                      }}
                      className={`rounded-xl border p-3 text-left transition-colors ${
                        active
                          ? "border-accent-500 bg-accent-50 dark:border-accent-600 dark:bg-accent-700/15"
                          : "border-ink-200 hover:bg-ink-50 dark:border-ink-800 dark:hover:bg-ink-950"
                      }`}>
                <p className="text-sm font-semibold">{label}</p>
                <p className="mt-1 text-xs text-ink-500">{help}</p>
              </button>
            );
          })}
        </div>
      </section>

      <section className="card space-y-4 p-4">
        <h2 className="text-sm font-semibold">Umbral de visualización</h2>
        <div>
          <label className="label">
            Mostrar sólo empleos con score ≥ {String(config.preferences.display?.min_display_score ?? 70)}
          </label>
          <input type="range" min={0} max={100} step={5} className="w-full accent-emerald-600"
                 value={Number(config.preferences.display?.min_display_score ?? 70)}
                 onChange={(e) => void saveDisplay("min_display_score", Number(e.target.value))} />
        </div>
        <div className="flex flex-wrap gap-4 text-sm">
          <label className="flex cursor-pointer items-center gap-2">
            <input type="checkbox" className="h-4 w-4 accent-emerald-600"
                   checked={Boolean(config.preferences.display?.hide_dismissed)}
                   onChange={(e) => void saveDisplay("hide_dismissed", e.target.checked)} />
            Ocultar descartados
          </label>
          <label className="flex cursor-pointer items-center gap-2">
            <input type="checkbox" className="h-4 w-4 accent-emerald-600"
                   checked={Boolean(config.preferences.display?.hide_not_eligible)}
                   onChange={(e) => void saveDisplay("hide_not_eligible", e.target.checked)} />
            Ocultar no elegibles
          </label>
        </div>
      </section>

      <section className="card space-y-3 p-4">
        <div className="flex items-baseline justify-between">
          <h2 className="text-sm font-semibold">Pesos del Fit Score</h2>
          <span className="text-xs text-ink-500">total {totalWeight}</span>
        </div>
        {Object.entries(fitWeights).map(([key, value]) => (
          <div key={key} className="flex items-center gap-3 text-sm">
            <span className="w-32 capitalize text-ink-600 dark:text-ink-300">{key}</span>
            <input type="range" min={0} max={40} step={1} value={Number(value)}
                   className="flex-1 accent-emerald-600"
                   onChange={(e) => void saveWeight("fit_weights", key, Number(e.target.value))} />
            <span className="w-8 text-right tabular-nums">{Number(value)}</span>
          </div>
        ))}
        <p className="text-xs text-ink-500">
          Los cambios se aplican al recalcular. Los pesos se normalizan sobre el total.
        </p>
      </section>

      {radar && (
        <section className="card p-4">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h2 className="text-sm font-semibold">En el radar</h2>
            <span className="text-xs text-ink-500">
              {radar.total_objetivos} objetivos por corrida
            </span>
          </div>
          <p className="mt-1 text-xs text-ink-500">
            {radar.empresas_consultadas} empresas se consultan una por una en su propio sistema
            de empleos, más {radar.agregador_objetivos} búsquedas en {radar.agregadores.length} agregadores.
          </p>

          <div className="mt-4 space-y-4">
            {radar.por_ats.map((group) => (
              <div key={group.ats}>
                <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-500">
                  {group.label} · {group.count}
                </h3>
                <div className="grid gap-1.5 sm:grid-cols-2 lg:grid-cols-3">
                  {group.companies.map((company) => (
                    <div key={company.name}
                         className="flex items-center justify-between gap-2 rounded-lg border border-ink-200 px-2.5 py-1.5 text-sm dark:border-ink-800">
                      <span className="flex min-w-0 items-center gap-2">
                        <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${
                          company.status === "ok" ? "bg-emerald-500"
                            : company.status === "error" ? "bg-red-500" : "bg-ink-300"
                        }`} />
                        <span className="truncate">{company.name}</span>
                      </span>
                      <span className="shrink-0 text-xs tabular-nums text-ink-500">
                        {company.jobs_found === null ? "—" : `${company.jobs_found} avisos`}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            ))}

            <div>
              <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-500">
                Agregadores · {radar.agregadores.length}
              </h3>
              <div className="flex flex-wrap gap-1.5">
                {radar.agregadores.map((name) => <span key={name} className="chip-neutral">{name}</span>)}
              </div>
            </div>
          </div>

          {radar.sin_conector.length > 0 && (
            <div className="mt-5 rounded-xl border border-amber-200 bg-amber-50 p-3 dark:border-amber-900 dark:bg-amber-950/30">
              <p className="text-xs font-semibold text-amber-900 dark:text-amber-200">
                {radar.sin_conector.length} empresas en tu lista que NO se consultan
              </p>
              <p className="mt-1 text-xs text-amber-800 dark:text-amber-300/90">
                Están como objetivo pero no tienen conector: su página de empleos no expone una
                API pública, o hay que detectarla. Usá el detector de abajo con la URL de su
                buscador de empleos.
              </p>
              <div className="mt-2 flex flex-wrap gap-1.5">
                {(showAllRadar ? radar.sin_conector : radar.sin_conector.slice(0, 12)).map((c) => (
                  <span key={c.name} className="chip border-amber-200 bg-white text-amber-900 dark:border-amber-900 dark:bg-ink-950 dark:text-amber-300">
                    {c.name}
                  </span>
                ))}
                {radar.sin_conector.length > 12 && (
                  <button className="chip-neutral" onClick={() => setShowAllRadar((v) => !v)}>
                    {showAllRadar ? "ver menos" : `+${radar.sin_conector.length - 12} más`}
                  </button>
                )}
              </div>
            </div>
          )}
        </section>
      )}

      <section className="card p-4">
        <h2 className="text-sm font-semibold">Estado de las fuentes</h2>
        <div className="mt-3 space-y-2">
          {sources.map((source) => (
            <div key={source.key} className="flex flex-wrap items-center gap-3 rounded-xl border border-ink-200 p-3 text-sm dark:border-ink-800">
              <span className={`h-2 w-2 shrink-0 rounded-full ${
                !source.enabled ? "bg-ink-300"
                  : source.status === "ok" ? "bg-emerald-500"
                  : source.status === "error" ? "bg-red-500" : "bg-amber-400"
              }`} />
              <span className="w-44 shrink-0 font-medium">{source.label}</span>
              <span className="w-20 shrink-0 text-xs text-ink-500">{source.status}</span>
              <span className="w-24 shrink-0 text-xs text-ink-500">{source.last_found} avisos</span>
              <span className="w-24 shrink-0 text-xs text-ink-500">
                {source.avg_duration_ms ? `${Math.round(source.avg_duration_ms)} ms` : "—"}
              </span>
              <span className="min-w-0 flex-1 truncate text-xs text-ink-400" title={source.compliance_note ?? ""}>
                {COMPLIANCE_LABEL[source.compliance_level] ?? source.compliance_level}
                {source.last_error ? ` · ${source.last_error.slice(0, 60)}` : ""}
              </span>
              <button
                className="btn-ghost px-3 py-1 text-xs"
                onClick={async () => {
                  await api.patch(`/api/sources/${source.key}`, { enabled: !source.enabled });
                  await load();
                }}
              >
                {source.enabled ? "Desactivar" : "Activar"}
              </button>
            </div>
          ))}
        </div>
      </section>

      <section className="card p-4">
        <h2 className="text-sm font-semibold">Portales con restricciones</h2>
        <p className="mt-1 text-xs text-ink-500">
          LinkedIn, Indeed, Bumeran, ZonaJobs y Glassdoor no permiten extracción automatizada.
          Hay dos caminos legítimos para traer sus avisos igual:
        </p>
        <ol className="mt-2 space-y-1 text-xs text-ink-600 dark:text-ink-300">
          <li>
            <strong>1. Alertas por email (recomendado).</strong> Creá una alerta de búsqueda
            en cada portal. Ellos te mandan las ofertas a tu casilla y la app las lee por IMAP.
            Se activa con <code>IMAP_ENABLED=true</code> y tus credenciales en el <code>.env</code>,
            más la fuente <em>Alertas por email</em> encendida acá arriba.
          </li>
          <li>
            <strong>2. Importar a mano.</strong> Desde <em>Empleos → Importar un aviso</em>,
            pegás el texto y se analiza con el mismo motor.
          </li>
        </ol>
        <p className="mt-2 text-xs text-ink-500">
          Y en cualquier momento podés abrir la búsqueda ya filtrada en el sitio original:
        </p>
        <div className="mt-3 flex flex-wrap gap-2">
          {links.map((link, index) => (
            <a key={index} href={link.url} target="_blank" rel="noopener noreferrer"
               className="chip-neutral hover:underline">
              {link.portal}: {link.query} ↗
            </a>
          ))}
        </div>
      </section>

      {suggestions.length > 0 && (
        <section className="card p-4">
          <h2 className="text-sm font-semibold">Empresas sugeridas</h2>
          <p className="mt-1 text-xs text-ink-500">
            Publican buenas oportunidades y no están en tu lista. No se agregan solas.
          </p>
          <div className="mt-3 space-y-2">
            {suggestions.map((s) => (
              <div key={s.company_id} className="flex items-center justify-between gap-3 rounded-xl border border-ink-200 p-3 text-sm dark:border-ink-800">
                <span>{s.texto}</span>
                <button className="btn-ghost px-3 py-1 text-xs"
                        onClick={async () => { await api.post("/api/companies", { name: s.name }); await load(); }}>
                  Agregar
                </button>
              </div>
            ))}
          </div>
        </section>
      )}

      <section className="card p-4">
        <h2 className="text-sm font-semibold">Empresas objetivo ({companies.length})</h2>
        <div className="mt-3 rounded-xl border border-ink-200 p-3 dark:border-ink-800">
          <label className="label">Detectar el ATS de una empresa</label>
          <p className="mb-2 text-xs text-ink-500">
            Pegá la URL del buscador de empleos de la empresa (no la landing) y averiguo
            sobre qué plataforma corre. Si tiene conector, lo pruebo contra su API antes
            de configurarlo.
          </p>
          <div className="flex flex-wrap gap-2">
            <input className="input flex-1" placeholder="https://empresa.com/careers/search"
                   value={detectUrl} onChange={(e) => setDetectUrl(e.target.value)} />
            <button className="btn-ghost" onClick={detectAts} disabled={detecting || !detectUrl}>
              {detecting ? "Detectando…" : "Detectar"}
            </button>
          </div>
          {detection && (
            <div className={`mt-2 rounded-lg border p-2 text-xs ${
              detection.verified
                ? "border-accent-200 bg-accent-50 text-accent-800 dark:border-accent-700 dark:bg-accent-700/10 dark:text-accent-300"
                : "border-amber-200 bg-amber-50 text-amber-900 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-200"
            }`}>
              <p className="font-medium">{detection.message}</p>
              {detection.supported && (
                <p className="mt-1 opacity-80">
                  Configuración: {detection.ats_type}
                  {detection.ats_token ? ` · token ${detection.ats_token}` : ""}
                  {detection.careers_url ? ` · ${detection.careers_url}` : ""}
                  {" — ya cargada abajo, revisá el nombre y guardá."}
                </p>
              )}
              {detection.sample_titles.length > 0 && (
                <ul className="mt-1 list-disc pl-4 opacity-80">
                  {detection.sample_titles.slice(0, 3).map((t, i) => <li key={i}>{t}</li>)}
                </ul>
              )}
            </div>
          )}
        </div>

        <div className="mt-3 grid gap-2 sm:grid-cols-4">
          <input className="input" placeholder="Nombre" value={newCompany.name}
                 onChange={(e) => setNewCompany({ ...newCompany, name: e.target.value })} />
          <select className="input" value={newCompany.ats_type}
                  onChange={(e) => setNewCompany({ ...newCompany, ats_type: e.target.value })}>
            <option value="">Sin ATS conectado</option>
            {["greenhouse", "lever", "ashby", "smartrecruiters", "workable", "recruitee",
              "workday", "oracle_recruiting", "eightfold", "successfactors",
              "company_careers"].map((t) => (
              <option key={t} value={t}>{t}</option>
            ))}
          </select>
          <input className="input" placeholder="Token del board" value={newCompany.ats_token}
                 onChange={(e) => setNewCompany({ ...newCompany, ats_token: e.target.value })} />
          <button className="btn-ghost"
                  onClick={async () => {
                    if (!newCompany.name) return;
                    await api.post("/api/companies", newCompany);
                    setNewCompany({ name: "", ats_type: "", ats_token: "", careers_url: "" });
                    setDetection(null);
                    setDetectUrl("");
                    await load();
                  }}>
            Agregar empresa
          </button>
        </div>
        {newCompany.careers_url && (
          <input className="input mt-2" placeholder="Config del conector (host|site, dominio…)"
                 value={newCompany.careers_url}
                 onChange={(e) => setNewCompany({ ...newCompany, careers_url: e.target.value })} />
        )}

        <div className="mt-4 max-h-96 overflow-auto">
          <table className="w-full text-left text-sm">
            <thead className="sticky top-0 bg-white text-xs uppercase text-ink-500 dark:bg-ink-900">
              <tr>
                <th className="py-2">Empresa</th><th>Categoría</th><th>ATS</th>
                <th>Calidad</th><th>Avisos</th><th></th>
              </tr>
            </thead>
            <tbody>
              {companies.map((company) => (
                <tr key={company.id} className="border-t border-ink-200/70 dark:border-ink-800">
                  <td className="py-2 font-medium">
                    {company.name} {company.german_relevant && "🇩🇪"}
                  </td>
                  <td className="text-ink-500">{company.category ?? "—"}</td>
                  <td className="text-xs text-ink-500">
                    {company.ats_type ? `${company.ats_type}${company.ats_token ? `:${company.ats_token}` : ""}` : "—"}
                  </td>
                  <td className="tabular-nums">
                    {company.quality_score ?? "—"}
                    <span className="ml-1 text-[10px] text-ink-400">{company.quality_confidence ?? ""}</span>
                  </td>
                  <td className="tabular-nums">{company.active_jobs}</td>
                  <td className="text-right">
                    <button className="text-xs text-ink-400 hover:text-red-600"
                            onClick={async () => { await api.del(`/api/companies/${company.id}`); await load(); }}>
                      Quitar
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between gap-3 rounded-lg border border-ink-200 px-3 py-2 dark:border-ink-800">
      <dt className="text-ink-500">{label}</dt>
      <dd className="font-medium">{value}</dd>
    </div>
  );
}
