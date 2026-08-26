import { z } from 'zod'

export const careerStages = [
  'Estudante de medicina',
  'Recém-formado',
  'Residente',
  'Médico plantonista',
  'Especialista com consultório',
  'Sócio de clínica',
] as const

export const partnershipCategories = [
  'Software de gestão',
  'Preparatório para residência médica',
  'Serviços financeiros',
  'Viagens',
  'Seguros',
  'Restaurantes',
  'Descontos em marcas',
] as const

export const partnerInterestSchema = z.object({
  careerStage: z.enum(careerStages, {
    errorMap: () => ({ message: 'Selecione seu momento de carreira.' }),
  }),
  categories: z.array(z.enum(partnershipCategories)).min(1, 'Selecione ao menos uma categoria.'),
  desiredBrands: z
    .string()
    .trim()
    .max(300, 'Máximo de 300 caracteres.')
    .optional()
    .or(z.literal('')),
})

export type PartnerInterestInput = {
  careerStage: string
  categories: string[]
  desiredBrands: string
}
