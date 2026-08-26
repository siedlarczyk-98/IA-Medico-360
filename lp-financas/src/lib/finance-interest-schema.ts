import { z } from "zod";

export const careerStages = [
  { value: "estudante", label: "Estudante de medicina" },
  { value: "residente", label: "Residente" },
  { value: "recem-formado", label: "Recém-formado" },
  { value: "consultorio-crescimento", label: "Consultório em crescimento" },
  { value: "consultorio-consolidado", label: "Consultório consolidado" },
] as const;

export const painPoints = [
  { value: "organizar-fluxo", label: "Não sei quanto sobra no fim do mês" },
  { value: "impostos-pj", label: "Impostos e gestão da PJ" },
  { value: "comecar-investir", label: "Não sei onde começar a investir" },
  { value: "dividas", label: "Dívidas e financiamentos" },
  { value: "objetivos-longo-prazo", label: "Planejar objetivos de longo prazo" },
  { value: "aposentadoria", label: "Independência financeira / aposentadoria" },
] as const;

const careerStageValues = careerStages.map((stage) => stage.value);
const painPointValues = painPoints.map((pain) => pain.value);

export const financeInterestSchema = z.object({
  careerStage: z.enum(careerStageValues as [string, ...string[]], {
    errorMap: () => ({ message: "Selecione seu momento de carreira." }),
  }),
  painPoint: z.enum(painPointValues as [string, ...string[]], {
    errorMap: () => ({ message: "Selecione sua principal dor financeira." }),
  }),
});

export type FinanceInterestInput = z.infer<typeof financeInterestSchema>;
