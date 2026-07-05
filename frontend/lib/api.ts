import type { Company, CompanyProfile, BenchmarkCorpus } from "./types";

export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:8001";

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
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email }),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(data?.detail ?? `Signup failed (${res.status})`);
  }
  return data.status as EarlyAccessStatus;
}

export function streamUrl(categoryKey: string, companyId: string): string {
  const params = new URLSearchParams({
    category: categoryKey,
    company_id: companyId,
  });
  return `${API_BASE}/api/run/stream?${params.toString()}`;
}
