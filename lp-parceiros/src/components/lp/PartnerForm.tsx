import { CheckCircle2, Loader2 } from 'lucide-react'
import { useEffect, useState } from 'react'

import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { checkAlreadySubmitted, submitPartnerInterest } from '@/lib/api'
import { getLeadFromUrl } from '@/lib/lead'
import {
  careerStages,
  partnerInterestSchema,
  partnershipCategories,
  type PartnerInterestInput,
} from '@/lib/partner-interest-schema'

const emptyForm: PartnerInterestInput = {
  careerStage: '',
  categories: [],
  desiredBrands: '',
}

const selectClass =
  'h-11 w-full rounded-xl border border-input bg-background/70 px-3 text-sm text-foreground outline-none transition-colors focus-visible:border-brand focus-visible:ring-[3px] focus-visible:ring-brand/25'

const inputClass = selectClass

export function PartnerForm() {
  const [form, setForm] = useState<PartnerInterestInput>(emptyForm)
  const [errors, setErrors] = useState<Record<string, string>>({})
  const leadEmail = getLeadFromUrl().email
  const [status, setStatus] = useState<'checking' | 'idle' | 'sending' | 'done'>(
    leadEmail ? 'checking' : 'idle',
  )
  const [serverError, setServerError] = useState<string | null>(null)

  useEffect(() => {
    if (!leadEmail) return
    checkAlreadySubmitted(leadEmail)
      .then((already) => setStatus(already ? 'done' : 'idle'))
      // Falha no check (rede, CORS, backend fora) nao pode travar a LP num
      // skeleton pra sempre — melhor deixar preencher de novo do que
      // esconder o form inteiro por causa de um GET que falhou.
      .catch(() => setStatus('idle'))
  }, [leadEmail])

  function update<K extends keyof PartnerInterestInput>(key: K, value: PartnerInterestInput[K]) {
    setForm((prev) => ({ ...prev, [key]: value }))
    setErrors((prev) => {
      const next = { ...prev }
      delete next[key as string]
      return next
    })
  }

  function toggleCategory(category: string) {
    update(
      'categories',
      form.categories.includes(category)
        ? form.categories.filter((c) => c !== category)
        : [...form.categories, category],
    )
  }

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setServerError(null)

    const parsed = partnerInterestSchema.safeParse(form)
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
      const result = await submitPartnerInterest(parsed.data as PartnerInterestInput)
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
        <h3 className="text-2xl font-semibold">Resposta registrada</h3>
        <p className="max-w-md text-sm leading-relaxed text-muted-foreground">
          Obrigado por ajudar a moldar o clube de parcerias do Médico 360. Vamos avisar você assim
          que os primeiros parceiros entrarem no ar.
        </p>
      </div>
    )
  }

  return (
    <form onSubmit={handleSubmit} className="panel space-y-7 p-6 sm:p-9" noValidate>
      <div className="space-y-2">
        <Label className="text-sm" htmlFor="careerStage">
          Fase da carreira
        </Label>
        <select
          id="careerStage"
          className={selectClass}
          value={form.careerStage}
          onChange={(event) => update('careerStage', event.target.value)}
        >
          <option value="">Selecione</option>
          {careerStages.map((stage) => (
            <option key={stage} value={stage}>
              {stage}
            </option>
          ))}
        </select>
        {errors['careerStage'] && <p className="text-xs text-destructive">{errors['careerStage']}</p>}
      </div>

      <fieldset className="space-y-3">
        <legend className="text-sm font-medium">Quais categorias de parceria mais te interessam?</legend>
        <p className="text-xs text-muted-foreground">Pode marcar quantas quiser.</p>
        <div className="grid gap-2 sm:grid-cols-2">
          {partnershipCategories.map((category) => (
            <label
              key={category}
              className="flex cursor-pointer items-start gap-3 rounded-lg border border-border bg-secondary/40 p-3 text-sm transition-colors hover:border-brand/50"
            >
              <input
                type="checkbox"
                className="mt-0.5 size-4 shrink-0 accent-brand"
                checked={form.categories.includes(category)}
                onChange={() => toggleCategory(category)}
              />
              <span className="text-muted-foreground">{category}</span>
            </label>
          ))}
        </div>
        {errors['categories'] && <p className="text-xs text-destructive">{errors['categories']}</p>}
      </fieldset>

      <div className="space-y-2">
        <Label className="text-sm" htmlFor="desiredBrands">
          Tem alguma marca, app ou serviço que você usa muito e queria desconto ou integração?
        </Label>
        <input
          id="desiredBrands"
          type="text"
          maxLength={300}
          placeholder="Marca, app ou serviço"
          className={inputClass}
          value={form.desiredBrands}
          onChange={(event) => update('desiredBrands', event.target.value)}
        />
        {errors['desiredBrands'] && (
          <p className="text-xs text-destructive">{errors['desiredBrands']}</p>
        )}
      </div>

      {serverError && <p className="text-sm text-destructive">{serverError}</p>}

      <div className="space-y-3">
        <Button type="submit" size="lg" className="h-12 w-full rounded-xl text-base font-semibold" disabled={status === 'sending'}>
          {status === 'sending' && <Loader2 className="mr-2 size-4 animate-spin" />}
          Enviar minhas preferências
        </Button>
        <p className="text-center text-xs text-muted-foreground">
          Sem custo e sem compromisso. Usamos suas respostas apenas para priorizar as próximas
          parcerias.
        </p>
      </div>
    </form>
  )
}
