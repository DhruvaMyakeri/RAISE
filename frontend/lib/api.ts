import type { Company, CompanyProfile, BenchmarkCorpus } from "./types";

export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:8001";

// Optional shared token matching the backend's VANTAGE_API_TOKEN. Note: any
// NEXT_PUBLIC_ value ships to the browser — this gates casual/cost abuse of a
// deployed demo, it is not a secret-grade credential.
const API_TOKEN = process.env.NEXT_PUBLIC_API_TOKEN ?? "";

function authHeaders(): Record<string, string> {
  return API_TOKEN ? { Authorization: `Bearer ${API_TOKEN}` } : {};
}

export async function fetchCompanies(): Promise<Company[]> {
  const res = await fetch(`${API_BASE}/api/companies`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Failed to load companies (${res.status})`);
  return res.json();
}

export async function fetchCompanySource(id: string): Promise<CompanyProfile> {
  const res = await fetch(`${API_BASE}/api/companies/${id}/source`, {
    cache: "no-store",
  });
  if (!res.ok) throw new Error(`Failed to load source data (${res.status})`);
  return res.json();
}

export async function fetchBenchmarks(
  categoryKey: string
): Promise<BenchmarkCorpus> {
  const res = await fetch(`${API_BASE}/api/benchmarks/${categoryKey}`, {
    cache: "no-store",
  });
  if (!res.ok) throw new Error(`Failed to load benchmark corpus (${res.status})`);
  return res.json();
}

export type EarlyAccessStatus = "registered" | "already_registered";

export async function submitEarlyAccess(
  email: string
): Promise<EarlyAccessStatus> {
  const res = await fetch(`${API_BASE}/api/early-access`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ email }),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(data?.detail ?? `Signup failed (${res.status})`);
  }
  return data.status as EarlyAccessStatus;
}

export async function fetchIntakeFields(): Promise<import("./types").IntakeFields> {
  const res = await fetch(`${API_BASE}/api/intake/fields`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Failed to load intake fields (${res.status})`);
  return res.json();
}

export async function extractProfile(
  file: File
): Promise<import("./types").ExtractionResult> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${API_BASE}/api/extract-profile`, {
    method: "POST",
    headers: authHeaders(),
    body: form,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data?.detail ?? `Extraction failed (${res.status})`);
  return data;
}

export async function prepareRun(
  category: string,
  values: Record<string, string | number>
): Promise<string> {
  const res = await fetch(`${API_BASE}/api/run/prepare`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ category, values }),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data?.detail ?? `Could not prepare run (${res.status})`);
  return data.run_id as string;
}

export function streamUrlForRun(runId: string): string {
  const params = new URLSearchParams({ run_id: runId });
  if (API_TOKEN) params.set("token", API_TOKEN);
  return `${API_BASE}/api/run/stream?${params.toString()}`;
}

export function streamUrl(categoryKey: string, companyId: string): string {
  const params = new URLSearchParams({
    category: categoryKey,
    company_id: companyId,
  });
  // EventSource cannot set headers; the backend accepts ?token= for SSE.
  if (API_TOKEN) params.set("token", API_TOKEN);
  return `${API_BASE}/api/run/stream?${params.toString()}`;
}
