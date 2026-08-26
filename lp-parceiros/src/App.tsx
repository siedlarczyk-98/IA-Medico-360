import { Rocket, Tag, Target } from 'lucide-react'

import heroImage from '@/assets/hero-parceiros.jpg'
import { PartnerForm } from '@/components/lp/PartnerForm'
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from '@/components/ui/accordion'
import { Button } from '@/components/ui/button'

const benefitCards = [
  {
    icon: Rocket,
    title: 'Acesso antecipado aos parceiros',
    text: 'Quem responde entra na primeira leva de convites, antes da abertura geral do clube.',
  },
  {
    icon: Target,
    title: 'Benefícios moldados à sua realidade',
    text: 'Cada resposta orienta quais empresas vamos negociar — de software de gestão a contabilidade médica.',
  },
  {
    icon: Tag,
    title: 'Descontos exclusivos na estreia',
    text: 'As condições de lançamento ficam reservadas para os médicos que ajudaram a construir o clube.',
  },
]

const faq = [
  {
    q: 'O que é o clube de parcerias do Médico 360?',
    a: 'É uma área dentro da plataforma reunindo descontos, integrações e serviços negociados especialmente para médicos, em todas as fases da carreira.',
  },
  {
    q: 'Quando estará disponível?',
    a: 'Estamos em fase de validação. As primeiras parcerias entram no ar assim que mapearmos as categorias mais pedidas por vocês.',
  },
  {
    q: 'Tem custo para o médico?',
    a: 'Não. O acesso ao clube faz parte da sua conta no Médico 360 — quem paga pela vitrine são as empresas parceiras.',
  },
  {
    q: 'Como vocês usam as minhas respostas?',
    a: 'Somente para priorizar parcerias e avisar você quando elas forem lançadas. Nada é compartilhado com terceiros.',
  },
]

export function App() {
  return (
    <main className="min-h-screen bg-background text-foreground">
      <section className="relative overflow-hidden">
        <img
          src={heroImage}
          alt="Médico usando tablet em uma clínica moderna"
          width={1600}
          height={1200}
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
              Em breve no Médico 360
            </span>
            <h1 className="mt-6 text-4xl leading-[1.05] font-semibold sm:text-6xl">
              Ajude a moldar o futuro do <span className="text-brand">Médico 360</span>
            </h1>

            <p className="mt-6 text-lg text-muted-foreground">
              Quais benefícios e ferramentas você quer ver aqui dentro? Estamos escolhendo os
              próximos parceiros do clube — e a decisão começa pela sua resposta.
            </p>
            <div className="mt-8 flex flex-wrap gap-3">
              <Button size="lg" className="h-12 rounded-xl px-8 text-base" asChild>
                <a href="#formulario">Quero escolher meus benefícios</a>
              </Button>
            </div>

            <p className="mt-6 text-sm text-muted-foreground">
              Leva menos de 2 minutos. Sem custo e sem compromisso.
            </p>
          </div>
        </div>
      </section>

      <section className="mx-auto max-w-6xl px-6 py-20">
        <p className="text-sm font-medium uppercase tracking-widest text-brand">Por que participar</p>
        <h2 className="mt-3 max-w-2xl text-3xl font-semibold sm:text-4xl">
          Você decide quem entra no clube de parcerias
        </h2>
        <div className="mt-10 grid gap-5 md:grid-cols-3">
          {benefitCards.map(({ icon: Icon, title, text }) => (
            <article key={title} className="panel p-6">
              <Icon className="size-6 text-brand" />
              <h3 className="mt-4 text-lg font-semibold">{title}</h3>
              <p className="mt-2 text-sm leading-relaxed text-muted-foreground">{text}</p>
            </article>
          ))}
        </div>
      </section>

      <section id="formulario" className="border-t border-border bg-card/40">
        <div className="mx-auto grid max-w-6xl gap-12 px-6 py-20 lg:grid-cols-[0.85fr_1.15fr]">
          <div className="lg:sticky lg:top-12 lg:self-start">
            <h2 className="text-3xl font-semibold sm:text-4xl">Diga o que você precisa</h2>
            <p className="mt-4 text-muted-foreground">
              Nos conte o que trava a sua rotina e quais serviços você já usa. Vamos atrás dessas
              empresas para negociar condições melhores para os médicos do Médico 360.
            </p>
          </div>
          <PartnerForm />
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
