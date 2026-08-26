import type { AccountingInterestInput } from './accounting-interest-schema'
import { getLeadFromUrl } from './lead'

const BASE = (import.meta.env.VITE_API_URL ?? 'http://localhost:8000').replace(/\/$/, '')

export async function submitAccountingInterest(data: AccountingInterestInput) {
  const lead = getLeadFromUrl()

  const response = await fetch(`${BASE}/api/v1/landing-pages/accounting/submit`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      name: lead.name,
      email: lead.email,
      email_missing: lead.emailMissing,
      career_stage: data.careerStage,
      income_method: data.incomeMethod,
      accountant_status: data.accountantStatus,
      revenue_range: data.revenueRange,
      willingness_to_pay: data.willingnessToPay,
      pain_points: data.painPoints,
    }),
  })

  if (!response.ok) {
    return { ok: false as const, message: 'Não conseguimos registrar seu interesse agora.' }
  }

  return { ok: true as const }
}
