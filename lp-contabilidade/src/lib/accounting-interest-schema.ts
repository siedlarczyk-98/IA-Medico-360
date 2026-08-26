import { z } from 'zod'

export const careerStages = [
  'Estudante de medicina',
  'Recém-formado',
  'Residente',
  'Médico plantonista',
  'Especialista com consultório',
  'Sócio de clínica',
] as const

export const incomeMethods = ['Pessoa Jurídica (PJ)', 'CLT', 'Autônomo / RPA', 'Misto'] as const

export const accountantStatuses = [
  'Não tenho contador',
  'Tenho, mas não gosto',
  'Tenho e estou satisfeito',
] as const

export const revenueRanges = [
  'Até R$ 15 mil/mês',
  'R$ 15 mil a R$ 40 mil/mês',
  'R$ 40 mil a R$ 80 mil/mês',
  'Acima de R$ 80 mil/mês',
  'Prefiro não informar',
] as const

export const willingnessToPayOptions = [
  'Até R$ 300/mês',
  'R$ 300 a R$ 600/mês',
  'R$ 600 a R$ 1.200/mês',
  'Depende do resultado',
  'Não pagaria nada',
] as const

export const painPoints = [
  'Não sei se pago imposto a mais',
  'Recebo de várias fontes (PJ, plantão, CLT)',
  'Meu contador não é especializado',
  'Perco prazos de guias e obrigações',
  'Quero abrir/regularizar minha PJ',
  'Folha e custos do consultório',
] as const

export const accountingInterestSchema = z.object({
  careerStage: z.enum(careerStages, {
    errorMap: () => ({ message: 'Selecione seu momento de carreira.' }),
  }),
  incomeMethod: z.enum(incomeMethods, {
    errorMap: () => ({ message: 'Selecione como você recebe hoje.' }),
  }),
  accountantStatus: z.enum(accountantStatuses, {
    errorMap: () => ({ message: 'Selecione sua situação com o contador.' }),
  }),
  revenueRange: z.enum(revenueRanges, {
    errorMap: () => ({ message: 'Selecione sua faixa de faturamento.' }),
  }),
  willingnessToPay: z.enum(willingnessToPayOptions, {
    errorMap: () => ({ message: 'Selecione quanto pagaria pelo serviço.' }),
  }),
  painPoints: z.array(z.enum(painPoints)).min(1, 'Selecione ao menos uma dor.'),
})

export type AccountingInterestInput = {
  careerStage: string
  incomeMethod: string
  accountantStatus: string
  revenueRange: string
  willingnessToPay: string
  painPoints: string[]
}
