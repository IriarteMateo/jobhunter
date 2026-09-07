"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const LINKS = [
  { href: "/", label: "Hoy" },
  { href: "/recientes", label: "Recientes" },
  { href: "/top-picks", label: "Top Picks" },
  { href: "/empleos", label: "Empleos" },
  { href: "/empresas", label: "Empresas" },
  { href: "/aleman", label: "Alemán" },
  { href: "/historial", label: "Historial" },
  { href: "/estadisticas", label: "Métricas" },
  { href: "/perfil", label: "Perfil" },
  { href: "/config", label: "Config" },
];

export function Nav() {
  const pathname = usePathname();
  return (
    <header className="sticky top-0 z-30 border-b border-ink-200/70 bg-ink-50/85 backdrop-blur dark:border-ink-800 dark:bg-ink-950/85">
      <div className="mx-auto flex w-full max-w-6xl items-center gap-4 px-4 py-3 sm:px-6">
        <Link href="/" className="flex shrink-0 items-center gap-2 font-semibold tracking-tight">
          <span className="grid h-7 w-7 place-items-center rounded-lg bg-ink-900 text-xs text-white dark:bg-white dark:text-ink-950">
            JH
          </span>
          <span className="hidden sm:inline">Job Hunter</span>
        </Link>
        <nav className="-mx-1 flex flex-1 gap-1 overflow-x-auto">
          {LINKS.map((link) => {
            const active = pathname === link.href;
            return (
              <Link
                key={link.href}
                href={link.href}
                className={`whitespace-nowrap rounded-lg px-3 py-1.5 text-sm font-medium transition-colors ${
                  active
                    ? "bg-ink-900 text-white dark:bg-white dark:text-ink-950"
                    : "text-ink-600 hover:bg-ink-200/60 dark:text-ink-300 dark:hover:bg-ink-800"
                }`}
              >
                {link.label}
              </Link>
            );
          })}
        </nav>
      </div>
    </header>
  );
}
