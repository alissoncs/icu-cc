export const t = {
  app: "Treinador de Ciclismo",
  nav: { form: "Forma", activities: "Atividades", week: "Semana" },
  navLabel: "Navegação principal",
  loading: "Carregando…",
  retry: "Tentar de novo",
  errors: {
    config_missing: {
      title: "Configuração ausente",
      body: "O servidor ainda não tem a chave do Intervals.icu. Copie o arquivo .env.example para .env, preencha INTERVALS_API_KEY e reinicie a API.",
    },
    intervals_unauthorized: {
      title: "Chave do Intervals.icu recusada",
      body: "O Intervals.icu não aceitou a chave. Confira INTERVALS_API_KEY no arquivo .env (Configurações > Desenvolvedor no Intervals.icu) e reinicie a API.",
    },
    network_error: {
      title: "API fora do ar",
      body: "Não foi possível falar com a API. Verifique se ela está rodando na porta 8787.",
    },
    generic: { title: "Algo deu errado", body: "Não foi possível carregar os dados." },
  },
  status: { warning: "Aviso", error: "Erro" },
  form: {
    title: "Forma",
    ctl: "Condição (CTL)",
    atl: "Fadiga (ATL)",
    tsb: "Forma (TSB)",
    ramp: "Rampa (7 dias)",
    chartTitle: "Condição, fadiga e forma",
    range42: "42 dias",
    range90: "90 dias",
    range: "Período",
    today: "hoje",
    sourceIntervals: "Fonte: Intervals.icu",
    sourceComputed: "Fonte: calculado a partir das cargas",
    fresh: "descansado",
    neutral: "neutro",
    tired: "cansado",
    empty: "Sem dados de forma neste período.",
  },
  activities: {
    title: "Atividades",
    days: (n: number) => `${n} dias`,
    filter: "Período",
    date: "Data",
    name: "Nome",
    duration: "Duração",
    tss: "TSS",
    np: "NP",
    if: "IF",
    hr: "FC média",
    empty: "Nenhuma atividade neste período.",
  },
  activity: {
    back: "Voltar às atividades",
    metrics: "Métricas",
    np: "NP",
    if: "IF",
    tss: "TSS",
    vi: "VI",
    ef: "EF",
    decoupling: "Desacoplamento",
    kj: "Energia",
    distance: "Distância",
    elevation: "Altimetria",
    zones7: "Tempo por zona (Coggan)",
    zones3: "Distribuição em 3 zonas (Seiler)",
    low: "Baixa",
    moderate: "Moderada",
    high: "Alta",
    findings: "Leituras",
    warnings: "Avisos",
    noFindings: "Sem leituras para esta atividade.",
    ftpNote: (w: number) => `Zonas calculadas com FTP de ${w} W (estimativa, não limiar fisiológico).`,
  },
  week: {
    title: "Semana",
    prev: "Semana anterior",
    next: "Próxima semana",
    hours: "Horas",
    tss: "TSS",
    rides: "Treinos",
    distribution: "Distribuição de intensidade",
    assessment: "Avaliação",
    notes: "Observações",
    activities: "Atividades da semana",
    noDistribution: "Sem distribuição para esta semana.",
    models: {
      polarized: "Polarizado",
      pyramidal: "Piramidal",
      threshold: "Limiar",
      mixed: "Misto",
      unknown: "Indefinido",
    } as Record<string, string>,
  },
  units: { w: "W", km: "km", m: "m", kj: "kJ", h: "h" },
  none: "—",
};

const nf1 = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 1, minimumFractionDigits: 1 });
const nf0 = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 0 });
const nf2 = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 2, minimumFractionDigits: 2 });

export const fmt0 = (v: number | null | undefined) => (v == null ? t.none : nf0.format(v));
export const fmt1 = (v: number | null | undefined) => (v == null ? t.none : nf1.format(v));
export const fmt2 = (v: number | null | undefined) => (v == null ? t.none : nf2.format(v));

/** Seconds -> h:mm */
export function fmtDuration(s: number): string {
  const m = Math.round(s / 60);
  return `${Math.floor(m / 60)}:${String(m % 60).padStart(2, "0")}`;
}

/** YYYY-MM-DD -> dd/mm/aaaa */
export function fmtDate(iso: string): string {
  const [y, m, d] = iso.split("-");
  return `${d}/${m}/${y}`;
}

export function fmtShortDate(iso: string): string {
  const [, m, d] = iso.split("-");
  return `${d}/${m}`;
}
