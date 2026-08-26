import {
  ArrowDownRight,
  ArrowUpRight,
  ClipboardCheck,
  Compass,
  LineChart,
  Sparkles,
  Wallet,
} from 'lucide-react'

import heroImage from '@/assets/investimentos-hero.jpg'
import { InterestForm } from '@/components/med360/InterestForm'
import { Wordmark } from '@/components/med360/Wordmark'

const steps = [
  {
    icon: ClipboardCheck,
    step: 'Etapa 01',
    title: 'Diagnóstico financeiro',
    text: 'Um retrato honesto do seu momento: receitas de plantão, PJ e consultório, dívidas, reservas e quanto realmente sobra no fim do mês.',
  },
  {
    icon: Compass,
    step: 'Etapa 02',
    title: 'Objetivos de curto, médio e longo prazo',
    text: 'Da reserva de emergência à sala própria, da especialização à independência financeira — cada objetivo com prazo e valor definidos.',
  },
  {
    icon: Sparkles,
    step: 'Etapa 03',
    title: 'Consultoria especializada',
    text: 'Orientação de quem entende a carreira médica sobre como gerir e fazer crescer o seu patrimônio até chegar lá.',
  },
]

const platformFeatures = [
  {
    icon: Wallet,
    title: 'Gestão de gastos',
    text: 'Categorias pensadas para a rotina médica, de anuidade do CRM a impostos da PJ.',
  },
  {
    icon: ArrowUpRight,
    title: 'Gestão de rendimentos',
    text: 'Plantões, consultório, aulas e procedimentos em um só lugar, mês a mês.',
  },
  {
    icon: LineChart,
    title: 'Balanço mensal',
    text: 'Quanto entrou, quanto saiu e quanto foi para os seus objetivos — sem planilha.',
  },
]

