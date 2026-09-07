"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { Profile } from "@/lib/types";

const FAMILY_OPTIONS = [
  ["business", "Business & Strategy"], ["product", "Product"], ["consulting", "Consulting"],
  ["data", "Data & Analytics"], ["marketing", "Marketing & Growth"], ["operations", "Operations"],
  ["finance", "Finance & Fintech"], ["customer", "Customer & Experience"],
  ["tech_business", "Technology Business"],
];

export default function ProfilePage() {
  const [profile, setProfile] = useState<Profile | null>(null);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [cvProposal, setCvProposal] = useState<Record<string, unknown> | null>(null);

  useEffect(() => {
    void api.get<Profile>("/api/profile").then(setProfile);
  }, []);

  if (!profile) return <p className="text-sm text-ink-500">Cargando…</p>;

  function update<K extends keyof Profile>(key: K, value: Profile[K]) {
    setProfile((prev) => (prev ? { ...prev, [key]: value } : prev));
  }

  async function save() {
    if (!profile) return;
    setSaving(true);
    setMessage(null);
    try {
      const saved = await api.put<Profile>("/api/profile", profile);
      setProfile(saved);
      const result = await api.post<{ analizados: number }>("/api/runs/reanalyze");
      setMessage(`Perfil guardado. Se recalcularon ${result.analizados} avisos con los nuevos datos.`);
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "no se pudo guardar");
    } finally {
      setSaving(false);
    }
  }

  async function uploadCv(file: File) {
    const body = new FormData();
    body.append("file", file);
    const res = await fetch("/api/profile/cv", { method: "POST", body });
    if (!res.ok) { setMessage("No se pudo leer el PDF."); return; }
    const data = await res.json();
    setCvProposal(data.propuesta);
    setMessage("CV leído. Revisá la propuesta y aplicá lo que corresponda.");
  }

  return (
    <div className="space-y-5">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Perfil</h1>
          <p className="mt-1 text-sm text-ink-500">
            Todo lo que alimenta el matching. Al guardar se recalculan los scores.
          </p>
        </div>
        <button className="btn-primary" onClick={save} disabled={saving}>
          {saving ? "Guardando…" : "Guardar y recalcular"}
        </button>
      </header>

      {message && <div className="card p-3 text-sm">{message}</div>}

      <section className="card space-y-4 p-4">
        <h2 className="text-sm font-semibold">Formación</h2>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Universidad" value={profile.university} onChange={(v) => update("university", v)} />
          <Field label="Carrera" value={profile.degree} onChange={(v) => update("degree", v)} />
          <Field label="Área de la carrera" value={profile.degree_field} onChange={(v) => update("degree_field", v)} />
          <Field label="Año de graduación" type="number" value={String(profile.graduation_year ?? "")}
                 onChange={(v) => update("graduation_year", v ? Number(v) : null)} />
        </div>
      </section>

      <section className="card space-y-4 p-4">
        <h2 className="text-sm font-semibold">Idiomas</h2>
        <div className="space-y-2">
          {profile.languages.map((lang, index) => (
            <div key={index} className="grid grid-cols-3 gap-2">
              <input className="input" value={lang.code}
                     onChange={(e) => {
                       const next = [...profile.languages];
                       next[index] = { ...lang, code: e.target.value };
                       update("languages", next);
                     }} />
              <input className="input" value={lang.name}
                     onChange={(e) => {
                       const next = [...profile.languages];
                       next[index] = { ...lang, name: e.target.value };
                       update("languages", next);
                     }} />
              <input className="input" value={lang.level} placeholder="Nivel"
                     onChange={(e) => {
                       const next = [...profile.languages];
                       next[index] = { ...lang, level: e.target.value };
                       update("languages", next);
                     }} />
            </div>
          ))}
        </div>
        <button className="btn-ghost"
                onClick={() => update("languages", [...profile.languages, { code: "", name: "", level: "" }])}>
          + Agregar idioma
        </button>
      </section>

      <section className="card space-y-4 p-4">
        <h2 className="text-sm font-semibold">Experiencia y skills</h2>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Años de experiencia" type="number" value={String(profile.years_experience)}
                 onChange={(v) => update("years_experience", Number(v || 0))} />
          <ListField label="Skills" values={profile.skills} onChange={(v) => update("skills", v)} />
          <ListField label="Cargos de interés" values={profile.target_roles} onChange={(v) => update("target_roles", v)} />
          <ListField label="Áreas excluidas" values={profile.excluded_areas} onChange={(v) => update("excluded_areas", v)} />
        </div>
        <div>
          <label className="label">Familias de rol activas</label>
          <div className="flex flex-wrap gap-1.5">
            {FAMILY_OPTIONS.map(([value, label]) => {
              const active = profile.role_families.includes(value);
              return (
                <button key={value}
                        onClick={() => update("role_families",
                          active ? profile.role_families.filter((f) => f !== value)
                                 : [...profile.role_families, value])}
                        className={`chip ${active
                          ? "border-ink-900 bg-ink-900 text-white dark:border-white dark:bg-white dark:text-ink-950"
                          : "border-ink-200 bg-white text-ink-600 dark:border-ink-800 dark:bg-ink-950 dark:text-ink-300"}`}>
                  {label}
                </button>
              );
            })}
          </div>
        </div>
      </section>

      <section className="card space-y-4 p-4">
        <h2 className="text-sm font-semibold">Ubicación y modalidad</h2>
        <div className="grid gap-3 sm:grid-cols-3">
          <Field label="Ciudad" value={profile.city} onChange={(v) => update("city", v)} />
          <Field label="Zona" value={profile.region} onChange={(v) => update("region", v)} />
          <Field label="Distancia máxima (km)" type="number" value={String(profile.max_commute_km ?? "")}
                 onChange={(v) => update("max_commute_km", v ? Number(v) : null)} />
        </div>
        <ListField label="Ubicaciones preferidas" values={profile.preferred_locations}
                   onChange={(v) => update("preferred_locations", v)} />
        <div className="flex flex-wrap gap-4 text-sm">
          <Toggle label="Acepto remoto" checked={profile.accepts_remote} onChange={(v) => update("accepts_remote", v)} />
          <Toggle label="Acepto híbrido" checked={profile.accepts_hybrid} onChange={(v) => update("accepts_hybrid", v)} />
          <Toggle label="Acepto presencial" checked={profile.accepts_onsite} onChange={(v) => update("accepts_onsite", v)} />
        </div>
      </section>

      <section className="card space-y-4 p-4">
        <h2 className="text-sm font-semibold">Empresas</h2>
        <div className="grid gap-3 sm:grid-cols-2">
          <ListField label="Favoritas" values={profile.favorite_companies}
                     onChange={(v) => update("favorite_companies", v)} />
          <ListField label="Bloqueadas" values={profile.blocked_companies}
                     onChange={(v) => update("blocked_companies", v)} />
        </div>
      </section>

      <section className="card space-y-3 p-4">
        <h2 className="text-sm font-semibold">CV</h2>
        <p className="text-xs text-ink-500">
          Se extraen datos del PDF como <strong>propuesta</strong>. Nada se aplica sin que lo revises.
        </p>
        <input type="file" accept="application/pdf" className="text-sm"
               onChange={(e) => { const f = e.target.files?.[0]; if (f) void uploadCv(f); }} />
        {profile.cv_filename && <p className="text-xs text-ink-500">Archivo actual: {profile.cv_filename}</p>}
        {cvProposal && (
          <pre className="max-h-64 overflow-auto rounded-xl border border-ink-200 bg-ink-50 p-3 text-xs dark:border-ink-800 dark:bg-ink-950">
            {JSON.stringify(cvProposal, null, 2)}
          </pre>
        )}
      </section>
    </div>
  );
}

function Field({ label, value, onChange, type = "text" }: {
  label: string; value: string; onChange: (v: string) => void; type?: string;
}) {
  return (
    <div>
      <label className="label">{label}</label>
      <input className="input" type={type} value={value} onChange={(e) => onChange(e.target.value)} />
    </div>
  );
}

function ListField({ label, values, onChange }: {
  label: string; values: string[]; onChange: (v: string[]) => void;
}) {
  return (
    <div>
      <label className="label">{label} <span className="normal-case text-ink-400">(separadas por coma)</span></label>
      <input className="input" value={values.join(", ")}
             onChange={(e) => onChange(e.target.value.split(",").map((s) => s.trim()).filter(Boolean))} />
    </div>
  );
}

function Toggle({ label, checked, onChange }: {
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
