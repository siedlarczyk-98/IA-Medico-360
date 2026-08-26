import { CheckCircle2, Loader2 } from 'lucide-react'
import { useEffect, useState } from 'react'

import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { checkAlreadySubmitted, submitAccountingInterest } from '@/lib/api'
import {
  accountantStatuses,
  accountingInterestSchema,
  careerStages,
  incomeMethods,
  painPoints,
  revenueRanges,
  willingnessToPayOptions,
  type AccountingInterestInput,
} from '@/lib/accounting-interest-schema'
import { getLeadFromUrl } from '@/lib/lead'

const emptyForm: AccountingInterestInput = {
  careerStage: '',
  incomeMethod: '',
  accountantStatus: '',
  revenueRange: '',
  willingnessToPay: '',
  painPoints: [],
}

const selectClass =
  'h-11 w-full rounded-xl border border-input bg-background/70 px-3 text-sm text-foreground outline-none transition-colors focus-visible:border-brand focus-visible:ring-[3px] focus-visible:ring-brand/25'

function SelectField({
  label,
  value,
  onChange,
  options,
  error,
}: {
  label: string
  value: string
  onChange: (value: string) => void
  options: readonly string[]
  error?: string
}) {
  return (
    <div className="space-y-2">
      <Label className="text-sm">{label}</Label>
      <select className={selectClass} value={value} onChange={(event) => onChange(event.target.value)}>
        <option value="">Selecione</option>
        {options.map((option) => (
          <option key={option} value={option}>
            {option}
          </option>
        ))}
      </select>
      {error && <p className="text-xs text-destructive">{error}</p>}
    </div>
  )
}

export function LeadForm() {
  const [form, setForm] = useState<AccountingInterestInput>(emptyForm)
  const [errors, setErrors] = useState<Record<string, string>>({})
  const leadEmail = getLeadFromUrl().email
  const [status, setStatus] = useState<'checking' | 'idle' | 'sending' | 'done'>(
    leadEmail ? 'checking' : 'idle',
  )
  const [serverError, setServerError] = useState<string | null>(null)

  useEffect(() => {
    if (!leadEmail) return
    checkAlreadySubmitted(leadEmail).then((already) => {
      setStatus(already ? 'done' : 'idle')
    })
  }, [leadEmail])

  function update<K extends keyof AccountingInterestInput>(key: K, value: AccountingInterestInput[K]) {
    setForm((prev) => ({ ...prev, [key]: value }))
    setErrors((prev) => {
      const next = { ...prev }
      delete next[key as string]
      return next
    })
  }

  function togglePainPoint(point: string) {
    update(
      'painPoints',
      form.painPoints.includes(point)
        ? form.painPoints.filter((p) => p !== point)
        : [...form.painPoints, point],
    )
  }

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setServerError(null)

    const parsed = accountingInterestSchema.safeParse(form)
    if (!parsed.success) {
      const fieldErrors: Record<string, string> = {}
      for (const issue of parsed.error.issues) {
        const key = String(issue.path[0])
        if (!fieldErrors[key]) fieldErrors[key] = issue.message
      }
      setErrors(fieldErrors)
      return
    }

    setStatus('sending')
    try {
      const result = await submitAccountingInterest(parsed.data as AccountingInterestInput)
      if (result.ok) {
        setStatus('done')
      } else {
        setServerError(result.message)
        setStatus('idle')
      }
    } catch (error) {
      console.error(error)
      setServerError('Algo deu errado no envio. Tente novamente em instantes.')
      setStatus('idle')
    }
  }

  if (status === 'checking') {
    return <div className="panel h-64 animate-pulse p-10" aria-hidden />
  }

  if (status === 'done') {
    return (
      <div className="panel flex flex-col items-center gap-4 p-10 text-center">
        <span className="grid size-12 place-items-center rounded-2xl bg-brand/15 text-brand">
          <CheckCircle2 className="size-6" />
        </span>
        <h3 className="text-2xl font-semibold">Interesse registrado</h3>
        <p className="max-w-md text-sm leading-relaxed text-muted-foreground">
          Você entrou na lista de acesso antecipado da Contabilidade Médico 360. Vamos chamar você
          para uma conversa rápida antes do lançamento — suas respostas ajudam a definir o produto.
        </p>
      </div>
    )
  }

  return (
    <form onSubmit={handleSubmit} className="panel space-y-7 p-6 sm:p-9" noValidate>
      <div className="grid gap-5 sm:grid-cols-2">
        <SelectField
          label="Momento da carreira"
          value={form.careerStage}
          onChange={(v) => update('careerStage', v)}
          options={careerStages}
          error={errors['careerStage']}
        />
        <SelectField
          label="Como você recebe hoje"
          value={form.incomeMethod}
          onChange={(v) => update('incomeMethod', v)}
          options={incomeMethods}
          error={errors['incomeMethod']}
        />
        <SelectField
          label="Situação com contador"
          value={form.accountantStatus}
          onChange={(v) => update('accountantStatus', v)}
          options={accountantStatuses}
          error={errors['accountantStatus']}
        />
        <SelectField
          label="Faixa de faturamento"
          value={form.revenueRange}
          onChange={(v) => update('revenueRange', v)}
          options={revenueRanges}
          error={errors['revenueRange']}
        />
      </div>

      <fieldset className="space-y-3">
        <legend className="text-sm font-medium">O que mais te incomoda hoje?</legend>
        <div className="grid gap-2 sm:grid-cols-2">
          {painPoints.map((point) => (
            <label
              key={point}
              className="flex cursor-pointer items-start gap-3 rounded-lg border border-border bg-secondary/40 p-3 text-sm transition-colors hover:border-brand/50"
            >
              <input
                type="checkbox"
                className="mt-0.5 size-4 shrink-0 accent-brand"
                checked={form.painPoints.includes(point)}
                onChange={() => togglePainPoint(point)}
              />
              <span className="text-muted-foreground">{point}</span>
            </label>
          ))}
        </div>
        {errors['painPoints'] && <p className="text-xs text-destructive">{errors['painPoints']}</p>}
      </fieldset>

      <SelectField
        label="Quanto pagaria por esse serviço?"
        value={form.willingnessToPay}
        onChange={(v) => update('willingnessToPay', v)}
        options={willingnessToPayOptions}
        error={errors['willingnessToPay']}
      />

      {serverError && <p className="text-sm text-destructive">{serverError}</p>}

      <div className="space-y-3">
        <Button type="submit" size="lg" className="h-12 w-full rounded-xl text-base font-semibold" disabled={status === 'sending'}>
          {status === 'sending' && <Loader2 className="mr-2 size-4 animate-spin" />}
          Quero acesso antecipado
        </Button>
        <p className="text-center text-xs text-muted-foreground">
          Sem custo e sem compromisso. Usamos suas respostas apenas para desenhar o produto.
        </p>
      </div>
    </form>
  )
}