export function App() {
  return (
    <div className="min-h-screen bg-background">
      <div className="mx-auto max-w-6xl px-4 pb-20 pt-6 sm:px-6 lg:px-10">
        <section className="relative overflow-hidden rounded-3xl border border-border bg-petrol-deep">
          <img
            src={heroImage}
            alt="Médico com tablet em consultório"
            width={1920}
            height={912}
            className="absolute inset-y-0 right-0 h-full w-full object-cover object-right opacity-70 sm:w-[68%]"
          />
          <div className="absolute inset-0 bg-gradient-to-r from-petrol-deep via-petrol-deep/95 to-transparent" />
          <div className="pointer-events-none absolute -right-10 top-1/2 hidden size-64 -translate-y-1/2 arc-360 opacity-80 md:block" />

          <div className="relative max-w-2xl px-6 py-14 sm:px-10 sm:py-20">
            <span className="inline-flex items-center gap-2 rounded-full border border-brand/40 bg-brand/10 px-3 py-1 text-xs font-semibold uppercase tracking-[0.16em] text-brand">
              Em breve
            </span>
            <Wordmark className="mt-7 block text-2xl sm:text-3xl" />
            <h1 className="mt-5 text-4xl font-semibold leading-[1.05] sm:text-5xl">
              Sua vida financeira
              <br />
              <span className="text-brand">em 360 graus.</span>
            </h1>
            <p className="mt-5 max-w-xl text-base leading-relaxed text-mint/90">
              A carreira médica avança em fases — e o dinheiro precisa acompanhar. Estamos
              construindo dentro do Médico 360 uma área para diagnosticar, planejar e gerir todo o
              seu patrimônio, com consultoria de quem entende a sua rotina.
            </p>
            <a
              href="#lista"
              className="mt-8 inline-flex h-12 items-center rounded-xl bg-primary px-7 text-base font-semibold text-primary-foreground transition-opacity hover:opacity-90"
            >
              Quero acesso antecipado
            </a>
          </div>
        </section>

        <section className="mt-14">
          <h2 className="text-sm font-semibold uppercase tracking-[0.16em] text-muted-foreground">
            Como vai funcionar
          </h2>
          <div className="mt-6 grid gap-4 md:grid-cols-3">
            {steps.map((step) => (
              <article key={step.title} className="panel flex flex-col gap-4 p-6">
                <span className="grid size-11 place-items-center rounded-2xl bg-brand/12 text-brand">
                  <step.icon className="size-5" />
                </span>
                <span className="text-xs font-semibold uppercase tracking-[0.16em] text-brand-soft">
                  {step.step}
                </span>
                <h3 className="text-xl font-semibold leading-snug">{step.title}</h3>
                <p className="text-sm leading-relaxed text-muted-foreground">{step.text}</p>
              </article>
            ))}
          </div>
        </section>

        <section className="mt-14 grid gap-4 lg:grid-cols-[1.05fr_1fr] lg:items-stretch">
          <div className="panel p-6 sm:p-8">
            <h2 className="text-2xl font-semibold">Dentro da plataforma</h2>
            <p className="mt-3 max-w-lg text-sm leading-relaxed text-muted-foreground">
              Além da consultoria, o dia a dia também fica aqui: gastos, rendimentos e o balanço de
              cada mês, sempre à mão.
            </p>
            <div className="mt-7 space-y-5">
              {platformFeatures.map((feature) => (
                <div key={feature.title} className="flex gap-4">
                  <span className="mt-0.5 grid size-10 shrink-0 place-items-center rounded-xl bg-secondary text-brand">
                    <feature.icon className="size-4" />
                  </span>
                  <div>
                    <h3 className="font-semibold">{feature.title}</h3>
                    <p className="mt-1 text-sm leading-relaxed text-muted-foreground">
                      {feature.text}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="panel relative overflow-hidden p-6 sm:p-8">
            <span className="inline-flex items-center rounded-full border border-border px-3 py-1 text-[0.7rem] uppercase tracking-[0.14em] text-muted-foreground">
              Prévia do conceito
            </span>
            <div className="mt-6 space-y-4" aria-hidden>
              <div className="rounded-2xl border border-border bg-background/60 p-5">
                <p className="text-xs uppercase tracking-[0.14em] text-muted-foreground">
                  Balanço de outubro
                </p>
                <p className="mt-2 text-3xl font-semibold text-brand">+ R$ 18.400</p>
                <div className="mt-4 flex h-2 overflow-hidden rounded-full bg-secondary">
                  <span className="h-full w-[62%] bg-brand" />
                  <span className="h-full w-[38%] bg-brand-soft" />
                </div>
                <div className="mt-3 flex justify-between text-xs text-muted-foreground">
                  <span>Objetivos 62%</span>
                  <span>Custos fixos 38%</span>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div className="rounded-2xl border border-border bg-background/60 p-4">
                  <ArrowUpRight className="size-4 text-brand" />
                  <p className="mt-3 text-xs text-muted-foreground">Rendimentos</p>
                  <p className="text-lg font-semibold">R$ 46.200</p>
                </div>
                <div className="rounded-2xl border border-border bg-background/60 p-4">
                  <ArrowDownRight className="size-4 text-mint" />
                  <p className="mt-3 text-xs text-muted-foreground">Gastos</p>
                  <p className="text-lg font-semibold">R$ 27.800</p>
                </div>
              </div>
            </div>
            <p className="mt-6 text-xs leading-relaxed text-muted-foreground">
              Valores ilustrativos de um conceito em desenvolvimento.
            </p>
          </div>
        </section>

        <section id="lista" className="mt-14 scroll-mt-8">
          <InterestForm />
        </section>

        <p className="mt-8 max-w-2xl text-xs leading-relaxed text-muted-foreground">
          Funcionalidade em desenvolvimento. Ao entrar na lista, você ajuda a definir o que
          construímos primeiro na área financeira do Médico 360.
        </p>
      </div>
    </div>
  )
}
