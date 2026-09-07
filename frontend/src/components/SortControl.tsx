"use client";

/** Orden compartido por todas las listas de empleos: mismo control, misma semántica. */

export type SortField =
  | "final_score" | "fit_score" | "company_score" | "career_score"
  | "german" | "published" | "date";
export type SortDir = "desc" | "asc";

export type Sort = { field: SortField; dir: SortDir };

export const SORT_DEFAULT: Sort = { field: "final_score", dir: "desc" };
export const SORT_RECIENTES: Sort = { field: "date", dir: "desc" };

const CAMPOS: { value: SortField; label: string; tipo: "puntaje" | "fecha" }[] = [
  { value: "final_score", label: "Puntaje final", tipo: "puntaje" },
  { value: "fit_score", label: "Fit con tu perfil", tipo: "puntaje" },
  { value: "company_score", label: "Calidad de empresa", tipo: "puntaje" },
  { value: "career_score", label: "Valor de carrera", tipo: "puntaje" },
  { value: "german", label: "Ventaja del alemán", tipo: "puntaje" },
  // "Antigüedad" y no "Fecha de publicación": cuando la fuente no informa la
  // publicación se usa la fecha de descubrimiento, igual que muestra la tarjeta.
  { value: "published", label: "Antigüedad del aviso", tipo: "fecha" },
  { value: "date", label: "Cuándo se encontró", tipo: "fecha" },
];

/** La etiqueta de dirección cambia según el campo: "mejor" no aplica a una fecha. */
function etiquetaDireccion(field: SortField, dir: SortDir): string {
  const tipo = CAMPOS.find((c) => c.value === field)?.tipo ?? "puntaje";
  if (tipo === "fecha") {
    return dir === "desc" ? "↓ Más reciente primero" : "↑ Más antiguo primero";
  }
  return dir === "desc" ? "↓ Mejor primero" : "↑ Peor primero";
}

export function sortToQuery(sort: Sort): string {
  return `order_by=${sort.field}&order_dir=${sort.dir}`;
}

export function SortControl({ sort, onChange, compact }: {
  sort: Sort;
  onChange: (sort: Sort) => void;
  compact?: boolean;
}) {
  return (
    <div className={`flex flex-wrap items-center gap-2 ${compact ? "" : "sm:gap-3"}`}>
      {!compact && (
        <span className="text-xs font-semibold uppercase tracking-wide text-ink-500">
          Ordenar
        </span>
      )}
      <select
        className="input w-auto min-w-44 py-1.5 text-sm"
        value={sort.field}
        title={
          sort.field === "published"
            ? "Usa la fecha de publicación; si la fuente no la informa, la de descubrimiento."
            : undefined
        }
        onChange={(e) => onChange({ ...sort, field: e.target.value as SortField })}
      >
        {CAMPOS.map((c) => (
          <option key={c.value} value={c.value}>{c.label}</option>
        ))}
      </select>
      <button
        type="button"
        className="btn-ghost whitespace-nowrap px-3 py-1.5 text-xs"
        onClick={() => onChange({ ...sort, dir: sort.dir === "desc" ? "asc" : "desc" })}
        title="Invertir el orden"
      >
        {etiquetaDireccion(sort.field, sort.dir)}
      </button>
    </div>
  );
}
