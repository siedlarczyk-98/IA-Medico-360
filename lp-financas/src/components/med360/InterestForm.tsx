import { CheckCircle2, Loader2 } from 'lucide-react'
import { useState } from 'react'

import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { submitFinanceInterest } from '@/lib/api'
import {
  careerStages,
  financeInterestSchema,
  painPoints,
  type FinanceInterestInput,
} from '@/lib/finance-interest-schema'

const emptyForm: FinanceInterestInput = {
  careerStage: '',
  painPoint: '',
}

const selectClass =
  'h-11 w-full rounded-xl border border-input bg-background/70 px-3 text-sm text-foreground outline-none transition-colors focus-visible:border-brand focus-visible:ring-[3px] focus-visible:ring-brand/25'

export function InterestForm() {
  const [form, setForm] = useState<FinanceInterestInput>(emptyForm)
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [status, setStatus] = useState<'idle' | 'sending' | 'done'>('idle')
  const [serverError, setServerError] = useState<string | null>(null)

  function update<K extends keyof FinanceInterestInput>(key: K, value: string) {
    setForm((prev) => ({ ...prev, [key]: value }))
    setErrors((prev) => {
      const next = { ...prev }
      delete next[key as string]
      return next
    })
  }

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setServerError(null)

    const parsed = financeInterestSchema.safeParse(form)
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
      const result = await submitFinanceInterest(parsed.data)
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

  if (status === 'done') {
    return (
      <div className="panel flex flex-col items-start gap-4 p-8">
        <span className="grid size-12 place-items-center rounded-2xl bg-brand/15 text-brand">
          <CheckCircle2 className="size-6" />
        </span>
        <h3 className="text-2xl font-semibold">Interesse registrado</h3>
        <p className="max-w-lg text-sm leading-relaxed text-muted-foreground">
          Obrigado! Vamos avisar em primeiro lugar quando a área de gestão financeira abrir — e o que
          você contou aqui entra direto na priorização do que construímos primeiro.
        </p>
      </div>
    )
  }

  return (
    <form onSubmit={handleSubmit} className="panel p-6 sm:p-8" noValidate>
      <h3 className="text-2xl font-semibold">Entrar na lista de acesso antecipado</h3>
      <p className="mt-2 max-w-xl text-sm leading-relaxed text-muted-foreground">
        Duas perguntas rápidas. Suas respostas definem o que entra primeiro na área financeira.
      </p>

      <div className="mt-7 grid gap-5 sm:grid-cols-2">
        <div className="space-y-2">
          <Label htmlFor="careerStage">Momento de carreira</Label>
          <select
            id="careerStage"
            className={selectClass}
            value={form.careerStage}
            onChange={(event) => update('careerStage', event.target.value)}
          >
            <option value="">Selecione</option>
            {careerStages.map((stage) => (
              <option key={stage.value} value={stage.value}>
                {stage.label}
              </option>
            ))}
          </select>
          {errors['careerStage'] && (
            <p className="text-xs text-destructive">{errors['careerStage']}</p>
          )}
        </div>

        <div className="space-y-2">
          <Label htmlFor="painPoint">Principal dor financeira hoje</Label>
          <select
            id="painPoint"
            className={selectClass}
            value={form.painPoint}
            onChange={(event) => update('painPoint', event.target.value)}
          >
            <option value="">Selecione</option>
            {painPoints.map((pain) => (
              <option key={pain.value} value={pain.value}>
                {pain.label}
              </option>
            ))}
          </select>
          {errors['painPoint'] && <p className="text-xs text-destructive">{errors['painPoint']}</p>}
        </div>
      </div>

      {serverError && <p className="mt-5 text-sm text-destructive">{serverError}</p>}

      <div className="mt-7 flex flex-wrap items-center gap-4">
        <Button
          type="submit"
          size="lg"
          disabled={status === 'sending'}
          className="h-12 rounded-xl px-7 text-base font-semibold"
        >
          {status === 'sending' && <Loader2 className="mr-2 size-4 animate-spin" />}
          Quero acesso antecipado
        </Button>
        <p className="text-xs text-muted-foreground">
          Usamos suas respostas apenas para priorizar esta funcionalidade.
        </p>
      </div>
    </form>
  )
}
