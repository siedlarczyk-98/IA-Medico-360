export interface AIModelInfo {
  shortDescription: string;
  tags: string[];
  idealFor: string[];
  icon: string;
}

export const MODEL_DESCRIPTIONS: Record<string, AIModelInfo> = {
  'claude-sonnet-4-20250514': {
    icon: '🧠',
    shortDescription: 'Máximo desempenho em raciocínio complexo e criatividade',
    tags: ['Avançado', 'Preciso'],
    idealFor: ['Programação', 'Análise profunda', 'Escrita técnica'],
  },
  'gpt-4o': {
    icon: '⚖️',
    shortDescription: 'Versátil e balanceado para tarefas variadas',
    tags: ['Multimodal', 'Equilibrado'],
    idealFor: ['Análise de dados', 'Interpretação de imagens', 'Tarefas gerais'],
  },
  'sonar-pro': {
    icon: '🔍',
    shortDescription: 'Especialista em pesquisa e informações atualizadas',
    tags: ['Pesquisa', 'Atualizado'],
    idealFor: ['Checagem de fatos', 'Pesquisa web', 'Relatórios citados'],
  },
  'gpt-5.4-nano': {
    icon: '⚡',
    shortDescription: 'Ultrarrápido e econômico para volume alto',
    tags: ['Rápido', 'Econômico'],
    idealFor: ['Tarefas em massa', 'Classificação', 'Extração de dados'],
  },
  'gpt-5.4-mini': {
    icon: '💫',
    shortDescription: 'Raciocínio lógico rápido com alta performance',
    tags: ['Rápido', 'Eficiente'],
    idealFor: ['Decisões lógicas', 'Processamento rápido'],
  },
  'gemini-2.5-flash': {
    icon: '🚀',
    shortDescription: 'Velocidade e custo-benefício para contexto médico',
    tags: ['Rápido', 'Econômico'],
    idealFor: ['Análises clínicas', 'Interpretação de dados', 'Respostas reais'],
  },
};
