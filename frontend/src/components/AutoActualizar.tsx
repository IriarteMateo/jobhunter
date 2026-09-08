"use client";

import { useEffect, useState } from "react";

/**
 * Recarga la pantalla sola cuando llega una versión nueva.
 *
 * La app se actualiza en segundo plano (`auto-update.sh` hace `git pull` cada
 * 10 minutos). El backend recarga solo, y Next.js en modo dev también, pero el
 * navegador se queda con el HTML viejo hasta que alguien apreta F5.
 *
 * Se avisa antes de recargar en vez de hacerlo de golpe: si la pantalla cambia
 * sin explicación, parece que se rompió.
 */
const CADA = 60_000;      // consultar la versión una vez por minuto
const ESPERA = 6;         // segundos de aviso antes de recargar

export function AutoActualizar() {
  const [cuenta, setCuenta] = useState<number | null>(null);

  useEffect(() => {
    let inicial: string | null = null;
    let cancelado = false;

    async function mirar() {
      try {
        const r = await fetch("/api/version", { cache: "no-store" });
        if (!r.ok) return;
        const { commit } = (await r.json()) as { commit: string };
        if (!commit || commit === "sin-git") return;
        if (inicial === null) {
          inicial = commit;
        } else if (commit !== inicial && !cancelado) {
          setCuenta(ESPERA);
        }
      } catch {
        // Sin conexión con el backend no hay nada que avisar: se reintenta solo.
      }
    }

    mirar();
    const id = setInterval(mirar, CADA);
    return () => {
      cancelado = true;
      clearInterval(id);
    };
  }, []);

  useEffect(() => {
    if (cuenta === null) return;
    if (cuenta <= 0) {
      window.location.reload();
      return;
    }
    const id = setTimeout(() => setCuenta((n) => (n === null ? null : n - 1)), 1000);
    return () => clearTimeout(id);
  }, [cuenta]);

  if (cuenta === null) return null;

  return (
    <div className="fixed inset-x-0 bottom-4 z-50 flex justify-center px-4">
      <div className="flex items-center gap-3 rounded-full border border-accent-400 bg-accent-50 px-4 py-2 text-sm shadow-card dark:border-accent-700 dark:bg-accent-700">
        <span className="text-accent-700 dark:text-accent-50">
          Hay mejoras nuevas. Actualizando en {cuenta}…
        </span>
        <button
          className="rounded-full bg-accent-600 px-3 py-1 text-xs font-medium text-white hover:bg-accent-700"
          onClick={() => window.location.reload()}
        >
          Ahora
        </button>
      </div>
    </div>
  );
}
