# Literature Sources — Edge AI Fan Fault Detector (compiled 2026-09-23)

Legend: **[V]** fetched and read · **[S]** confirmed via search/index metadata only — open before citing · **[U]** unverified — do not cite as-is.

---

## A. Industrial case for predictive maintenance (PdM)

| # | Source | Supports | Key quote / figure |
|---|---|---|---|
| A1 [V] | Sullivan, Pugh, Melendez, Hunt (2010). *O&M Best Practices Guide, Release 3.0*. PNNL for US DOE FEMP. https://www.energy.gov/sites/default/files/2020/04/f74/omguide_complete_w-eo-disclaimer.pdf | PdM vs preventive vs reactive | Preventive: "12% to 18% cost savings over reactive." Predictive: "8% to 12% over … preventive." Surveys: ROI 10x; maintenance cost −25–30%; breakdowns −70–75%; downtime −35–45%. Also: "Much of the equipment requires cost in excess of $50,000." ⚠ "independent surveys" not named — cite as "FEMP (2010), citing industry surveys." |
| A2 [V] | Deuel, Chandramouli, Coleman, Damodaran (2017). "Making maintenance smarter." Deloitte Insights. https://www.deloitte.com/us/en/insights/industry/manufacturing-industrial-products/industry-4-0/using-predictive-technologies-for-asset-maintenance.html | PdM benefits | "reduce the time required to plan maintenance by 20–50 percent, increase equipment uptime … by 10–20 percent, and reduce overall maintenance costs by 5–10 percent." ⚠ its "$50B/yr downtime" figure is unsourced — avoid. |
| A3 [V] | Siemens/Senseye (2024). *The True Cost of Downtime 2024*. https://assets.new.siemens.com/siemens/assets/api/uuid:1b43afb5-2d07-47f7-9eb7-893fe7d0bc59/TCOD-2024_original.pdf | Cost of downtime | Fortune Global 500 lose "almost $1.4 trillion annually … 11% of their revenues"; SMEs up to "$150,000 an hour". Vendor survey, not peer-reviewed. |
| A4 [V] | Brügge (2023). "Predictive maintenance market: 5 highlights for 2024 and beyond." IoT Analytics. https://iot-analytics.com/predictive-maintenance-market/ | Market size | "$5.5 billion in 2022", 17% CAGR → $14.3B by 2028. (Other firms differ ~2x by definition.) |
| A5 [U] | McKinsey, "Manufacturing: Analytics unleashes productivity and profitability." | Downtime −30–50%, machine life +20–40% | Page would not load — verify before citing. |

## B. Gap: monitoring is costly → only critical assets; wireless low-cost sensors fill the gap

| # | Source | Key quote |
|---|---|---|
| B1 [V] | ABB (2019). "ABB Smart Sensors are helping solve one of industry's biggest problems." https://new.abb.com/news/detail/48761/abb-smart-sensors-are-helping-solve-one-of-industrys-biggest-problems | "Conventional condition monitoring of motors is costly and time consuming … engineers need to manually gather data … for each motor." |
| B2 [V] | SKF Enlight Collect IMx-1 datasheet (CM/WA6100). https://d347awuzx0kdse.cloudfront.net/industrialworld/product-download/cmwa6100_skf.pdf | Data "previously collected manually every month." |
| B3 [V] | Emerson AMS Wireless Vibration Monitor. https://www.emerson.com/en/automation-systems/asset-performance-management/machinery-health-management/ams-wireless-vibration-monitor | "extending coverage to more assets—including … balance-of-plant machines." |
| B4 [V] | Medina-García et al. (2017). "A Wireless Sensor System for Real-Time Monitoring and Fault Detection of Motor Arrays." *Sensors* 17(3):469. doi:10.3390/s17030469 | Wireless overcomes "complexity of installation, the high maintenance costs and the lack of versatility of the traditional wired systems." |
| B5 [V] | Jakobsen et al. (2024). "Low cost MEMS accelerometer and microphone based condition monitoring sensor, with LoRa and BLE." *HardwareX*. doi:10.1016/j.ohx.2024.e00525 | "an efficient CM system often necessitates the use of high-cost accelerometers"; $180 BOM. |

