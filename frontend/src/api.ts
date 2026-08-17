const BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'
export type Segment = { id: string; text: string }
export type Result = { summary: { total_errors: number; caught: number; missed: number; false_challenges: number }; errors: Array<{ id:string; presented_statement:string; source_supported_statement:string; caught:boolean; explanation:string; source_evidence:string }> }
async function request<T>(path:string, options?:RequestInit):Promise<T> {
  const response = await fetch(`${BASE}${path}`, { ...options, headers: { 'Content-Type':'application/json', ...options?.headers } })
  const data = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(data.detail || 'The request could not be completed.')
  return data as T
}
export const api = {
  create: (source_text:string) => request<{session_id:string;segment_count:number;first_segment:Segment}>('/api/sessions',{method:'POST',body:JSON.stringify({source_text})}),
  next: (id:string) => request<{completed?:boolean;segment?:Segment;index?:number;total?:number}>(`/api/sessions/${id}/continue`,{method:'POST'}),
  challenge: (id:string, segment_id:string, reason:string) => request<{valid:boolean;reasoning_score:number;feedback:string}>(`/api/sessions/${id}/challenge`,{method:'POST',body:JSON.stringify({segment_id,reason})}),
  result: (id:string) => request<Result>(`/api/sessions/${id}/result`),
}
