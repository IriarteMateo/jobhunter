"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { Job } from "@/lib/types";
import { JobCard } from "@/components/JobCard";
import { ImportJob } from "@/components/ImportJob";
import { SORT_DEFAULT, SortControl, type Sort, sortToQuery } from "@/components/SortControl";

const SENIORITIES = ["Internship", "Trainee", "Graduate", "Entry Level", "Junior", "Junior+", "Semi Senior"];
const MODALITIES = [
  { value: "onsite", label: "Presencial" },
  { value: "hybrid", label: "Híbrido" },
  { value: "remote", label: "Remoto" },
];
const STATUSES = ["NEW", "SEEN", "SAVED", "APPLIED", "INTERVIEW", "DISCARDED"];
const FAMILIES = [
  { value: "", label: "Todas las áreas" },
  { value: "business", label: "Business & Strategy" },
  { value: "product", label: "Product" },
  { value: "consulting", label: "Consulting" },
  { value: "data", label: "Data & Analytics" },
  { value: "marketing", label: "Marketing & Growth" },
  { value: "operations", label: "Operations" },
  { value: "finance", label: "Finance & Fintech" },
  { value: "customer", label: "Customer & Experience" },
  { value: "tech_business", label: "Technology Business" },
];

export default function JobsPage() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [q, setQ] = useState("");
  const [minScore, setMinScore] = useState(70);
  const [seniority, setSeniority] = useState<string[]>([]);
  const [modality, setModality] = useState<string[]>([]);
  const [status, setStatus] = useState<string[]>([]);
  const [family, setFamily] = useState("");
  const [germanOnly, setGermanOnly] = useState(false);
  const [targetOnly, setTargetOnly] = useState(false);
  const [graduateOnly, setGraduateOnly] = useState(false);
  const [newOnly, setNewOnly] = useState(false);
  const [includeNotEligible, setIncludeNotEligible] = useState(false);
  const [maxExperience, setMaxExperience] = useState<string>("");
  const [sort, setSort] = useState<Sort>(SORT_DEFAULT);

  const load = useCallback(async () => {
    setLoading(true);
    const params = new URLSearchParams();
    params.set("page_size", "60");
    params.set("min_score", String(minScore));
    sortToQuery(sort).split("&").forEach((kv) => { const [k, v] = kv.split("="); params.set(k, v); });
    if (q) params.set("q", q);
    if (family) params.set("role_family", family);
    seniority.forEach((s) => params.append("seniority", s));
    modality.forEach((m) => params.append("remote_type", m));
    status.forEach((s) => params.append("status", s));
    if (germanOnly) params.set("german_only", "true");
    if (targetOnly) params.set("target_only", "true");
    if (graduateOnly) params.set("graduate_only", "true");
    if (newOnly) params.set("new_only", "true");
    if (includeNotEligible) params.set("include_not_eligible", "true");
    if (maxExperience) params.set("max_experience", maxExperience);

    const data = await api.get<{ items: Job[]; total: number }>(`/api/jobs?${params}`);
    setJobs(data.items);
    setTotal(data.total);
    setLoading(false);
  }, [q, minScore, seniority, modality, status, family, germanOnly, targetOnly,
      graduateOnly, newOnly, includeNotEligible, maxExperience, sort]);

  useEffect(() => { void load(); }, [load]);

  function toggle(list: string[], setList: (v: string[]) => void, value: string) {
    setList(list.includes(value) ? list.filter((v) => v !== value) : [...list, value]);
  }

  return (
    <div className="space-y-5">
      <header className="flex flex-wrap items-baseline justify-between gap-2">
        <h1 className="text-2xl font-bold tracking-tight">Empleos</h1>
        <p className="text-sm text-ink-500">{total} resultado{total === 1 ? "" : "s"}</p>
      </header>

      <ImportJob onImported={() => void load()} />

      <section className="card space-y-4 p-4">
        <div className="grid gap-3 sm:grid-cols-3">
          <div className="sm:col-span-2">
            <label className="label">Buscar</label>
            <input className="input" placeholder="Cargo, empresa o palabra clave"
                   value={q} onChange={(e) => setQ(e.target.value)} />
          </div>
          <div>
            <label className="label">Área</label>
            <select className="input" value={family} onChange={(e) => setFamily(e.target.value)}>
              {FAMILIES.map((f) => <option key={f.value} value={f.value}>{f.label}</option>)}
            </select>
          </div>
        </div>

        <div className="grid gap-3 sm:grid-cols-3">
          <div>
            <label className="label">Score mínimo: {minScore}</label>
            <input type="range" min={0} max={100} step={5} value={minScore}
                   className="w-full accent-emerald-600"
                   onChange={(e) => setMinScore(Number(e.target.value))} />
          </div>
          <div>
            <label className="label">Experiencia máxima pedida</label>
            <select className="input" value={maxExperience} onChange={(e) => setMaxExperience(e.target.value)}>
              <option value="">Cualquiera</option>
              <option value="0">Sin experiencia</option>
              <option value="1">Hasta 1 año</option>
              <option value="2">Hasta 2 años</option>
            </select>
          </div>
          <div>
            <label className="label">Ordenar por</label>
            <SortControl sort={sort} onChange={setSort} compact />
          </div>
        </div>

        <FilterGroup label="Seniority" options={SENIORITIES.map((s) => ({ value: s, label: s }))}
                     selected={seniority} onToggle={(v) => toggle(seniority, setSeniority, v)} />
        <FilterGroup label="Modalidad" options={MODALITIES}
                     selected={modality} onToggle={(v) => toggle(modality, setModality, v)} />
        <FilterGroup label="Estado" options={STATUSES.map((s) => ({ value: s, label: s }))}
                     selected={status} onToggle={(v) => toggle(status, setStatus, v)} />

        <div className="flex flex-wrap gap-4 text-sm">
          <Check label="🇩🇪 Sólo con alemán" checked={germanOnly} onChange={setGermanOnly} />
          <Check label="⭐ Sólo empresas objetivo" checked={targetOnly} onChange={setTargetOnly} />
          <Check label="🎓 Sólo graduate / trainee" checked={graduateOnly} onChange={setGraduateOnly} />
          <Check label="🆕 Sólo nuevos hoy" checked={newOnly} onChange={setNewOnly} />
          <Check label="Incluir no elegibles" checked={includeNotEligible} onChange={setIncludeNotEligible} />
        </div>
      </section>

      {loading && <p className="text-sm text-ink-500">Cargando…</p>}
      {!loading && jobs.length === 0 && (
        <div className="card p-8 text-center text-sm text-ink-500">
          Ningún empleo coincide con estos filtros.
        </div>
      )}
      <div className="space-y-4">
        {jobs.map((job) => <JobCard key={job.id} job={job} onChange={() => void load()} />)}
      </div>
    </div>
  );
}

function FilterGroup({ label, options, selected, onToggle }: {
  label: string;
  options: { value: string; label: string }[];
  selected: string[];
  onToggle: (value: string) => void;
}) {
  return (
    <div>
      <label className="label">{label}</label>
      <div className="flex flex-wrap gap-1.5">
        {options.map((option) => (
          <button
            key={option.value}
            onClick={() => onToggle(option.value)}
            className={`chip transition-colors ${
              selected.includes(option.value)
                ? "border-ink-900 bg-ink-900 text-white dark:border-white dark:bg-white dark:text-ink-950"
                : "border-ink-200 bg-white text-ink-600 hover:bg-ink-100 dark:border-ink-800 dark:bg-ink-950 dark:text-ink-300"
            }`}
          >
            {option.label}
          </button>
        ))}
      </div>
    </div>
  );
}

function Check({ label, checked, onChange }: {
  label: string; checked: boolean; onChange: (v: boolean) => void;
}) {
  return (
    <label className="flex cursor-pointer items-center gap-2">
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)}
             className="h-4 w-4 rounded accent-emerald-600" />
      {label}
    </label>
  );
}
