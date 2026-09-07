export type Analysis = {
  fit_score: number;
  company_quality_score: number;
  career_value_score: number;
  german_advantage_score: number;
  location_score: number;
  recency_score: number;
  final_score: number;
  fit_breakdown: Record<string, { score: number; weight: number; points: number }>;
  boosts: { key: string; points: number; label: string }[];
  penalties: { key: string; points: number; label: string }[];
  eligible: boolean;
  not_eligible_reason: string | null;
  recommendation: string;
  match_reasons: string[];
  gaps: string[];
  hard_blockers: string[];
  summary: string | null;
  why_apply: string | null;
  confidence: number;
  analyzer: string;
  analyzed_at: string;
};

export type Job = {
  id: number;
  job_id: string;
  job_title: string;
  company: string;
  company_logo: string | null;
  company_quality_confidence: string;
  is_target_company: boolean;
  location: string | null;
  remote_type: string;
  employment_type: string | null;
  seniority: string;
  experience_label: string;
  languages: { code: string; name: string; requirement: string }[];
  skills: string[];
  salary_min: number | null;
  salary_max: number | null;
  salary_currency: string | null;
  salary_is_published: boolean;
  source: string;
  sources: string[];
  url: string;
  apply_url: string | null;
  publication_date: string | null;
  first_seen_date: string;
  is_new_today: boolean;
  is_repost: boolean;
  status: string;
  category_emoji: string;
  category_label: string;
  role_family: string | null;
  analysis: Analysis | null;
};

export type Resumen = {
  overview: string;
  responsabilidades: string[];
  requisitos: string[];
  deseables: string[];
  beneficios: string[];
  palabras: number;
  lectura_min: number;
  cobertura: "completo" | "parcial" | "sin_descripcion";
};

export type CompanyOverview = {
  company_id: number; name: string; category: string | null;
  ats_type: string | null; ats_label: string | null;
  is_target: boolean; german_relevant: boolean;
  quality_score: number | null; quality_confidence: string | null;
  total_jobs: number; eligible_jobs: number; recommended_jobs: number;
  new_today: number; best_score: number | null; logo_url: string | null;
};

export type JobDetail = Job & {
  description: string | null;
  requirements: string[];
  preferred_requirements: string[];
  education_requirements: string[];
  application_deadline: string | null;
  occurrences: { source: string; url: string; first_seen_at: string }[];
  application: Record<string, unknown> | null;
  resumen: Resumen | null;
};

export type TodaySummary = {
  nuevas_hoy: number;
  recomendadas: number;
  aplicar_ya: number;
  empresas_objetivo: number;
  con_aleman: number;
  threshold: number;
  ultima_corrida: {
    id: number; status: string; finished_at: string | null;
    new_jobs: number; raw_jobs: number; filtered_out: number; duration_ms: number;
  } | null;
};

export type Profile = {
  id: number; full_name: string; headline: string; university: string;
  degree: string; degree_field: string; graduation_year: number | null;
  education_extra: unknown[]; languages: { code: string; name: string; level: string }[];
  years_experience: number; has_formal_experience: boolean; experience_items: unknown[];
  skills: string[]; target_roles: string[]; role_families: string[]; excluded_areas: string[];
  city: string; region: string; country: string;
  accepts_remote: boolean; accepts_hybrid: boolean; accepts_onsite: boolean;
  max_commute_km: number | null; preferred_locations: string[];
  salary_expectation_min: number | null; salary_currency: string;
  favorite_companies: string[]; blocked_companies: string[];
  cv_filename: string | null; updated_at: string;
};

export type SourceHealth = {
  key: string; label: string; kind: string; enabled: boolean; status: string;
  last_run_at: string | null; last_found: number; last_error: string | null;
  avg_duration_ms: number | null; compliance_note: string | null; compliance_level: string;
};

export type TargetCompany = {
  id: number; company_id: number; name: string; category: string | null;
  priority: number; german_relevant: boolean; ats_type: string | null;
  ats_token: string | null; careers_url: string | null; enabled: boolean;
  suggested: boolean; quality_score: number | null; quality_confidence: string | null;
  active_jobs: number;
};

export type RunResult = {
  run_id: number; status: string; duration_ms: number; sources_queried: number;
  sources_failed: number; raw_jobs: number; new_jobs: number; duplicates: number;
  filtered_out: number; recommended: number; analyzed_llm: number;
  analyzed_heuristic: number; errors: { source: string; error: string }[];
  // Opcionales: GET /api/runs/{id} los devuelve dentro de `stats`, no en la raíz.
  filter_reasons?: Record<string, number>;
  sources?: { source: string; target: string; status: string; found: number; created: number; error: string | null }[];
};
