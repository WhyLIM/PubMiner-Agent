export interface BiomedicalEntity {
  id: string;
  name: string;
  type: 'gene' | 'disease' | 'drug' | 'pathway';
  count: number;
}

export interface RelationalTriple {
  subject: string;
  predicate: string; // e.g., 'INHIBITS', 'MUTATES_TO', 'SYNERGIZES_WITH', 'ASSOCIATED_WITH'
  object: string;
  confidence: number;
}

export interface Paper {
  id: string;
  pmid: string;
  doi: string;
  title: string;
  journal: string;
  year: number;
  authors: string;
  abstract: string;
  studyType: string;
  sampleSize?: number;
  hazardRatio?: string;
  pValue?: string;
  confidenceScore: number;
  screeningStatus: 'included' | 'excluded' | 'flagged' | 'unscreened';
  entities: {
    genes: string[];
    diseases: string[];
    drugs: string[];
    pathways: string[];
  };
  triples: RelationalTriple[];
  citations: number;
  openAccess: boolean;
  meshTerms: string[];
  biasRisk: 'Low' | 'Moderate' | 'High';
  // 扩展字段（来自后端 useResearch）
  signature?: string;
  supportCount?: number;
  contradictCount?: number;
  noEffectCount?: number;
  uncertainCount?: number;
  independentValidation?: boolean;
  evidenceCount?: number;
  /** 复核乐观锁所需的真实 claim 版本号 */
  claimVersion?: number;
}

export interface GraphNode {
  id: string;
  name: string;
  category: 0 | 1 | 2 | 3; // 0: Gene/Target, 1: Disease, 2: Drug, 3: Pathway
  symbolSize: number;
  value: number;
  color?: string;
  details?: string;
}

export interface GraphLink {
  source: string;
  target: string;
  relation: string;
  weight: number;
  evidenceCount: number;
}

export interface AgentStep {
  id: string;
  agentName: string;
  role: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  summary: string;
  logs: string[];
  durationMs: number;
  metrics: Record<string, string | number>;
  toolCalls?: { tool: string; args: string; result: string }[];
}

export interface ResearchTopic {
  id: string;
  title: string;
  englishTitle: string;
  subtitle: string;
  query: string;
  meshTerms: string[];
  papers: Paper[];
  graphNodes: GraphNode[];
  graphLinks: GraphLink[];
  trendYears: string[];
  pubCounts: number[];
  citationAverages: number[];
  cooccurrenceMatrix: {
    xLabels: string[];
    yLabels: string[];
    data: [number, number, number][]; // [xIndex, yIndex, value]
  };
  evidenceDistribution: { name: string; value: number }[];
  biomarkerRanking: { name: string; score: number; articles: number }[];
  reviewReport: string;
}
