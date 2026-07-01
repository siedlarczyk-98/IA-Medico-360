export interface VisibleWhen {
  field: string;
  equals?: unknown;
  notEquals?: unknown;
  includes?: unknown;
}

export interface FormField {
  key: string;
  visibleWhen?: VisibleWhen[];
}

export interface FormSection {
  title: string;
  collapsible?: boolean;
  fields: FormField[];
  visibleWhen?: VisibleWhen[];
  /** Substitui a seção por um separador visual com título — não renderiza campos. */
  isDivider?: boolean;
  dividerDescription?: string;
  /** Chave do passo (WizardStep) ao qual esta seção pertence. Se ausente, o formulário é renderizado em página única. */
  step?: string;
}

export interface WizardStep {
  key: string;
  title: string;
}

export interface FormSpec {
  sections: FormSection[];
  /** Se definido, o formulário é renderizado como wizard multi-etapas em vez de página única. */
  steps?: WizardStep[];
}

export const formSpecRegistry: Record<string, FormSpec | undefined> = {};
