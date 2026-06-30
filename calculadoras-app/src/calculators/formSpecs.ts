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
}

export interface FormSpec {
  sections: FormSection[];
}

export const formSpecRegistry: Record<string, FormSpec | undefined> = {};
