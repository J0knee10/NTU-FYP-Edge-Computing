# NTU FYP: Plug-and-Play Edge AI Fault Detector for Rotating Machinery

## 1. Project Context & Vision
- **Student:** Jonathan Low Seng Kian (jlow100@e.ntu.edu.sg)
- **Institution / Period:** Nanyang Technological University (NTU), AY2026/2027 (Commencement Aug 2026)
- **Primary Objective:** Build a commercial-grade, plug-and-play retrofit sensor kit that attaches to rotating machinery (pumps, CNC spindles, motors) to passively learn baseline vibrations over an initial burn-in period (e.g., 2-3 days) and subsequently detect anomalies without manual threshold calibration.
- **Hardware Target:** STM32 Cortex-M Microcontroller (targeting bare-metal or FreeRTOS, 128KB-512KB SRAM constraint).
- **Communication:** MQTT over lightweight networking (lwIP / Wi-Fi / Ethernet) pushing weight updates to a central server for **Federated Learning (FL)**.

---

## 2. Theoretical Clarification: Why the Original Concept is Not RL
The original project proposal described the local engine as:
> *"A local RL agent trained to predict the expected next state based on historical operation... the reward function incentivizes the agent to minimize prediction error. Large divergence produces a massive negative reward, triggering a fault alert."*

### The Scientific Reality
1. **Unsupervised / Self-Supervised Learning (What the product actually does):**
   - Passive time-series next-step forecasting or autoencoding minimizes Mean Squared Error (MSE) via gradient descent backpropagation.
   - The device is purely a **passive observer**—it takes no physical or environmental action.
   - Calling predictive error minimization "Reinforcement Learning" will be flagged as technically incorrect by academic examiners/professors.

2. **Reinforcement Learning (RL Definition):**
   - Requires an agent acting within a Markov Decision Process (MDP): an agent takes an **action** in a state, affecting the environment or its operational policy, and receives a scalar **reward**.
   - Without active control decisions, policy exploration, and state transitions driven by actions, an RL framing for simple passive curve fitting does not hold.

---

## 3. The Two Strategic Architectural Options

The student is consulting their FYP supervisor to determine whether the exact methodology of **"Reinforcement Learning"** is mandatory for project approval. Below are the two pathways:

### Option 1: The Clean Industry-Standard Path (No RL)
*Use this if the supervisor agrees that RL is not strictly required.*

- **Title / Framing:**  
  *Plug-and-Play Edge AI Fault Detector using On-Device Self-Supervised Learning and Federated Learning on Microcontrollers*
- **Local Engine (On-Device):**
  - Lightweight Autoencoder (e.g., Conv1D-Autoencoder or compact MLP) running on Cortex-M.
  - **Burn-in Phase:** Device runs continuous forward + backward passes for a few days to memorize normal vibration FFT/RMS signatures using on-device backprop (via Tiny Training Engine / lightweight C++ engine with frozen lower layers or sparse updates).
  - **Inference Phase:** High reconstruction error flags mechanical anomalies (bearing faults, unbalance, misalignment).
- **Global Engine (Federated Learning):**
  - Devices periodically transmit model weights via MQTT to a central aggregator running Clustered Federated Learning (e.g., FedAvg/IFCA).
  - Enables fleet-wide learning across similar motor types while preserving data privacy and minimizing network bandwidth.
- **Pros:** Academically sound, clean story, fewer points of failure, directly mirrors modern industrial TinyML predictive maintenance.

---

### Option 2: The Dual-Engine Path with Genuine RL (If RL is Mandatory)
*Use this if the supervisor mandates the explicit inclusion of Reinforcement Learning.*

- **Title / Framing:**  
  *Plug-and-Play Edge AI Fault Detector using Federated Anomaly Detection and On-Device Reinforcement Learning for Adaptive Sensing & Alarm Policies*
- **How RL is genuinely integrated (Solving real IoT edge constraints):**
  - **The Problem:** Continuous 10 kHz vibration sampling and neural network inference rapidly drains battery life, while raw thresholding causes excessive false alarms in noisy factory environments.
  - **The RL Formulation (Contextual Bandit / Q-Learning on MCU):**
    - **State:** Moving statistical features (RMS vibration, recent reconstruction errors from the detector, temperature, current battery level / duty cycle).
    - **Action:** Operational decisions chosen by the MCU agent:
      1. `DEEP_SLEEP`: Sleep for 10-30 minutes to conserve power.
      2. `QUICK_SAMPLE`: Wake up for 500ms, run cheap time-domain checks.
      3. `FULL_DIAGNOSTIC`: Trigger high-frequency sensor burst + run full anomaly model.
      4. `FIRE_ALARM`: Dispatch MQTT urgent maintenance alert.
    - **Reward:**
      - Positive reward for remaining in low-power sleep while machine is healthy.
      - High penalty if an alarm is triggered but machine returns to normal without human confirmation (false alarm).
      - Catastrophic penalty if vibration spikes persist and the sensor failed to wake up in time.
- **Federated Engine:** Continues to aggregate both the anomaly detector weights and the shared RL policy across machines.
- **Pros:** Scientifically rigorous use of RL that examiners will praise, directly solves battery and false alarm problems on embedded systems.

---

## 4. Hardware & Technical Stack Recommendations

- **Target Microcontroller:** STM32 family with hardware FPU (e.g., STM32F401/F446RE, STM32H7, or STM32U5 for ultra-low power). Minimum 256KB SRAM recommended for backward-pass activation memory + MQTT networking buffers.
- **Sensors:** 3-axis digital accelerometer / IMU (e.g., ADXL345, ISM330DHCX, or MPU6050 via SPI/I2C with DMA).
- **Networking:** FreeRTOS + lwIP (or ESP32/Wi-Fi co-processor via UART AT commands) pushing binary payloads via MQTT.
- **ML Toolchain:** Python (PyTorch/TensorFlow) for simulation and baseline validation -> C/C++ generation for Cortex-M (Tiny Training Engine / CMSIS-NN).

---

## 5. Next Immediate Steps (Phase 1)
1. **Supervisor Consultation:** Confirm whether **Option 1** (Self-Supervised + FL) or **Option 2** (Self-Supervised Anomaly Detection + RL Policy + FL) is preferred.
2. **Phase 1 Implementation:**
   - Set up synthetic and public rotating machinery datasets (e.g., NASA Bearing Dataset / CWRU).
   - Build a Python simulator to validate the baseline detector and the Federated Learning aggregation script.
