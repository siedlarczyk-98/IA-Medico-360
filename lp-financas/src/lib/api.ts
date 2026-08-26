import type { FinanceInterestInput } from './finance-interest-schema'
import { getLeadFromUrl } from './lead'

const BASE = (import.meta.env.VITE_API_URL ?? 'http://localhost:8000').replace(/\/$/, '')

export async function submitFinanceInterest(data: FinanceInterestInput) {
  const lead = getLeadFromUrl()

  const response = await fetch(`${BASE}/api/v1/landing-pages/finance/submit`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      name: lead.name,
      email: lead.email,
      email_missing: lead.emailMissing,
      career_stage: data.careerStage,
      main_pain_point: data.painPoint,
    }),
  })

  if (!response.ok) {
    return { ok: false as const, message: 'Não foi possível salvar seu cadastro agora.' }
  }

  return { ok: true as const }
}