**Commercial products (all cloud/gateway analytics; none advertise on-device learning or FL):** ABB Ability Smart Sensor (cloud), SKF Enlight IMx-1 (on-sensor thresholds + cloud ML), Siemens SIMOTICS CONNECT 400 (cloud, motors for "pumps, fans, or compressors"), Siemens SITRANS MS200 (KPIs on sensor, analysis at gateway), Augury (cloud AI + human experts), Petasense (cloud). Phrase novelty as "not advertised."

## C. Singapore context

| # | Source | Key quote / figure |
|---|---|---|
| C1 [V] | NEA. *ACMV Systems* (SCEM reference manual). https://www.nea.gov.sg/docs/default-source/cmd-documents/energy-efficiency/industrial-sector/scem/acmv.pdf | "ACMV system consumes about 60% of the total energy consumption of a typical commercial building." |
| C2 [V] | NCCS, "Buildings." https://www.nccs.gov.sg/singapores-climate-action/mitigation-efforts/buildings/ | AC "accounting for 40~60% of a building's energy consumption"; periodic energy audits of cooling systems "every 3 years". |
| C3 [V] | BCA media release (30 Jul 2026), 80% energy-efficiency target study. https://www1.bca.gov.sg/resources/newsroom/new-bca-study-confirms-80--energy-efficiency-target-is-within-reach-for-singapore-s-built-environment-sector/ | "cooling accounts for 40 to 60% of building energy consumption". |
| C4 [V] | NEA REACH consultation (2015), MEPS for air-conditioners. https://reach.gov.sg/Participate/Public-Consultation/National-Environment-Agency/Pollution-Control/Raising-Minimum-Energy-Performance-Standards-for-Air-conditioners | AC ≈ "37% of household electricity consumption". (BCA 2018 letter says ~25% — note conflict.) |
| C5 [V] | Environmental Public Health (Cooling Towers and Water Fountains) Regulations (Rg 7). https://www.nea.gov.sg/docs/default-source/our-services/environmental-public-health-(cooling-towers-and-water-fountains)-regulations-(180-kb).pdf | Cleaned/disinfected "at least once every 6 months"; inspected "at least once a week"; records mandatory; fines up to $5k/$10k. (2017 print — check amendments.) |
| C6 [V] | SS 553:2016+A1:2017 ACMV code of practice (preview). Enterprise Singapore eShop. | Scope includes "maintainability"; Section 5 "Operation and maintenance", cl. 20 "Maintenance", cl. 21 "Energy audit". [U] a 2026 edition may exist. |
| C7 [V] | SS 554:2026 Indoor air quality code (preview). | Annex H "Maintenance of ACMV systems"; new informative annex on **low-cost sensors**. |
| C8 [V] | BCA, Periodic Energy Audit (PEA). https://www1.bca.gov.sg/sustainability/legislation-on-environmental-sustainability-for-buildings/existing-buildings/periodic-energy-audit-pea/ | Mandatory cooling-system audits at ≥3-year intervals. |
| C9 [V] | BCA/FMIC Smart FM Taskforce (2026). *Guide to Smart FM* v2.2. https://isomer-user-content.by.gov.sg/338/033e3b4f-13d8-463d-b6df-25176d687d72/Guide%20to%20Smart%20FM%20v2.2%20(31%20July%202026).pdf | Shift FM "using smart solutions, predictive maintenance, and data analytics"; FDD definition (§4.3.2); "processing and consolidation at the edge before the data is being sent"; condition-based maintenance (§4.3.3). **Strongest local justification.** |
| C10 [V] | MCI PQ reply (27 Jul 2021). https://www.mddi.gov.sg/newsroom/mci-response-pq-data-carbon-emissions-data-centres-sg/ | Data centres ≈ 7% (3.40 TWh) of SG electricity in 2020. |
| C11 [V] | IMDA (2024). *Green Data Centre Roadmap*. https://www.imda.gov.sg/-/media/imda/files/how-we-can-help/green-dc-roadmap/green-dc-roadmap.pdf | PUE 1.3 target; cooling towers "up to 97% of a DC's water usage"; predictive analytics for chiller/CRAC. |
| C12 [V] | LTA, "Road Tunnel Operations & Safety." https://www.lta.gov.sg/content/ltagov/en/getting_around/driving_in_singapore/road_tunnel_operations_safety.html | Tunnel ventilation fans and jet fans. |

