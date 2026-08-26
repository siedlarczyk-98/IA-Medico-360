import type { PartnerInterestInput } from './partner-interest-schema'
import { getLeadFromUrl } from './lead'

const BASE = (import.meta.env.VITE_API_URL ?? 'http://localhost:8000').replace(/\/$/, '')

export async function checkAlreadySubmitted(email: string) {
  const response = await fetch(
    `${BASE}/api/v1/landing-pages/partners/check?email=${encodeURIComponent(email)}`,
  )
  if (!response.ok) return false
  const data = (await response.json()) as { already_submitted: boolean }
  return data.already_submitted
}

export async function submitPartnerInterest(data: PartnerInterestInput) {
  const lead = getLeadFromUrl()

  const response = await fetch(`${BASE}/api/v1/landing-pages/partners/submit`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      name: lead.name,
      email: lead.email,
      email_missing: lead.emailMissing,
      career_stage: data.careerStage,
      categories: data.categories,
      desired_brands: data.desiredBrands || null,
    }),
  })

  if (!response.ok) {
    return { ok: false as const, message: 'Não conseguimos registrar seu interesse agora.' }
  }

  return { ok: true as const }
}
