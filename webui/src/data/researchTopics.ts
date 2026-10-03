import { ResearchTopic, Paper } from '../types';

export const RESEARCH_TOPICS: ResearchTopic[] = [
  {
    id: 'egfr-resistance',
    title: 'EGFR T790M/C797S 突变靶向耐药与双靶协同策略',
    englishTitle: 'Targeted Resistance Mechanisms to EGFR TKIs (T790M/C797S) & Dual-Target Synergy in NSCLC',
    subtitle: '非小细胞肺癌三代 TKI 奥希替尼获得性耐药网络、MET旁路激活与四代变构抑制剂前沿',
    query: '(EGFR[MeSH] OR "Epidermal Growth Factor Receptor") AND (T790M OR C797S) AND (Osimertinib OR "MET amplification") AND (Resistance OR "Bypass Pathway")',
    meshTerms: [
      'Carcinoma, Non-Small-Cell Lung/genetics',
      'ErbB Receptors/antagonists & inhibitors',
      'Drug Resistance, Neoplasm/genetics',
      'Protein Kinase Inhibitors/therapeutic use',
      'Proto-Oncogene Proteins c-met/antagonists & inhibitors'
    ],
    trendYears: ['2019', '2020', '2021', '2022', '2023', '2024', '2025', '2026'],
    pubCounts: [412, 538, 720, 894, 1105, 1280, 1450, 1620],
    citationAverages: [28.4, 34.2, 42.8, 51.6, 60.1, 68.4, 75.2, 81.0],
    cooccurrenceMatrix: {
      xLabels: ['Osimertinib', 'Savolitinib', 'Amivantamab', 'Lazertinib', 'Gefitinib', 'BLU-945'],
      yLabels: ['EGFR-T790M', 'EGFR-C797S', 'MET-Amp', 'HER2-Amp', 'PIK3CA', 'BRAF-V600E'],
      data: [
        [0, 0, 94], [0, 1, 88], [0, 2, 76], [0, 3, 52], [0, 4, 38], [0, 5, 29],
        [1, 0, 24], [1, 1, 31], [1, 2, 92], [1, 3, 18], [1, 4, 14], [1, 5, 11],
        [2, 0, 68], [2, 1, 82], [2, 2, 85], [2, 3, 44], [2, 4, 31], [2, 5, 19],
        [3, 0, 72], [3, 1, 59], [3, 2, 46], [3, 3, 28], [3, 4, 22], [3, 5, 16],
        [4, 0, 89], [4, 1, 12], [4, 2, 25], [4, 3, 19], [4, 4, 15], [4, 5, 8],
        [5, 0, 41], [5, 1, 91], [5, 2, 34], [5, 3, 21], [5, 4, 18], [5, 5, 12]
      ]
    },
    evidenceDistribution: [
      { name: 'Phase III Randomized Trials', value: 34 },
      { name: 'Phase I/II Clinical Trials', value: 89 },
      { name: 'Prospective Cohorts', value: 142 },
      { name: 'Preclinical & In Vitro Models', value: 310 },
      { name: 'Systematic Reviews & Meta', value: 45 }
    ],
    biomarkerRanking: [
      { name: 'EGFR C797S 顺反式突变', score: 96.4, articles: 482 },
      { name: 'MET 基因局灶性扩增', score: 91.8, articles: 395 },
      { name: 'HER2 (ERBB2) 外显子20插入', score: 79.2, articles: 218 },
      { name: 'PIK3CA E545K 激活突变', score: 72.5, articles: 164 },
      { name: 'BRAF V600E 旁路激活', score: 65.3, articles: 129 },
      { name: 'RET / ALK 继发融合', score: 58.7, articles: 87 }
    ],
    graphNodes: [
      { id: 'EGFR', name: 'EGFR (靶点)', category: 0, symbolSize: 52, value: 95, details: '表皮生长因子受体酪氨酸激酶，驱动非小细胞肺癌发生发展的关键致癌驱动基因。' },
      { id: 'T790M', name: 'T790M 突变', category: 0, symbolSize: 42, value: 84, details: '门控残基突变，引起一代/二代TKI空间位阻并增强ATP亲和力。' },
      { id: 'C797S', name: 'C797S 突变', category: 0, symbolSize: 46, value: 90, details: '三代奥希替尼共价结合半胱氨酸位点丢失，导致获得性耐药核心突变。' },
      { id: 'MET', name: 'MET 扩增', category: 0, symbolSize: 44, value: 88, details: '受体酪氨酸激酶旁路扩增，独立激活下游ERBB3-PI3K-Akt信号通路。' },
      { id: 'HER2', name: 'HER2 (ERBB2)', category: 0, symbolSize: 32, value: 65, details: '旁路代偿激活成员，介导非依赖性生存信号传导。' },
      { id: 'PI3K_AKT', name: 'PI3K-Akt 信号通路', category: 3, symbolSize: 38, value: 78, details: '关键抗凋亡与细胞生存增殖传导轴。' },
      { id: 'MAPK', name: 'MAPK/ERK 通路', category: 3, symbolSize: 36, value: 74, details: '有丝分裂原激活蛋白激酶通路，调控肿瘤侵袭与增殖。' },
      { id: 'NSCLC', name: '非小细胞肺癌 (NSCLC)', category: 1, symbolSize: 56, value: 98, details: '占原发性肺癌 85% 以上，腺癌亚型中常见驱动基因变异。' },
      { id: 'BrainMet', name: '中枢神经系统脑转移', category: 1, symbolSize: 34, value: 62, details: '高发转移部位，三代奥希替尼及双抗组合具有穿透血脑屏障优势。' },
      { id: 'Osimertinib', name: '奥希替尼 (Osimertinib)', category: 2, symbolSize: 54, value: 96, details: '第三代不可逆口服 EGFR-TKI，针对经典敏感突变及 T790M。' },
      { id: 'Savolitinib', name: '赛沃替尼 (Savolitinib)', category: 2, symbolSize: 40, value: 80, details: '高选择性口服 MET 受体酪氨酸激酶抑制剂，联合奥希替尼克服MET耐药。' },
      { id: 'Amivantamab', name: '埃万妥单抗 (Amivantamab)', category: 2, symbolSize: 42, value: 82, details: 'EGFR/MET 双特异性抗体，靶向受体降解并诱导ADCC免疫杀伤效应。' },
      { id: 'BLU_945', name: 'BLU-945 (四代变构抑制剂)', category: 2, symbolSize: 35, value: 70, details: '针对 EGFR 敏感突变结合 C797S 与 T790M 三重突变的新型四代药物。' }
    ],
    graphLinks: [
      { source: 'Osimertinib', target: 'EGFR', relation: 'INHIBITS', weight: 9.8, evidenceCount: 420 },
      { source: 'Osimertinib', target: 'T790M', relation: 'INHIBITS', weight: 9.5, evidenceCount: 380 },
      { source: 'EGFR', target: 'C797S', relation: 'MUTATES_TO', weight: 8.9, evidenceCount: 295 },
      { source: 'C797S', target: 'Osimertinib', relation: 'RESISTS', weight: 9.2, evidenceCount: 310 },
      { source: 'EGFR', target: 'NSCLC', relation: 'DRIVES', weight: 9.9, evidenceCount: 560 },
      { source: 'MET', target: 'NSCLC', relation: 'ASSOCIATED_WITH', weight: 8.6, evidenceCount: 210 },
      { source: 'MET', target: 'PI3K_AKT', relation: 'ACTIVATES', weight: 9.1, evidenceCount: 245 },
      { source: 'EGFR', target: 'MAPK', relation: 'ACTIVATES', weight: 8.8, evidenceCount: 230 },
      { source: 'Savolitinib', target: 'MET', relation: 'INHIBITS', weight: 9.4, evidenceCount: 198 },
      { source: 'Osimertinib', target: 'Savolitinib', relation: 'SYNERGIZES_WITH', weight: 9.3, evidenceCount: 178 },
      { source: 'Amivantamab', target: 'EGFR', relation: 'BINDS_AND_DEGRADES', weight: 9.0, evidenceCount: 204 },
      { source: 'Amivantamab', target: 'MET', relation: 'BINDS_AND_DEGRADES', weight: 9.0, evidenceCount: 195 },
      { source: 'BLU_945', target: 'C797S', relation: 'SELECTIVELY_INHIBITS', weight: 8.7, evidenceCount: 112 },
      { source: 'Osimertinib', target: 'BrainMet', relation: 'IMPROVES_SURVIVAL', weight: 8.4, evidenceCount: 160 },
      { source: 'HER2', target: 'MAPK', relation: 'ACTIVATES', weight: 7.9, evidenceCount: 88 }
    ],
    papers: [
      {
        id: 'p1',
        pmid: '37812836',
        doi: '10.1056/NEJMoa2308795',
        title: 'Amivantamab plus Lazertinib in Previously Untreated EGFR-Mutated Advanced Non-Small-Cell Lung Cancer',
        journal: 'New England Journal of Medicine (NEJM)',
        year: 2024,
        authors: 'Cho BC, Felip E, Spira AI, et al. (MARIPOSA Investigators)',
        abstract: 'In this global, randomized phase 3 trial, amivantamab (an EGFR-MET bispecific antibody) combined with lazertinib significantly prolonged progression-free survival compared to osimertinib monotherapy in treatment-naive advanced NSCLC harboring classical EGFR mutations. The dual blockade delayed secondary resistance including MET amplification and C797S emergence.',
        studyType: 'Clinical Trial Phase III',
        sampleSize: 1074,
        hazardRatio: 'HR = 0.70 (95% CI 0.58-0.85)',
        pValue: 'p < 0.001',
        confidenceScore: 98,
        screeningStatus: 'included',
        citations: 284,
        openAccess: true,
        biasRisk: 'Low',
        meshTerms: ['Carcinoma, Non-Small-Cell Lung', 'ErbB Receptors', 'Antineoplastic Agents', 'Progression-Free Survival'],
        entities: {
          genes: ['EGFR', 'MET'],
          diseases: ['Non-Small-Cell Lung Cancer', 'Metastatic Adenocarcinoma'],
          drugs: ['Amivantamab', 'Lazertinib', 'Osimertinib'],
          pathways: ['Receptor Tyrosine Kinase signaling', 'ADCC Immune Induction']
        },
        triples: [
          { subject: 'Amivantamab', predicate: 'SYNERGIZES_WITH', object: 'Lazertinib', confidence: 0.98 },
          { subject: 'Amivantamab', predicate: 'INHIBITS', object: 'MET', confidence: 0.96 },
          { subject: 'Lazertinib', predicate: 'INHIBITS', object: 'EGFR', confidence: 0.97 }
        ]
      },
      {
        id: 'p2',
        pmid: '36972041',
        doi: '10.1016/S1470-2045(23)00085-7',
        title: 'Osimertinib plus Savolitinib in EGFR-mutated MET-amplified advanced NSCLC: The Phase II SAVANNAH Trial',
        journal: 'The Lancet Oncology',
        year: 2023,
        authors: 'Sequist LV, Han JY, Ahn MJ, et al.',
        abstract: 'SAVANNAH evaluated savolitinib combined with osimertinib in patients who developed disease progression on prior osimertinib due to high MET gene copy number amplification or MET protein overexpression. High-MET subgroup achieved an objective response rate of 49% and median PFS of 7.1 months, validating MET co-inhibition as standard targeted rescue.',
        studyType: 'Clinical Trial Phase I/II',
        sampleSize: 293,
        hazardRatio: 'ORR = 49%, mPFS = 7.1 mo',
        pValue: 'p = 0.002',
        confidenceScore: 94,
        screeningStatus: 'included',
        citations: 196,
        openAccess: true,
        biasRisk: 'Low',
        meshTerms: ['Receptor Protein-Tyrosine Kinases', 'Gene Amplification', 'Lung Neoplasms'],
        entities: {
          genes: ['EGFR', 'MET', 'ERBB3'],
          diseases: ['EGFR-TKI Resistant NSCLC'],
          drugs: ['Osimertinib', 'Savolitinib'],
          pathways: ['PI3K-Akt Bypass', 'HGF-MET Axis']
        },
        triples: [
          { subject: 'Savolitinib', predicate: 'INHIBITS', object: 'MET', confidence: 0.96 },
          { subject: 'Osimertinib+Savolitinib', predicate: 'OVERCOMES_RESISTANCE', object: 'EGFR-TKI Resistant NSCLC', confidence: 0.94 }
        ]
      },
      {
        id: 'p3',
        pmid: '35894982',
        doi: '10.1158/2159-8290.CD-22-0428',
        title: 'Structural Basis and Preclinical Activity of BLU-945, a Fourth-Generation Allosteric and Reversible EGFR Inhibitor',
        journal: 'Cancer Discovery',
        year: 2022,
        authors: 'Schalm SS, Dinami R, Hur W, et al.',
        abstract: 'BLU-945 is a selective, fourth-generation EGFR tyrosine kinase inhibitor engineered to target triple-mutant EGFR (Exon 19 del/T790M/C797S and L858R/T790M/C797S). Cryo-EM and enzymatic assays demonstrated potent inhibition while sparing wild-type EGFR, demonstrating suppression of intracranial lesions in patient-derived xenograft models.',
        studyType: 'Preclinical / In Vitro',
        sampleSize: 64,
        pValue: 'IC50 < 2.3 nM',
        confidenceScore: 92,
        screeningStatus: 'included',
        citations: 165,
        openAccess: false,
        biasRisk: 'Low',
        meshTerms: ['Fourth-Generation TKI', 'C797S Mutation', 'Cryo-EM Structure'],
        entities: {
          genes: ['EGFR', 'T790M', 'C797S'],
          diseases: ['Refractory Non-Small Cell Lung Cancer'],
          drugs: ['BLU-945', 'Osimertinib'],
          pathways: ['Kinase Catalytic Domain Remodeling']
        },
        triples: [
          { subject: 'BLU-945', predicate: 'SELECTIVELY_INHIBITS', object: 'C797S', confidence: 0.93 },
          { subject: 'BLU-945', predicate: 'SPARES', object: 'Wild-Type EGFR', confidence: 0.91 }
        ]
      },
      {
        id: 'p4',
        pmid: '34145781',
        doi: '10.1038/s41568-021-00366-2',
        title: 'Mechanisms of Acquired Resistance to Third-Generation EGFR TKIs and Emerging Countermeasures',
        journal: 'Nature Reviews Clinical Oncology',
        year: 2021,
        authors: 'Leonetti A, Sharma S, Minari R, Perego P, et al.',
        abstract: 'A comprehensive systematic review detailing on-target EGFR resistance (C797S in cis vs trans, G796R, L718Q) and off-target bypass mechanisms including MET amplification (15-20%), HER2 amplifications (5%), RET/BRAF rearrangements, and histologic transformation to small cell lung cancer (SCLC).',
        studyType: 'Systematic Review',
        sampleSize: 1820,
        confidenceScore: 96,
        screeningStatus: 'included',
        citations: 512,
        openAccess: true,
        biasRisk: 'Low',
        meshTerms: ['Drug Resistance', 'Review', 'Receptor, Epidermal Growth Factor'],
        entities: {
          genes: ['EGFR', 'MET', 'HER2', 'BRAF', 'RET'],
          diseases: ['Adenocarcinoma', 'Small Cell Lung Cancer Transformation'],
          drugs: ['Osimertinib', 'Afatinib', 'Trastuzumab Deruxtecan'],
          pathways: ['MAPK cascade', 'PI3K-Akt signaling', 'Neuroendocrine switch']
        },
        triples: [
          { subject: 'MET', predicate: 'BYPASSES', object: 'EGFR', confidence: 0.97 },
          { subject: 'HER2', predicate: 'BYPASSES', object: 'EGFR', confidence: 0.90 }
        ]
      },
      {
        id: 'p5',
        pmid: '35147890',
        doi: '10.1200/JCO.21.02534',
        title: 'Circulating Tumor DNA Genomic Profiling Identifies Clonal Evolution during Osimertinib Therapy',
        journal: 'Journal of Clinical Oncology',
        year: 2022,
        authors: 'Papadimitrakopoulou VA, Mok TS, Han JY, et al.',
        abstract: 'Liquid biopsy analysis across 385 patients enrolled in AURA3 demonstrated that dynamic ctDNA shedding accurately predicted C797S and MET co-occurrence up to 3.2 months before radiological progression according to RECIST criteria.',
        studyType: 'Prospective Cohort',
        sampleSize: 385,
        hazardRatio: 'Sensitivity = 91.2%',
        pValue: 'p < 0.001',
        confidenceScore: 90,
        screeningStatus: 'flagged',
        citations: 142,
        openAccess: true,
        biasRisk: 'Moderate',
        meshTerms: ['Circulating Tumor DNA', 'Liquid Biopsy', 'Clonal Evolution'],
        entities: {
          genes: ['EGFR', 'T790M', 'C797S', 'TP53'],
          diseases: ['Metastatic NSCLC'],
          drugs: ['Osimertinib'],
          pathways: ['DNA repair', 'Clonal selection']
        },
        triples: [
          { subject: 'ctDNA', predicate: 'BIOMARKER_FOR', object: 'C797S', confidence: 0.92 }
        ]
      }
    ],
    reviewReport: `# 系统性学术文献挖掘与证据合成报告
## 课题：EGFR T790M/C797S 突变靶向耐药机制与双靶协同策略

### 1. 执行摘要 (Executive Summary)
第三代表皮生长因子受体酪氨酸激酶抑制剂（EGFR-TKI）**奥希替尼 (Osimertinib)** 凭借在 **FLAURA** 研究中确立的卓越生存获益，已成为敏感突变（19del / L858R）晚期非小细胞肺癌（NSCLC）一线标准疗法。然而，患者在接受中位 18.9 个月治疗后几乎均不可避免地出现疾病进展。
PubMiner-Agent 智能文献挖掘系统通过对 PubMed、PMC 全文库及 SemMedDB 知识库的系统性检索、NER 实体抽取与共现图谱分析，归纳出奥希替尼获得性耐药的两大核心路径：**靶内耐药（On-target resistance, 约占 15-25%）** 与 **旁路激活耐药（Off-target bypass signaling, 约占 40-50%）**。

### 2. 分子靶点与突变全景 (Target Mutation Landscape)
- **C797S 顺反式突变 (cis vs. trans)**：奥希替尼通过与 EGFR ATP 结合口袋内的 Cys797 残基形成不可逆共价键发挥抑制效能。当发生 C797S 错义突变后，共价交联丢失，药物结合自由能显著降低。若 C797S 与 T790M 呈 **反式存在 (trans)**，一代联合三代 TKI 可恢复部分敏感性；若呈 **顺式存在 (cis)**，目前三代抑制剂全部耐药，亟需四代变构抑制剂（如 **BLU-945**、**BBT-176**）。
- **MET 基因局部扩增与过表达**：发生率约为 15%-22%，为最常见的旁路激活机制。扩增的 MET 激酶独立磷酸化 ERBB3（HER3），进而强烈偶联并激活下游 **PI3K-Akt-mTOR** 促存活信号轴。

### 3. 循证临床试验与联合干预策略 (Clinical Evidence & Combination Regimens)
| 试验方案 | 靶点机制 | 样本规模 ($N$) | 客观缓解率 (ORR) | 中位 PFS (mo) | 证据等级 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **MARIPOSA (Amivantamab + Lazertinib)** | EGFR/MET 双抗 + 三代TKI | 1074 | 86% | 23.7 (HR=0.70) | Level 1 (Phase III) |
| **SAVANNAH (Savolitinib + Osimertinib)** | 选择性MET抑制 + EGFR抑制 | 293 | 49% | 7.1 | Level 2 (Phase II) |
| **CHRYSALIS-2 (Amivantamab + Lazertinib + Chemo)** | 多重靶向联合免疫介导杀伤 | 280 | 41% | 6.8 | Level 2 (Phase II) |
| **BLU-945 Monotherapy** | 四代变构可逆选择性抑制 | 64 | 28% (Phase 1) | 待更新 | Level 3 (Phase I) |

### 4. 机制协同与双靶组合的生物学基础
双特异性抗体 **Amivantamab** 具备独特的双重机制：既能够特异性结合肿瘤细胞表面过度表达的 EGFR 与 MET 受体诱导其内吞降解，阻断二聚体形成；又可通过其工程化 Fc 段招募巨噬细胞与 NK 细胞，触发强大的抗体依赖性细胞毒性作用（ADCC），从而在消除突变克隆的同时克服异质性旁路耐药。

### 5. 待解决科学问题与未来方向
1. **液体活检（ctDNA/cfDNA）超灵敏动态监测**：如何在影像学进展前 3-6 个月捕获低频克隆突变演化并实施抢先式靶向轮换？
2. **抗体偶联药物（ADC，如 HER3-DXd、Dato-DXd）联合应用空间**：在多重通路复合耐药背景下的挽救性获益评估。
`
  },
  {
    id: 'glp1-neuro',
    title: 'GLP-1 受体激动剂在中枢神经退行性疾病中的神经保护机制',
    englishTitle: 'GLP-1 Receptor Agonists & Neuroprotection Mechanisms in Neurodegenerative Disorders',
    subtitle: '司美格鲁肽/利拉鲁肽通过 AMPK-mTOR 轴抑制小胶质细胞神经炎症与 Tau 蛋白异常磷酸化',
    query: '("GLP-1 receptor agonist" OR Semaglutide OR Liraglutide) AND ("Alzheimer disease" OR "Parkinson disease") AND (Neuroinflammation OR "Microglial activation" OR Autophagy)',
    meshTerms: [
      'Glucagon-Like Peptide-1 Receptor/agonists',
      'Neurodegenerative Diseases/drug therapy',
      'Neuroinflammatory Diseases/prevention & control',
      'Microglia/metabolism',
      'AMP-Activated Protein Kinases/metabolism'
    ],
    trendYears: ['2019', '2020', '2021', '2022', '2023', '2024', '2025', '2026'],
    pubCounts: [280, 395, 520, 680, 910, 1150, 1380, 1590],
    citationAverages: [22.1, 29.8, 38.4, 46.2, 55.7, 63.9, 71.5, 78.2],
    cooccurrenceMatrix: {
      xLabels: ['Semaglutide', 'Liraglutide', 'Tirzepatide', 'Exenatide', 'Dulaglutide'],
      yLabels: ['GLP1R', 'AMPK-Axis', 'Microglia-M1', 'Tau-pS396', 'Alpha-Synuclein', 'NLRP3-Inflammasome'],
      data: [
        [0, 0, 98], [0, 1, 91], [0, 2, 85], [0, 3, 79], [0, 4, 72], [0, 5, 88],
        [1, 0, 89], [1, 1, 84], [1, 2, 78], [1, 3, 73], [1, 4, 66], [1, 5, 74],
        [2, 0, 92], [2, 1, 88], [2, 2, 74], [2, 3, 68], [2, 4, 61], [2, 5, 80],
        [3, 0, 77], [3, 1, 71], [3, 2, 69], [3, 3, 64], [3, 4, 75], [3, 5, 62],
        [4, 0, 65], [4, 1, 59], [4, 2, 52], [4, 3, 48], [4, 4, 43], [4, 5, 51]
      ]
    },
    evidenceDistribution: [
      { name: 'Phase III RCTs (EVOKE / EVOKE Plus)', value: 18 },
      { name: 'Phase II Clinical Trials', value: 52 },
      { name: 'Neuroimaging & Biomarker Cohorts', value: 110 },
      { name: 'Preclinical Cellular / Animal Models', value: 430 },
      { name: 'Meta-Analyses & Reviews', value: 65 }
    ],
    biomarkerRanking: [
      { name: '小胶质细胞 NLRP3 炎症小体抑制率', score: 94.2, articles: 388 },
      { name: '脑脊液 p-tau181 / p-tau217 水平', score: 89.6, articles: 342 },
      { name: '神经丝轻链蛋白 (NfL) 血浆清除率', score: 84.1, articles: 290 },
      { name: '海马突触素 (Synaptophysin) 表达密度', score: 78.5, articles: 215 },
      { name: 'Alpha-突触核蛋白寡聚体蓄积抑制', score: 71.3, articles: 182 }
    ],
    graphNodes: [
      { id: 'GLP1R', name: 'GLP-1R (受体)', category: 0, symbolSize: 52, value: 96, details: '广泛分布于下丘脑、海马和皮质神经元以及星形胶质细胞的G蛋白偶联受体。' },
      { id: 'AMPK', name: 'AMPK 激酶', category: 0, symbolSize: 45, value: 89, details: '细胞能量代谢中枢调控者，激活后抑制mTOR并诱导自噬流。' },
      { id: 'Tau', name: 'Tau 蛋白 (MAPT)', category: 0, symbolSize: 42, value: 85, details: '微管相关蛋白，过度磷酸化后形成神经原纤维缠结，驱动阿尔茨海默病。' },
      { id: 'NLRP3', name: 'NLRP3 炎症小体', category: 0, symbolSize: 40, value: 83, details: '介导 Caspase-1 激活及 IL-1b 释放的核心促炎复合物。' },
      { id: 'AD', name: '阿尔茨海默病 (AD)', category: 1, symbolSize: 55, value: 98, details: '进行性神经退行性疾病，伴随认知功能进行性衰退与海马萎缩。' },
      { id: 'PD', name: '帕金森病 (PD)', category: 1, symbolSize: 46, value: 88, details: '黑质多巴胺能神经元进行性丢失与运动障碍。' },
      { id: 'Neuroinflammation', name: '中枢神经炎症', category: 1, symbolSize: 48, value: 92, details: '小胶质细胞过度极化（M1型）释放炎性介质诱发的二次神经元损伤。' },
      { id: 'Autophagy', name: '神经自噬清理通路', category: 3, symbolSize: 42, value: 86, details: '清除错误折叠蛋白（Abeta 与 p-Tau）的自噬溶酶体降解系统。' },
      { id: 'Semaglutide', name: '司美格鲁肽 (Semaglutide)', category: 2, symbolSize: 54, value: 98, details: '长效 GLP-1 类似物，具有高受体亲和力与中枢神经抗炎活性。' },
      { id: 'Tirzepatide', name: '替尔泊肽 (Tirzepatide)', category: 2, symbolSize: 46, value: 91, details: 'GIP/GLP-1 双受体双重激动剂，协同增强线粒体能量代谢。' },
      { id: 'Liraglutide', name: '利拉鲁肽 (Liraglutide)', category: 2, symbolSize: 44, value: 84, details: '每日一次人源化 GLP-1R 激动剂，证实可减少皮质糖代谢衰退。' }
    ],
    graphLinks: [
      { source: 'Semaglutide', target: 'GLP1R', relation: 'AGONIST_OF', weight: 9.9, evidenceCount: 460 },
      { source: 'GLP1R', target: 'AMPK', relation: 'PHOSPHORYLATES_ACTIVATES', weight: 9.3, evidenceCount: 380 },
      { source: 'AMPK', target: 'Autophagy', relation: 'PROMOTES', weight: 9.1, evidenceCount: 310 },
      { source: 'Autophagy', target: 'Tau', relation: 'CLEARS_DEGRADES', weight: 8.8, evidenceCount: 260 },
      { source: 'GLP1R', target: 'NLRP3', relation: 'INHIBITS', weight: 9.4, evidenceCount: 340 },
      { source: 'NLRP3', target: 'Neuroinflammation', relation: 'DRIVES', weight: 9.5, evidenceCount: 410 },
      { source: 'Neuroinflammation', target: 'AD', relation: 'EXACERBATES', weight: 9.6, evidenceCount: 520 },
      { source: 'Neuroinflammation', target: 'PD', relation: 'EXACERBATES', weight: 9.0, evidenceCount: 390 },
      { source: 'Tirzepatide', target: 'GLP1R', relation: 'POTENT_AGONIST', weight: 9.2, evidenceCount: 210 },
      { source: 'Liraglutide', target: 'AD', relation: 'ATTENUATES_DECLINE', weight: 8.7, evidenceCount: 280 }
    ],
    papers: [
      {
        id: 'p101',
        pmid: '37123991',
        doi: '10.1038/s41591-023-02341-2',
        title: 'Oral Semaglutide in Early Alzheimer Disease: Biological Basis and Clinical Rationale for the EVOKE Trials',
        journal: 'Nature Medicine',
        year: 2023,
        authors: 'Cummings J, Scheltens P, Feldman HH, et al.',
        abstract: 'Preclinical studies consistently establish that GLP-1 receptor activation preserves synaptic transmission, decreases microglial neuroinflammation, and lowers phosphorylated Tau. This article outlines the design, biomarker endpoints, and molecular basis of ongoing EVOKE and EVOKE Plus Phase 3 clinical trials evaluating daily oral semaglutide in 3,600 patients with early AD.',
        studyType: 'Clinical Trial Phase III',
        sampleSize: 3600,
        hazardRatio: 'Endpoint: CDR-SB & ADAS-Cog13',
        pValue: 'Ongoing Study Protocol',
        confidenceScore: 97,
        screeningStatus: 'included',
        citations: 215,
        openAccess: true,
        biasRisk: 'Low',
        meshTerms: ['Semaglutide', 'Alzheimer Disease', 'Clinical Trial Protocol'],
        entities: {
          genes: ['GLP1R', 'MAPT', 'APP'],
          diseases: ['Mild Cognitive Impairment', 'Early Alzheimer Disease'],
          drugs: ['Semaglutide'],
          pathways: ['Neurovascular Coupling', 'Synaptic Plasticity']
        },
        triples: [
          { subject: 'Semaglutide', predicate: 'ACTIVATES', object: 'GLP1R', confidence: 0.99 },
          { subject: 'Semaglutide', predicate: 'ATTENUATES', object: 'Early Alzheimer Disease', confidence: 0.95 }
        ]
      },
      {
        id: 'p102',
        pmid: '35489110',
        doi: '10.1016/j.cell.2022.03.042',
        title: 'Microglial GLP-1R signaling suppresses NLRP3 inflammasome activation via the AMPK/SIRT1 axis',
        journal: 'Cell',
        year: 2022,
        authors: 'Zhang Y, Wang H, Lin Q, et al.',
        abstract: 'Here we show that microglial-specific ablation of Glp1r aggravates cognitive impairment and promotes Abeta plaque accumulation in APP/PS1 mice. Mechanistically, agonist binding triggers cAMP-PKA and AMPK phosphorylation, promoting SIRT1 deacetylation of NLRP3 and impeding ASC speck assembly.',
        studyType: 'Preclinical / In Vitro',
        sampleSize: 96,
        pValue: 'p < 0.0001',
        confidenceScore: 95,
        screeningStatus: 'included',
        citations: 340,
        openAccess: false,
        biasRisk: 'Low',
        meshTerms: ['Microglia', 'NLRP3 Inflammasome', 'Autophagy Flux'],
        entities: {
          genes: ['GLP1R', 'AMPK', 'SIRT1', 'NLRP3'],
          diseases: ['Neuroinflammation', 'Synaptotoxicity'],
          drugs: ['Exenatide', 'Semaglutide'],
          pathways: ['cAMP-PKA cascade', 'AMPK-SIRT1 deacetylation']
        },
        triples: [
          { subject: 'GLP1R', predicate: 'SUPPRESSES', object: 'NLRP3 Inflammasome', confidence: 0.97 },
          { subject: 'AMPK', predicate: 'ACTIVATES', object: 'SIRT1', confidence: 0.94 }
        ]
      }
    ],
    reviewReport: `# 系统性文献挖掘与机制合成报告
## 课题：GLP-1 受体激动剂在中枢神经退行性疾病中的神经保护机制

### 1. 科学背景与转化前景
随着全球人口老龄化加剧，阿尔茨海默病（AD）与帕金森病（PD）的发病率呈爆发性增长。传统单一针对淀粉样蛋白 $\beta$（Abeta）的单抗疗法在临床中面临疗效有限与淀粉样蛋白相关影像异常（ARIA）水肿风险。
流行病学与实效证据（Real-World Evidence）表明，接受 GLP-1 受体激动剂治疗的 2 型糖尿病患者，罹患痴呆与认知衰退的风险降低了 34%-53%。

### 2. 神经保护的三大多维分子机制
1. **重塑小胶质细胞极化并阻断 NLRP3 炎症小体**：
   - 药物透过血脑屏障结合小胶质细胞表面 GLP-1R，通过激活 cAMP-PKA 信号级联，促进 AMPK 磷酸化，抑制 NF-$\kappa$B 核易位，从而显著减少 IL-1$\beta$、TNF-$\alpha$ 等细胞毒性因子的释放。
2. **激活 AMPK-mTOR 自噬溶酶体通路促进毒性蛋白清除**：
   - 上调 Beclin-1 与 LC3-II/LC3-I 比值，增强神经元对过度磷酸化的 Tau 蛋白（p-Tau217/p-Tau181）与 $\alpha$-突触核蛋白聚集体的泛素化清除。
3. **修复脑微血管内皮屏障与线粒体稳态**：
   - 促进脑源性神经营养因子（BDNF）分泌，逆转脑内胰岛素抵抗，维持海马突触树突棘密度与长时程增强（LTP）。
`
  },
  {
    id: 'cart-exhaustion',
    title: 'CAR-T 细胞免疫耗竭调控机制与新型免疫检查点靶向策略',
    englishTitle: 'Epigenetic & Transcriptional Regulators of CAR-T Cell Exhaustion and Novel Checkpoint Targets',
    subtitle: 'TOX/NR4A 转录因子网络、表观遗传重塑及阻断 LAG-3/TIM-3 维持持久抗肿瘤应答',
    query: '("CAR-T cell" OR "Chimeric Antigen Receptor") AND (Exhaustion OR "T-cell dysfunction") AND (TOX OR NR4A OR LAG3 OR "Epigenetic remodeling")',
    meshTerms: [
      'Receptors, Chimeric Antigen/immunology',
      'T-Lymphocytes/immunology',
      'DNA-Binding Proteins/metabolism',
      'Immune Checkpoint Proteins/antagonists & inhibitors',
      'Epigenomics'
    ],
    trendYears: ['2019', '2020', '2021', '2022', '2023', '2024', '2025', '2026'],
    pubCounts: [310, 445, 610, 830, 1090, 1340, 1620, 1890],
    citationAverages: [26.5, 33.4, 44.1, 53.8, 64.2, 73.1, 82.6, 90.4],
    cooccurrenceMatrix: {
      xLabels: ['Tisagenlecleucel', 'Axi-cel', 'Relatlimab', 'Pembrolizumab', 'CRISPR-TOX-KO'],
      yLabels: ['TOX-Factor', 'NR4A-Family', 'LAG-3', 'TIM-3', 'PD-1', 'TCF-1-Stemness'],
      data: [
        [0, 0, 78], [0, 1, 74], [0, 2, 82], [0, 3, 76], [0, 4, 88], [0, 5, 80],
        [1, 0, 84], [1, 1, 81], [1, 2, 86], [1, 3, 80], [1, 4, 91], [1, 5, 75],
        [2, 0, 42], [2, 1, 39], [2, 2, 98], [2, 3, 62], [2, 4, 71], [2, 5, 68],
        [3, 0, 51], [3, 1, 48], [3, 2, 65], [3, 3, 58], [3, 4, 96], [3, 5, 62],
        [4, 0, 96], [4, 1, 93], [4, 2, 79], [4, 3, 74], [4, 4, 82], [4, 5, 95]
      ]
    },
    evidenceDistribution: [
      { name: 'Phase II/III Registration Trials', value: 26 },
      { name: 'Phase I Exploratory Trials', value: 68 },
      { name: 'Single-Cell Multi-Omics Studies', value: 165 },
      { name: 'Preclinical Genetic Engineering Models', value: 380 },
      { name: 'Systematic Reviews', value: 42 }
    ],
    biomarkerRanking: [
      { name: 'TOX 染色质开放区结合峰 (ATAC-seq)', score: 98.1, articles: 412 },
      { name: 'TCF-1+ 干性记忆 T 细胞亚群比例', score: 93.4, articles: 365 },
      { name: 'LAG-3 / TIM-3 双阳性耗竭共表达', score: 87.2, articles: 310 },
      { name: 'c-Jun 过表达与 AP-1 复合物失衡', score: 81.6, articles: 245 },
      { name: 'NR4A 家族基因三敲除 (TKO) 表型', score: 76.9, articles: 198 }
    ],
    graphNodes: [
      { id: 'CART', name: 'CAR-T 细胞', category: 0, symbolSize: 56, value: 99, details: '嵌合抗原受体 T 细胞，基因工程重塑的过继性细胞免疫治疗先锋。' },
      { id: 'TOX', name: 'TOX 转录因子', category: 0, symbolSize: 48, value: 94, details: '高迁移率族蛋白，特异性维系 T 细胞不可逆耗竭表观遗传程序的分子开关。' },
      { id: 'NR4A', name: 'NR4A 家族 (NR4A1/2/3)', category: 0, symbolSize: 44, value: 90, details: '核受体转录因子家族，在持续强抗原刺激下协同诱导细胞功能衰竭。' },
      { id: 'TCF1', name: 'TCF-1 (干性转录因子)', category: 0, symbolSize: 42, value: 88, details: '维系前体耗竭细胞（Tpex）自我更新与持久增殖潜能的关键标志。' },
      { id: 'Lymphoma', name: '弥漫大 B 细胞淋巴瘤 (DLBCL)', category: 1, symbolSize: 52, value: 95, details: '侵袭性血液肿瘤，二线及以上 CAR-T 治疗的关键适应症。' },
      { id: 'SolidTumor', name: '实体瘤微环境 (TME)', category: 1, symbolSize: 46, value: 89, details: '存在强免疫抑制屏障（TGF-b、缺氧、酸中毒），加速 T 细胞终末耗竭。' },
      { id: 'Exhaustion', name: '免疫耗竭 (T Cell Exhaustion)', category: 1, symbolSize: 50, value: 96, details: '效应细胞因子分泌缺陷、增殖停滞、共抑制受体持续共表达的病理状态。' },
      { id: 'LAG3', name: 'LAG-3 免疫检查点', category: 2, symbolSize: 40, value: 82, details: '淋巴细胞活化基因-3，高亲和力结合 MHC-II 抑制 TCR 激活信号。' },
      { id: 'TIM3', name: 'TIM-3 检查点', category: 2, symbolSize: 38, value: 78, details: '结合半乳糖凝集素-9 (Galectin-9)，诱导效应 T 细胞凋亡。' },
      { id: 'Relatlimab', name: '瑞拉利单抗 (Relatlimab)', category: 2, symbolSize: 42, value: 84, details: '全人源 IgG4 LAG-3 单抗，临床打破耐受与耗竭状态。' },
      { id: 'CRISPR_KO', name: 'CRISPR 基因敲除编辑', category: 3, symbolSize: 45, value: 91, details: '体外敲除 TOX/NR4A 或 PD-1 等负向调控分子，赋予细胞长效杀伤潜能。' }
    ],
    graphLinks: [
      { source: 'CART', target: 'Lymphoma', relation: 'KILLS_TARGETS', weight: 9.8, evidenceCount: 520 },
      { source: 'CART', target: 'Exhaustion', relation: 'SUCCUMBS_TO', weight: 9.5, evidenceCount: 460 },
      { source: 'TOX', target: 'Exhaustion', relation: 'EPIGENETICALLY_DRIVES', weight: 9.9, evidenceCount: 480 },
      { source: 'NR4A', target: 'Exhaustion', relation: 'COOPERATES_WITH_TOX', weight: 9.4, evidenceCount: 390 },
      { source: 'TCF1', target: 'CART', relation: 'PRESERVES_STEMNESS', weight: 9.3, evidenceCount: 340 },
      { source: 'CRISPR_KO', target: 'TOX', relation: 'KNOCKS_OUT', weight: 9.7, evidenceCount: 290 },
      { source: 'CRISPR_KO', target: 'CART', relation: 'ENHANCES_PERSISTENCE', weight: 9.6, evidenceCount: 310 },
      { source: 'LAG3', target: 'Exhaustion', relation: 'BIOMARKER_OF', weight: 8.9, evidenceCount: 270 },
      { source: 'Relatlimab', target: 'LAG3', relation: 'BLOCKS', weight: 9.2, evidenceCount: 230 },
      { source: 'SolidTumor', target: 'Exhaustion', relation: 'ACCELERATES', weight: 9.1, evidenceCount: 380 }
    ],
    papers: [
      {
        id: 'p201',
        pmid: '36881920',
        doi: '10.1038/s41587-023-01712-4',
        title: 'Single-cell Epigenetic Profiling Reveals TOX and NR4A Drive Irreversible CAR-T Dysfunction in Solid Tumors',
        journal: 'Nature Biotechnology',
        year: 2023,
        authors: 'Good CR, Patel RP, Lynn RC, et al.',
        abstract: 'Using paired single-cell RNA-seq and ATAC-seq on tumor-infiltrating CAR-T cells, we mapped the transition from functional effector state to terminally exhausted T cells. Genetic deletion of both TOX and NR4A using base editing unlocked an epigenetic state with increased accessibility at memory-associated enhancers.',
        studyType: 'Preclinical / In Vitro',
        sampleSize: 120,
        pValue: 'FDR < 0.001',
        confidenceScore: 96,
        screeningStatus: 'included',
        citations: 288,
        openAccess: true,
        biasRisk: 'Low',
        meshTerms: ['Base Editing', 'Chromatin Accessibility', 'Adoptive Cell Therapy'],
        entities: {
          genes: ['TOX', 'NR4A1', 'NR4A2', 'TCF7'],
          diseases: ['Glioblastoma', 'Pancreatic Cancer'],
          drugs: ['CAR-T Cell Therapy'],
          pathways: ['TCR signaling exhaustion', 'Epigenetic memory reprogramming']
        },
        triples: [
          { subject: 'TOX', predicate: 'DRIVES', object: 'T-cell Dysfunction', confidence: 0.98 },
          { subject: 'Base Editing', predicate: 'REVERSES', object: 'Epigenetic Exhaustion', confidence: 0.95 }
        ]
      }
    ],
    reviewReport: `# 系统性文献挖掘与机制合成报告
## 课题：CAR-T 细胞免疫耗竭调控机制与新型免疫检查点靶向策略

### 1. 临床困境与表观遗传屏障
嵌合抗原受体 T 细胞（CAR-T）在血液肿瘤中取得革命性突破，但超过 50% 的患者在 1-2 年内因细胞体内扩增停滞与快速耗竭而复发。尤其在实体瘤微环境中，持续高负荷的抗原刺激驱动 T 细胞快速进入终末耗竭态（Terminally Exhausted, Tex）。

### 2. 关键转录调控因子网络
- **TOX 与表观遗传烙印**：TOX 持续高表达导致染色质开放图谱发生永久性重构，沉默促效应细胞因子（IFN-$\gamma$、TNF-$\alpha$）增强子，并固化 PD-1、LAG-3、TIM-3 的转录活化。
- **前体耗竭亚群（Tpex）的干性维持**：**TCF-1+** 亚群展现出强大的自我更新能力，是决定过继细胞能否长期存续的决定性标志物。

### 3. 下一代工程化策略
1. **CRISPR 多重基因敲除**：敲除 TOX、NR4A 家族基因阻断耗竭信号传导；
2. **共表达 c-Jun**：恢复 AP-1/NFAT 平衡，克服功能衰竭；
3. **双靶向检查点单抗联合**：阻断 LAG-3（如 **Relatlimab**）可显著激活 CAR-T 细胞对微环境抑制信号的抵抗力。
`
  }
];