## D. Fan fault mechanisms, signatures, standards

| # | Source | Key quote / figure |
|---|---|---|
| D1 [V] | US DOE & AMCA (2003). *Improving Fan System Performance: A Sourcebook for Industry*. DOE/GO-102003-1294. https://docs.nlr.gov/docs/fy03osti/29166.pdf | Vibration analysis detects "bearing problem, motor winding problem, or dynamic imbalance"; "Contaminant build-up on fan blades can cause severe performance degradation and fan imbalance"; erosion/corrosion → imbalance; "Belt drives are frequently the most maintenance-intensive component." |
| D2 [V] | Zhang, Zhang, Wang, Habetler (2020). "Deep Learning Algorithms for Bearing Fault Diagnostics – A Comprehensive Review." arXiv:1901.08247 | Bearing faults "responsible for 30% to 40% of all the machine failures" (citing IEEE-IAS motor reliability surveys, IEEE Trans. Ind. Appl. IA-21, 1985, and JEMA). ⚠ The popular "IEEE 44% / EPRI 41% bearings" split could not be traced — avoid. |
| D3 [V] | IRD Mechanalysis, "Induced Draft (ID) Fan Vibration Monitoring." https://www.irdmech.com/induced-draft-id-fan | Buildup/erosion → "progressive increase in vibrations due to unbalance." |
| D4 [V] | Plant Engineering (2001). "Understanding fan vibration and imbalance." https://www.plantengineering.com/articles/understanding-fan-vibration-and-imbalance/ | Sticky particulate adheres to impeller; "setscrews may loosen due to fretting or corrosion." |
| D5 [V] | Fluke/Pruftechnik, "Demystifying Vibration Monitoring Part 4." https://www.fluke.com/en-us/learn/blog/alignment/understanding-vibration-monitoring-common-faults-part-4 | Imbalance → 1X radial; misalignment → 1X axial + 2X; looseness → 1X harmonics; bearings → non-synchronous peaks. |
| D6 [S] | Randall & Antoni (2011). "Rolling element bearing diagnostics—A tutorial." *MSSP* 25:485–520. doi:10.1016/j.ymssp.2010.07.017 | Standard bearing-diagnostics reference (BPFO/BPFI). |
| D7 [V] | ISO 14694:2003+Amd1:2010, *Industrial fans — balance quality and vibration levels* (scope sample). | ⚠ Excludes fans "designed solely for air circulation, e.g. ceiling fans and table fans" — cite as industrial benchmark, not rig compliance. |
| D8 [V] | ANSI/AMCA 204-20, *Balance Quality and Vibration Levels for Fans*. https://www.amca.org/assets/resources/public/Standards%20for%20Member%20Download/amca-204-20.pdf | Covers HVAC, industrial, tunnel, power-gen fans; categories BV-1 (residential ≤0.15 kW) to BV-3. |
| D9 [V] | ISO 20816-1:2016, machine vibration evaluation — general guidelines (scope sample). | Evaluation by vibration magnitude **and change of vibration** — supports change-detection approach. |
| D10 [V] | US DOE AMO (2012). Motor Systems Tip Sheet #5, "Replace V-Belts…". https://www.energy.gov/sites/prod/files/2014/04/f15/replace_vbelts_motor_systemts5.pdf | "Approximately one-third of the electric motors in the industrial and commercial sectors use belt drives." |
| D11 [V] | NREL (2018). "Tune-Up Your Fan Systems for Improved Performance." NREL/FS-5500-70566. https://docs.nlr.gov/docs/fy18osti/70566.pdf | Belt tension, sheave misalignment, loose set screws as fan maintenance issues. |
| D12 [S] | Aung, Kok, Koh, Teo (2024). "An Embedded Machine Learning Fault Detection System for Electric Fan Drive." *Electronics* 13(3):493. doi:10.3390/electronics13030493 | **Closest prior work** — accelerometer + CNN on MCU for fan faults (supervised, no on-device learning/FL). |

## E. Datasets

