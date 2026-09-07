"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import type { JobDetail } from "@/lib/types";
import { JobCard } from "./JobCard";

type ImportResult = {
  job_id: number; created: boolean; merged_with_existing: boolean;
  fetched_url: boolean; message: string; job: JobDetail | null;
};

export function ImportJob({ onImported }: { onImported?: () => void }) {
  const [open, setOpen] = useState(false);
  const [url, setUrl] = useState("");
  const [text, setText] = useState("");
  const [title, setTitle] = useState("");
  const [company, setCompany] = useState("");
  const [location, setLocation] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ImportResult | null>(null);

  async function submit() {
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const payload = { url: url || null, text: text || null, title: title || null,
                        company: company || null, location: location || null };
      const data = await api.post<ImportResult>("/api/jobs/import", payload);
      setResult(data);
      onImported?.();
    } catch (e) {
      const raw = e instanceof Error ? e.message : "no se pudo importar";
      const match = raw.match(/"detail":"(.*?)"}/);
      setError(match ? match[1] : raw);
    } finally {
      setBusy(false);
    }
  }

  function reset() {
    setUrl(""); setText(""); setTitle(""); setCompany(""); setLocation("");
    setResult(null); setError(null);
  }

  return (
    <section className="card p-4">
      <button className="flex w-full items-center justify-between text-left"
              onClick={() => setOpen((v) => !v)}>
        <div>
          <h2 className="text-sm font-semibold">Importar un aviso</h2>
          <p className="text-xs text-ink-500">
            Pegá el texto de cualquier aviso —LinkedIn, Bumeran, un mensaje— y se analiza igual que el resto.
          </p>
        </div>
        <span className="text-ink-400">{open ? "−" : "+"}</span>
      </button>

      {open && (
        <div className="mt-4 space-y-3">
          <div>
            <label className="label">Link del aviso</label>
            <input className="input" placeholder="https://…" value={url}
                   onChange={(e) => setUrl(e.target.value)} />
            <p className="mt-1 text-xs text-ink-500">
              Si es de Greenhouse, Lever, Ashby o SmartRecruiters alcanza con el link:
              se trae el aviso completo por su API. LinkedIn, Indeed y Bumeran no permiten
              lectura automatizada — para esos, pegá el texto abajo.
            </p>
          </div>

          <div>
            <label className="label">Texto del aviso</label>
            <textarea className="input min-h-32" rows={7}
                      placeholder="Copiá y pegá la descripción completa del puesto…"
                      value={text} onChange={(e) => setText(e.target.value)} />
          </div>

          <div className="grid gap-3 sm:grid-cols-3">
            <div>
              <label className="label">Puesto (opcional)</label>
              <input className="input" value={title} onChange={(e) => setTitle(e.target.value)} />
            </div>
            <div>
              <label className="label">Empresa (opcional)</label>
              <input className="input" value={company} onChange={(e) => setCompany(e.target.value)} />
            </div>
            <div>
              <label className="label">Ubicación (opcional)</label>
              <input className="input" value={location} onChange={(e) => setLocation(e.target.value)} />
            </div>
          </div>

          <div className="flex flex-wrap gap-2">
            <button className="btn-primary" onClick={submit} disabled={busy || (!url && !text)}>
              {busy ? "Analizando…" : "Importar y analizar"}
            </button>
            <button className="btn-ghost" onClick={reset} disabled={busy}>Limpiar</button>
          </div>

          {error && (
            <div className="rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-200">
              {error}
            </div>
          )}

          {result && (
            <div className="space-y-3">
              <p className="text-sm font-medium text-accent-700 dark:text-accent-400">
                {result.message}
              </p>
              {result.job && <JobCard job={result.job} />}
            </div>
          )}
        </div>
      )}
    </section>
  );
}