// Helper to generate dynamic topic data for custom queries
export function createCustomTopic(query: string): ResearchTopic {
  const cleanTerm = query.trim() || 'Custom Biomedical Query';
  return {
    id: 'custom-' + Date.now(),
    title: `自定义课题: ${cleanTerm}`,
    englishTitle: `Literature Mining & Entity Discovery for: ${cleanTerm}`,
    subtitle: `PubMiner-Agent 自动化实时多源检索、生物医学实体关系抽取与证据合成`,
    query: query,
    meshTerms: [
      `${cleanTerm}/therapeutic use`,
      `${cleanTerm}/pharmacology`,
      'Biological Biomarkers',
      'Clinical Trials as Topic'
    ],
    trendYears: ['2020', '2021', '2022', '2023', '2024', '2025', '2026'],
    pubCounts: [320, 480, 670, 890, 1140, 1420, 1710],
    citationAverages: [18.5, 25.2, 34.0, 42.8, 51.5, 60.2, 69.8],
    cooccurrenceMatrix: {
      xLabels: [`Compound A`, `Inhibitor B`, `Antibody C`, `Agonist D`],
      yLabels: [`Target ${cleanTerm}`, `Pathway X`, `Receptor Y`, `Biomarker Z`],
      data: [
        [0, 0, 88], [0, 1, 74], [0, 2, 62], [0, 3, 51],
        [1, 0, 79], [1, 1, 85], [1, 2, 67], [1, 3, 58],
        [2, 0, 65], [2, 1, 71], [2, 2, 89], [2, 3, 63],
        [3, 0, 52], [3, 1, 60], [3, 2, 73], [3, 3, 84]
      ]
    },
    evidenceDistribution: [
      { name: 'Phase III Trials', value: 24 },
      { name: 'Phase II Trials', value: 65 },
      { name: 'Prospective Cohorts', value: 120 },
      { name: 'In Vitro & Preclinical', value: 280 },
      { name: 'Meta-Analyses', value: 38 }
    ],
    biomarkerRanking: [
      { name: `${cleanTerm} 基因突变变异`, score: 94.5, articles: 382 },
      { name: `下游磷酸化信号通路激活`, score: 88.2, articles: 295 },
      { name: `微环境免疫浸润评分`, score: 79.4, articles: 210 },
      { name: `血浆游离 ctDNA 阳性率`, score: 72.1, articles: 165 }
    ],
    graphNodes: [
      { id: 'CoreTarget', name: `${cleanTerm} (核心靶点)`, category: 0, symbolSize: 54, value: 95, details: `检索词识别的核心生物标志物/基因。` },
      { id: 'DiseaseIndication', name: `${cleanTerm} 相关适应症`, category: 1, symbolSize: 50, value: 90, details: `主要临床疾病表型与病理组织学表现。` },
      { id: 'LeadCandidate', name: `候选分子 / 抑制剂`, category: 2, symbolSize: 48, value: 88, details: `靶向 ${cleanTerm} 的前沿化合物或生物制剂。` },
      { id: 'DownstreamPathway', name: `下游信号传导轴`, category: 3, symbolSize: 44, value: 85, details: `介导细胞存活、增殖及耐药的分子通路。` },
      { id: 'BiomarkerMarker', name: `伴随诊断标志物`, category: 0, symbolSize: 38, value: 76, details: `用于患者分层与疗效监测的分子指标。` },
      { id: 'SecondaryResist', name: `旁路代偿机制`, category: 3, symbolSize: 36, value: 72, details: `长期治疗后诱导的继发性耐药通路。` }
    ],
    graphLinks: [
      { source: 'LeadCandidate', target: 'CoreTarget', relation: 'INHIBITS', weight: 9.6, evidenceCount: 310 },
      { source: 'CoreTarget', target: 'DownstreamPathway', relation: 'ACTIVATES', weight: 9.2, evidenceCount: 260 },
      { source: 'DownstreamPathway', target: 'DiseaseIndication', relation: 'DRIVES', weight: 9.0, evidenceCount: 280 },
      { source: 'BiomarkerMarker', target: 'DiseaseIndication', relation: 'PREDICTS_OUTCOME', weight: 8.5, evidenceCount: 195 },
      { source: 'SecondaryResist', target: 'DownstreamPathway', relation: 'BYPASSES', weight: 8.1, evidenceCount: 140 }
    ],
    papers: [
      {
        id: `cp-1`,
        pmid: '38192004',
        doi: '10.1016/j.cell.2024.01.012',
        title: `Comprehensive Molecular Characterization and Therapeutic Targeting of ${cleanTerm}`,
        journal: 'Cell Discovery & Translational Medicine',
        year: 2024,
        authors: 'Chen J, Miller T, Schmidt K, et al.',
        abstract: `This study demonstrates that targeting ${cleanTerm} produces robust biological response and halts tumor progression in preclinical translational models. Quantitative multi-omics profiling identifies critical dependencies along the pathway and validates biomarker stratification.`,
        studyType: 'Clinical Trial Phase I/II',
        sampleSize: 180,
        hazardRatio: 'HR = 0.68 (95% CI 0.52-0.89)',
        pValue: 'p = 0.003',
        confidenceScore: 94,
        screeningStatus: 'included',
        citations: 86,
        openAccess: true,
        biasRisk: 'Low',
        meshTerms: [cleanTerm, 'Targeted Therapy', 'Biomarkers'],
        entities: {
          genes: [cleanTerm, 'AKT1', 'MAPK1'],
          diseases: [`${cleanTerm} 相关疾病`],
          drugs: ['Novel Inhibitor A'],
          pathways: ['Signal Transduction', 'Cellular Apoptosis']
        },
        triples: [
          { subject: 'Novel Inhibitor A', predicate: 'INHIBITS', object: cleanTerm, confidence: 0.95 },
          { subject: cleanTerm, predicate: 'DRIVES', object: 'Pathology', confidence: 0.91 }
        ]
      }
    ],
    reviewReport: `# 系统性文献挖掘与机制合成报告
## 课题：${cleanTerm}

### 1. 执行摘要
PubMiner-Agent 通过自动化文献挖掘引擎针对 **${cleanTerm}** 完成了跨库检索、实体识别与关系网络构建。初步证据表明该靶标在疾病进展、细胞应激适应及临床预后中起到了关键调控作用。

### 2. 核心实体网络与关联
- **靶标与分子机制**：该靶点与下游信号通路存在密切的物理结合与级联激活效应；
- **药物研发前沿**：目前已有多个小分子抑制剂与单克隆抗体进入早期临床前验证阶段；
- **证据评估**：现有文献以早期临床试验与临床前研究为主，需进一步开展大样本多中心随机对照验证。
`
  };
}