| # | Dataset | Notes |
|---|---|---|
| E1 [V] | **UCI "Accelerometer"** — Sampaio et al. (2019), DOI 10.24432/C5Q61V. https://archive.ics.uci.edu/dataset/846/accelerometer | **Cooler fan with blade weights** (doubled weight on neighbouring / perpendicular / opposite blades; no balanced run, despite the page calling the first "normal"), 17 speeds, 50 Hz, MMA8452Q low-cost MEMS. Closest match to the rig. |
| E2 [V] | **MIMII** — Purohit et al., DCASE 2019 Workshop. https://arxiv.org/abs/1909.09347 | Industrial fan/pump/valve/slide-rail sounds, normal + anomalous (incl. rotating unbalance). |
| E3 [V] | **DCASE Task 2** (2020–2025). Koizumi et al. 2020 (arXiv:2006.05822); Kawaguchi et al. 2021 (arXiv:2106.04492); Dohi et al. 2023 (arXiv:2305.07828); Nishida et al. 2025 (arXiv:2506.10097) | Unsupervised anomalous sound detection trained on normal data only; fan in 2020–22 (dev+eval), 2023–25 dev only. Autoencoder baseline. |
| E4 [V] | **MaFaulDa** (UFRJ). https://www02.smt.ufrj.br/~offshore/mfs/page_01.html | SpectraQuest rig, 700–3600 rpm, 50 kHz; normal, imbalance, misalignment, bearing faults (1,951 runs). |
| E5 [V] | **CWRU Bearing Data Center.** https://engineering.case.edu/bearingdatacenter · benchmark study: Smith & Randall (2015), *MSSP* 64–65:100–131 [S] | Seeded bearing faults, 2 hp motor. |
| E6 [V] | **Paderborn** — Lessmeier et al. (2016), PHM Society Europe. https://papers.phmsociety.org/index.php/phme/article/view/1577 | Bearing damage, vibration + motor current, artificial and real damage. |
| E7 [V] | Atmaja et al. (2022). "Lab-scale Vibration Analysis Dataset…" arXiv:2212.14732 | Lab rig: normal, unbalance, misalignment, bearing. |

## F. On-device learning & anomaly detection

| # | Source | Relevance |
|---|---|---|
| F1 [V] | Lin, Zhu, Chen, Wang, Gan, Han (2022). "On-Device Training Under 256KB Memory." *NeurIPS*. https://arxiv.org/abs/2206.15472 | The Tiny Training Engine used in the proposal. |
| F2 [V] | Ren, Anicic, Runkler (2021). "TinyOL: TinyML with Online-Learning on Microcontrollers." *IJCNN*. https://arxiv.org/abs/2103.08295 | Streaming on-MCU learning precedent. |
| F3 [V] | Lin et al. (2023). "Tiny Machine Learning: Progress and Futures." *IEEE CAS Magazine* 23(3). https://arxiv.org/abs/2403.19076 | TinyML survey. |
| F4 [V] | Yamada & Matsutani (2022). "A Sequential Concept Drift Detection Method for On-Device Learning on Low-End Edge Devices." arXiv:2212.09637 | Drift detection + retraining on RP2040 (264 KB). |
| F5 [V] | Pang, Shen, Cao, van den Hengel (2021). "Deep Learning for Anomaly Detection: A Review." *ACM Computing Surveys*. https://arxiv.org/abs/2007.02500 | Reconstruction-based (autoencoder) AD taxonomy. |
| F6 [S] | Givnan et al. (2022). "Anomaly Detection Using Autoencoder Reconstruction upon Industrial Motors." *Sensors* 22(9):3166. | AE on healthy vibration features. |
| F7 [V/S] | **ST NanoEdge AI Studio** (v5.1, free). https://stm32ai.st.com/nanoedge-ai/ · ST wiki AD library · ST community how-to https://community.st.com/t5/stm32-mcus/how-to-use-nanoedge-ai-studio-for-anomaly-detection/ta-p/697858 | **Main prior art.** On-MCU incremental learning (`neai_anomalydetection_learn()`), similarity score 0–100, user-set threshold. **User decides when to learn**; closed-source; no FL. |

## G. Drift vs contamination ("learning the fault as normal")

