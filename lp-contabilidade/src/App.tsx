import {
  AlertTriangle,
  ArrowRight,
  Calculator,
  FileSpreadsheet,
  ReceiptText,
  ShieldCheck,
  Stethoscope,
} from 'lucide-react'

import heroImage from '@/assets/hero-contabilidade.jpg'
import { LeadForm } from '@/components/lp/LeadForm'
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from '@/components/ui/accordion'
import { Button } from '@/components/ui/button'

const painCards = [
  {
    icon: ReceiptText,
    title: 'Imposto pago no escuro',
    text: 'Sem enquadramento correto, é comum pagar milhares de reais a mais por ano — e nunca descobrir.',
  },
  {
    icon: FileSpreadsheet,
    title: 'Rendas espalhadas',
    text: 'Plantão, cooperativa, consultório e CLT ao mesmo tempo, sem ninguém consolidando nada.',
  },
  {
    icon: AlertTriangle,
    title: 'Contador genérico',
    text: 'Escritórios que não conhecem CNAE médico, equiparação hospitalar nem a rotina de plantão.',
  },
]

const faq = [
  {
    q: 'Isso já está disponível?',
    a: 'Ainda não. Estamos validando o interesse dos médicos da plataforma antes de abrir as primeiras vagas. Quem entrar na lista fala com o time antes do lançamento.',
  },
  {
    q: 'Já tenho contador. Faz sentido entrar na lista?',
    a: 'Sim. Boa parte do valor está no comparativo: mostramos quanto você paga hoje e quanto pagaria com o enquadramento ideal. A troca só acontece se compensar.',
  },
  {
    q: 'Atende residente e recém-formado?',
    a: 'Sim. Muitos médicos abrem PJ cedo demais ou tarde demais. O diagnóstico indica o melhor momento para cada fase da carreira.',
  },
  {
    q: 'Meus dados ficam seguros?',
    a: 'Suas respostas são usadas apenas para desenhar o produto e entrar em contato sobre o acesso antecipado. Nada é compartilhado com terceiros.',
  },
]

export function App() {
  return (
    <main className="min-h-screen bg-background text-foreground">
      <section className="relative overflow-hidden">
        <img
          src={heroImage}
          alt="Médico revisando documentos financeiros do consultório"
          width={1600}
          height={1104}
          className="absolute inset-0 size-full object-cover object-right opacity-70"
        />
        <div
          className="absolute inset-0"
          style={{
            background:
              'linear-gradient(95deg, var(--petrol-deep) 8%, color-mix(in oklab, var(--petrol-deep) 78%, transparent) 45%, transparent 85%)',
          }}
        />
        <div className="relative mx-auto grid max-w-6xl gap-10 px-6 py-20 sm:py-28 lg:grid-cols-[minmax(0,1fr)_320px]">
          <div className="max-w-xl">
            <span className="inline-flex items-center gap-2 rounded-full border border-brand/35 bg-brand/10 px-3 py-1 text-xs font-medium uppercase tracking-wide text-brand">
              <Stethoscope className="size-3.5" /> Em desenvolvimento no Médico 360
            </span>
            <h1 className="mt-6 text-4xl leading-[1.05] font-semibold sm:text-6xl">
              Sua contabilidade otimizada e no <span className="text-brand">piloto automático</span>
            </h1>

            <p className="mt-6 text-lg text-muted-foreground">
              Contabilidade feita só para médicos: abertura de PJ, impostos, guias, folha do
              consultório e planejamento tributário — tudo dentro da plataforma que você já usa.
            </p>
            <div className="mt-8 flex flex-wrap gap-3">
              <Button size="lg" className="h-12 rounded-xl px-8 text-base" asChild>
                <a href="#lista">
                  Entrar na lista de acesso <ArrowRight className="size-4" />
                </a>
              </Button>
            </div>

            <p className="mt-6 text-sm text-muted-foreground">
              Leva 2 minutos. Suas respostas definem o que vamos construir primeiro.
            </p>
          </div>
        </div>
      </section>

      <section className="mx-auto max-w-6xl px-6 py-20">
        <p className="text-sm font-medium uppercase tracking-widest text-brand">O problema</p>
        <h2 className="mt-3 max-w-2xl text-3xl font-semibold sm:text-4xl">
          Ninguém ensina contabilidade na faculdade de medicina
        </h2>
        <div className="mt-10 grid gap-5 md:grid-cols-3">
          {painCards.map(({ icon: Icon, title, text }) => (
            <article key={title} className="panel p-6">
              <Icon className="size-6 text-brand" />
              <h3 className="mt-4 text-lg font-semibold">{title}</h3>
              <p className="mt-2 text-sm leading-relaxed text-muted-foreground">{text}</p>
            </article>
          ))}
        </div>
      </section>

      <section id="lista" className="border-t border-border bg-card/40">
        <div className="mx-auto grid max-w-6xl gap-12 px-6 py-20 lg:grid-cols-[0.85fr_1.15fr]">
          <div className="lg:sticky lg:top-12 lg:self-start">
            <h2 className="text-3xl font-semibold sm:text-4xl">
              Garanta seu <span className="text-brand">acesso antecipado</span>
            </h2>
            <p className="mt-4 text-muted-foreground">
              Estamos selecionando os primeiros médicos para desenhar o serviço junto com o time.
              Quanto mais detalhes você der, mais o produto nasce parecido com a sua rotina.
            </p>
            <ul className="mt-8 space-y-3 text-sm text-muted-foreground">
              <li className="flex gap-3">
                <ShieldCheck className="size-5 shrink-0 text-brand" /> Prioridade nas primeiras
                vagas
              </li>
              <li className="flex gap-3">
                <Calculator className="size-5 shrink-0 text-brand" /> Diagnóstico tributário
                gratuito no lançamento
              </li>
              <li className="flex gap-3">
                <Stethoscope className="size-5 shrink-0 text-brand" /> Condição especial para
                membros do Médico 360
              </li>
            </ul>
          </div>
          <LeadForm />
        </div>
      </section>

      <section className="mx-auto max-w-3xl px-6 py-20">
        <h2 className="text-3xl font-semibold">Perguntas frequentes</h2>
        <Accordion type="single" collapsible className="mt-8">
          {faq.map(({ q, a }) => (
            <AccordionItem key={q} value={q}>
              <AccordionTrigger className="text-left">{q}</AccordionTrigger>
              <AccordionContent className="text-muted-foreground">{a}</AccordionContent>
            </AccordionItem>
          ))}
        </Accordion>
      </section>

      <footer className="border-t border-border px-6 py-10 text-center text-xs text-muted-foreground">
        Médico 360 — produto em validação. Nenhuma contratação é feita nesta página.
      </footer>
    </main>
  )
}
