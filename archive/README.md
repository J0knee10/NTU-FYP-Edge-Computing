# Archive

Superseded material from earlier project directions. Kept for history only — do not build on it.
The current direction is described in `../docs/FYP_predictive_maintenance_proposal.docx` (revised 23 Sep 2026).

| Item | Why it is archived |
|---|---|
| `fyp_edge_ai_fault_detector_proposal.docx` | Aug 2026 proposal: STM32 bare-metal, generic rotating machinery, "RL" framed as next-state prediction. Replaced by the fan proposal. |
| `CrossRoads.md` | Decision note weighing "no RL" vs "RL for duty-cycling". Resolved differently: the final design uses RL to gate on-device learning (ADAPT / FREEZE / ALERT). |
| `PassiveSelfDetectionLitReview.docx` | Literature review for the STM32 / no-RL direction. Current sources are in `../docs/literature_sources.md` and section 6 of the proposal. |
| `stage1_cwru_prototype/` | First Python prototype (PyTorch autoencoder + unweighted FedAvg on CWRU bearing data). CWRU is sampled at 12/48 kHz, far above the Nano 33 BLE Sense Rev1 IMU (~952 Hz), so it is only a secondary benchmark now. Parts may be salvaged into the new pipeline. |