| # | Source | Relevance |
|---|---|---|
| G1 [V] | Bhatia, Jain, Srivastava, Kawaguchi, Hooi (2022). "MemStream: Memory-Based Streaming Anomaly Detection." *WWW '22*. https://arxiv.org/abs/2106.03837 | Explicitly guards against "memory poisoning" by anomalies. |
| G2 [V] | Li, Malialis, Polycarpou (2023). "Autoencoder-based Anomaly Detection in Streaming Data with Incremental Learning and Concept Drift Adaptation." *IJCNN*. https://arxiv.org/abs/2305.08977 | Incremental AE + drift detection; anomaly-vs-drift distinction. |

## H. RL for thresholds / retraining decisions

| # | Source | Relevance |
|---|---|---|
| H1 [V] | Yang, Howley, Schukat (2023). "ADT: Agent-based Dynamic Thresholding for Anomaly Detection." ALA @ AAMAS. https://arxiv.org/abs/2312.01488 · journal version *Neural Computing & Applications* 2024 [S] | Thresholding as MDP, DQN over AE scores. |
| H2 [S] | Liebman, Zavesky, Stone (2018). "A Stitch in Time – Autonomous Model Management via Reinforcement Learning." *AAMAS*. https://ifaamas.org/Proceedings/aamas2018/pdfs/p990.pdf | **RL deciding when to retrain** — closest precedent for Adapt/Freeze. |
| H3 [S] | Siraskar et al. (2023). "Reinforcement learning for predictive maintenance: a systematic technical review." *Artificial Intelligence Review*. doi:10.1007/s10462-023-10468-6 | RL-for-PdM survey. |
| H4 [V] | Ogunfowora & Najjaran (2023). "Reinforcement and Deep RL-based Solutions for Machine Maintenance Planning…" arXiv:2307.03860 | Survey. |

## I. Federated learning

| # | Source | Relevance |
|---|---|---|
| I1 [S] | Sattler, Müller, Samek (2021). "Clustered Federated Learning…" *IEEE TNNLS* 32(8):3710–3722. doi:10.1109/TNNLS.2020.3015958 | CFL. |
| I2 [V] | Ghosh, Chung, Yin, Ramchandran (2020). "An Efficient Framework for Clustered Federated Learning" (IFCA). *NeurIPS*. https://arxiv.org/abs/2006.04088 | Clustered FL. |
| I3 [V] | Lu, Thelen, Fink, Hu, Laflamme (2023). "Federated Learning with Uncertainty-Based Client Clustering for Fleet-Wide Fault Diagnosis." arXiv:2304.13275 | Clustered FL for fleet fault diagnosis — direct analogue. |
| I4 [V] | Zhou et al. (2021). "A Survey on Federated Learning and its Applications for Accelerating Industrial IoT." arXiv:2104.10501 | FL in IIoT survey. |
| I5 [V] | Kopparapu & Lin (2021). "TinyFedTL: Federated Transfer Learning on Tiny Devices." arXiv:2110.01107 | FL on MCUs. |
| I6 [S] | Llisterri Giménez et al. (2022). "On-Device Training of ML Models on Microcontrollers with Federated Learning." *Electronics* 11(4):573. | On-MCU training + FL (Arduino). |

---

## Stats to AVOID (could not trace to an original source)
- "IEEE 44% / EPRI 41% of motor failures are bearings" → use "30–40%" (D2) instead.
- "X% of fan problems are due to imbalance" → no primary source; say "among the most common" (D1, D5).
- "50–60% of building energy is air-con" → use "about 60%" (C1) or "40–60%" (C2/C3).
- "$50B/yr unplanned downtime" (Deloitte, unsourced); Aberdeen "$260k/hour"; "Deloitte 70% fewer breakdowns"; "wired costs 3x wireless" (vendor blogs).
- Data centres "12% by 2030" projection.

## Gap statement supported by the above
On-MCU training (F1, F2, F7), drift-aware streaming autoencoders (G1, G2), RL for thresholding/retraining (H1, H2), and clustered FL for fleets (I1–I3) each exist separately. No source found combines **an on-MCU RL policy that gates self-learning (Adapt / Freeze / Alert) to prevent a developing fault being learned as normal, on bare-metal STM32, with clustered federated learning across a fan fleet.** The closest commercial tool (NanoEdge AI) leaves the learn/freeze decision to the developer, and the closest academic fan work (D12) is supervised with no on-device adaptation.
