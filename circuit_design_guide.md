# Practical Circuit Design Guide for Firmware Engineers

> **Author:** Jonathan Low / Engineering Reference  
> **Location:** `NTU-FYP-Edge-Computing / circuit_design_guide.md`  
> **Audience:** Firmware & Embedded Engineers transitioning to Circuit Design  

---

## 1. Introduction: The Mental Model Shift

As a firmware engineer, you naturally think in terms of **registers, state machines, timing diagrams, bus protocols (SPI/I2C/UART), and data flow**. 

Circuit design is the exact same discipline, but implemented in physical physics across three continuous variables:
1. **Voltage** — Logic thresholds, supply rails, voltage references, signal headroom, and ground reference.
2. **Current** — Quiescent draw, dynamic switching inrush, sink/source limits, and fault/ESD paths.
3. **Impedance ($Z$)** — Source impedance vs. load impedance, high-Z inputs, low-Z drivers, and impedance matching.

```
       FIRMWARE PERSPECTIVE                 HARDWARE / CIRCUIT PERSPECTIVE
 ┌──────────────────────────────┐        ┌──────────────────────────────────┐
 │ Registers, Bits & Protocols  │        │ Voltages, Current Limits & Noise │
 │ State Machines & Algorithms  │  ◄──►  │ Transfer Functions & Filtering   │
 │ Drivers & Peripherals (HAL)  │        │ Physical Protection & Buffering  │
 └──────────────────────────────┘        └──────────────────────────────────┘
```

---

## 2. The 6-Step End-to-End Circuit Design Process

```
[Step 1: Requirements & System Budgets]
              │
              ▼
[Step 2: Pick "Anchor" ICs (MCU, AFEs, Power)]
              │
              ▼
[Step 3: Power Tree & Grounding Strategy]
              │
              ▼
[Step 4: Signal Conditioning & Passive Selection (R, C, L, Op-Amps)]
              │
              ▼
[Step 5: External Interfaces, Protection & DFT (Test Points)]
              │
              ▼
[Step 6: Simulation, ERC & Schematic Review]
```

### Step 1: Requirements & System Budgets
Before opening KiCad or placing a single part, write down the **system budgets**:
* **Signal Budget:** What are the inputs? (Amplitude: µV, mV, or 3.3 V? Bandwidth: DC, audio 20 kHz, radio MHz? Differential or single-ended?)
* **Power Budget:** What power sources are available? (USB 5 V, LiPo 3.7 V, 12 V bench, battery?) What is the total estimated current draw per rail?
* **Pin & Peripheral Budget:** How many SPI, I2C, UART, ADC channels, PWMs, and external interrupts (`EXTI`) are needed? Add **20% spare GPIOs**.

### Step 2: Pick the "Anchor" ICs First
**Always pick the key ICs first.** You do not start with resistors and capacitors.
1. **The Brain:** MCU / SoC / FPGA chosen based on core speed, RAM/Flash, required peripherals, and package hand-solderability (e.g. STM32H753, nRF52840, RP2040).
2. **Specialized Front-Ends / Sensors:** Dedicated ICs that do what the MCU cannot do accurately:
   * Bio-potentials $\rightarrow$ `ADS1298` (24-bit multi-channel ECG/EMG AFE)
   * High-precision RTD/NTC temperature $\rightarrow$ `ADS1220`
   * Fast analog multiplexing $\rightarrow$ `ADG1606` / `ADG1206`
   * Motion sensing $\rightarrow$ `ICM-42688-P` / `LSM9DS1`
3. **The Golden Rule for ICs:** **Never design support circuitry from a blank sheet.** 
   * Look up the IC's **Evaluation Board Schematic** (EVB / PDK) and the datasheet's **Application Information** section.
   * IC manufacturers (TI, ADI, ST) spend hundreds of engineering hours optimizing decoupling, reference circuits, and layout recommendations. Use their reference design as your baseline.

### Step 3: Power Tree & Grounding Architecture
Draw the power flow diagram before wiring chips:
```
  5V Bench / USB
        │
        ├──────────────────────► High-power loads (Motors, LEDs, Relays)
        │
        ├──► Buck / Switcher ──► +3.3V Digital (MCU, Flash, Fast Digital IO)
        │
        └──► Isolated DC-DC / LDO ──► ±7.3V / +3.3V Analog (Op-amps, References, ADCs)
```
* **Switching Regulators (Buck/Boost):** Use when high efficiency is required or when dropping large voltages at high current ($5\text{V} \rightarrow 3.3\text{V}$ at $1\text{ A}$). They generate high-frequency switching ripple.
* **Linear Regulators (LDOs):** Use for sensitive analog circuitry. They have no switching ripple and provide high Power Supply Rejection Ratio (PSRR), but dissipate heat:
  $$P_{\text{loss}} = (V_{\text{in}} - V_{\text{out}}) \times I_{\text{load}}$$
* **Grounding:**
  * **Digital GND:** Noisy return currents from fast clock edges and MCU switching.
  * **Analog GND (`AGND`):** Quiet return path for microvolt-level signals.
  * Tie them together at **only one single star point** (e.g. via a Net-Tie footprint `NT` near the ADC).

---

## 3. How to Know Where to Put Resistors, Capacitors, and Op-Amps

Passives are not decorative—every resistor, capacitor, and op-amp performs a specific physical role:

### 1. Resistors: Current Control & State Definition

| Function | Circuit Location | Why it is needed | Typical Values |
|---|---|---|---|
| **Pull-Up / Pull-Down** | I2C lines (`SDA`/`SCL`), Reset pins, SPI `CS`, MUX `EN` | Digital lines float when tristated or during MCU reset. Pull-ups/downs prevent floating states that cause high power draw or random glitching. | $2.2\text{ k}\Omega - 10\text{ k}\Omega$ (I2C)<br>$10\text{ k}\Omega - 100\text{ k}\Omega$ (CS/Reset) |
| **Current Limiting** | In series with ADC inputs, transistor gates, LEDs, connectors | Protects silicon. Limits fault current into internal ESD clamp diodes if an op-amp rail swings to its maximum. | $100\text{ }\Omega - 1\text{ k}\Omega$ (ADC/IO)<br>$220\text{ }\Omega - 1\text{ k}\Omega$ (LEDs) |
| **Series Termination** | In series at the source of fast digital clocks (`SCK`, `MOSI`) | Fast edges have high frequency content that bounces off high-Z receiver inputs. Damps transmission line reflections and ringing. | $22\text{ }\Omega - 47\text{ }\Omega$ |
| **Voltage Dividers** | Level shifting, ADC scaling, LDO voltage setting | Scales a high voltage down into the ADC's valid input range: $V_{\text{out}} = V_{\text{in}} \cdot \frac{R_2}{R_1 + R_2}$. | $1\text{ k}\Omega - 100\text{ k}\Omega$ |
| **Op-Amp Feedback** | Output to inverting input ($R_f, R_g$) | Sets closed-loop negative feedback gain: Non-inverting $G = 1 + R_f / R_g$; Inverting $G = -R_f / R_g$. | $1\text{ k}\Omega - 100\text{ k}\Omega$ |

---

### 2. Capacitors: Charge Storage, Decoupling & Filtering

| Function | Circuit Location | Why it is needed | Typical Values |
|---|---|---|---|
| **High-Frequency Decoupling** | Between $V_{DD}$ and GND, physically $<2\text{ mm}$ from every IC pin | IC transistors draw huge bursts of current within nanoseconds. Trace inductance prevents the power supply from delivering current instantly; local caps provide this instant charge. | $100\text{ nF}$ ceramic (X7R / X5R) |
| **Bulk Storage** | Board power entry and regulator outputs | Absorbs low-frequency load steps and provides loop stability for LDOs and DC-DC converters. | $10\text{ µF} - 100\text{ µF}$ (tantalum/electrolytic/ceramic) |
| **DC-Blocking (AC Coupling)** | In series with analog signals (audio, ECG, EIT, pulses) | Blocks unwanted DC offsets (e.g. half-cell electrode potentials that would saturate an amplifier) while passing AC waveforms. Cutoff: $f_c = \frac{1}{2\pi R C}$. | $10\text{ nF} - 1\text{ µF}$ film or C0G |
| **Anti-Aliasing / Low-Pass Filter** | Directly in front of ADC inputs | An ADC cannot distinguish frequencies above $f_s / 2$ (Nyquist theorem; causes aliasing). A low-pass filter strips out high-frequency noise before sampling. | $R = 100\text{ }\Omega - 1\text{ k}\Omega$,<br>$C = 1\text{ nF} - 10\text{ nF}$ |
| **Feedback Phase Compensation** | Across op-amp feedback resistors | Counteracts stray/parasitic load capacitance (e.g., from cables or multiplexers) to restore phase margin and stop oscillations. | $10\text{ pF} - 47\text{ pF}$ C0G |

> **Capacitor Dielectric Tip:**
> * Use **C0G / NP0** for analog filters, timing, and ADC inputs (zero voltage coefficient, zero temperature drift, no microphonics).
> * Use **X7R / X5R** for power supply decoupling.
> * Avoid **Y5V / Z5U** (loses up to 80% of capacitance under rated voltage and temperature).

---

### 3. Op-Amps: Impedance Matching & Signal Conditioning

You need an op-amp whenever you must change the **amplitude** or **impedance** of a signal:

```
WEAK SENSOR (High Output Z)                       ADC / LOAD (Low Input Z)
 ┌───────────────┐        ┌──────────────────┐        ┌──────────────┐
 │ High internal │  ───►  │  BUFFER / OP-AMP │  ───►  │ Requires low │
 │  resistance   │        │ High Zin, Low Zout│       │ driving Z    │
 └───────────────┘        └──────────────────┘        └──────────────┘
```

* **Voltage Follower (Buffer, Gain = 1):**
  * Input impedance $\approx \infty$, output impedance $\approx 0\text{ }\Omega$.
  * *Why you need it:* Connecting a high-impedance divider or sensor directly to an ADC pin creates a "loading effect" that pulls down the signal. A buffer isolates the sensor.
* **Instrumentation Amplifier (In-Amp, e.g. AD8421, INA333):**
  * Measures tiny differential voltages ($\mu\text{V}$ to $\text{mV}$) in the presence of large common-mode noise (mains 50/60 Hz hum, human body potential).
* **Active Filters (e.g., Sallen-Key):**
  * Creates steep 2nd or 4th order low-pass filtering without loading preceding stages.
* **Level Shifters:**
  * Shifts a bipolar signal ($\pm 1.5\text{ V}$) up to mid-scale ($+1.65\text{ V}$) so a single-supply MCU ADC ($0 - 3.3\text{ V}$) can digitize both positive and negative half-cycles.

---

## 4. What Else is Needed in Circuit Design?

### 1. Circuit Protection (The "Real World" Boundary)
Never let an external connector pin touch a bare MCU pin:
* **TVS Diodes (Transient Voltage Suppressors):** Placed right at connectors to clamp Electrostatic Discharge (ESD) from human fingers or cables to ground within picoseconds.
* **Reverse Polarity Protection:** A high-side P-MOSFET (or Schottky diode) prevents smoke if external power wires are reversed.
* **PTC Resettable Fuses (Polyfuses):** Trips during shorts or overcurrent events and resets once cooled.

### 2. Design for Testability (DFT) — Essential for Firmware Bring-Up
* **Test Points (`TP`):** Place accessible probe pads on:
  * Every power supply rail (+5V, +3.3V, analog rails)
  * Ground reference
  * Intermediate analog nodes (DAC output, filter output, in-amp output, ADC input)
  * SPI clock and bus lines
* **0 Ω Jumpers / Solder Bridges:** Place 0 Ω resistors between power domains or critical sub-circuits. If the board has a short or a sub-circuit malfunctions during bring-up, you can desolder the 0 Ω resistor to isolate the fault without cutting PCB traces.
* **Status LEDs:** Always provide at least one power LED and 1–2 firmware-controlled GPIO status LEDs (e.g., heartbeat, error).

---

## 5. Top 8 Circuit Design Gotchas That Ruin First Revisions

1. **Floating Inputs:** Never leave unused CMOS inputs, reset pins, or enable lines unconnected. Always pull them high or low.
2. **Missing Pull-Ups on Open-Drain Buses:** I2C lines (`SDA`, `SCL`) require external pull-up resistors ($2.2\text{ k}\Omega - 4.7\text{ k}\Omega$) unless built into the breakout module.
3. **Overdriving MCU Pins:** STM32 5V-tolerant pins are only 5V-tolerant in digital input mode when $V_{DD}$ is powered. In analog mode (ADC), voltages $> V_{DDA} + 0.3\text{ V}$ will destroy the pin!
4. **Thermal Dissipation on LDOs:** Dropping 12 V to 3.3 V with a linear LDO drawing $300\text{ mA}$ generates:
   $$P = (12 - 3.3) \times 0.3 = 2.61\text{ W}$$
   A small SOT-23 package will overheat and shut down in seconds. Use a switching buck converter first.
5. **Shared SPI Modes:** Different chips on the same SPI bus may require different modes (Mode 0 vs Mode 1). Firmware must reconfigure SPI clock polarity (`CPOL`) and phase (`CPHA`) dynamically between device selections.
6. **Mismatched Connector Pinouts:** Always verify connector pinouts from both the mating cable view and the board footprint view. (Pin 1 orientation errors are the #1 cause of redesigns).
7. **Neglecting Decoupling Proximity:** A 100 nF capacitor placed 3 cm away from an IC through long, thin traces is useless at high frequencies due to trace inductance. Place it immediately adjacent to the $V_{DD}$ pin with a via straight to GND.
8. **DC-DC Converter Inrush / Hot-Plugging:** High-power isolated DC-DC modules often cannot be plugged into a live DC rail without an LC inrush current spike destroying the input stage. Always switch power from the source.

---

## 6. Quick Reference Formulas

| Formula Name | Equation | Purpose / Application |
|---|---|---|
| **Ohm's Law** | $V = I \cdot R$ | Sizing resistors, calculating voltage drops. |
| **RC Filter Cutoff** | $f_c = \frac{1}{2\pi R C}$ | Sizing low-pass / high-pass filters and AC-coupling caps. |
| **Voltage Divider** | $V_{\text{out}} = V_{\text{in}} \cdot \frac{R_2}{R_1 + R_2}$ | Scaling voltages into ADC ranges. |
| **LED Resistor** | $R = \frac{V_{\text{supply}} - V_f}{I_{\text{LED}}}$ | Sizing LED current limit ($V_f \approx 2.0\text{V}$ green, $I \approx 2-5\text{mA}$). |
| **Non-Inverting Gain** | $G = 1 + \frac{R_f}{R_g}$ | Setting op-amp closed-loop amplification. |
| **Inverting Gain** | $G = -\frac{R_f}{R_{\text{in}}}$ | Setting inverting op-amp amplification. |
| **Power Dissipation** | $P = V \cdot I = I^2 R = \frac{V^2}{R}$ | Sizing resistor power ratings (0603 $\approx 100\text{mW}$, 0805 $\approx 125\text{mW}$). |
| **ADC LSB Resolution** | $1\text{ LSB} = \frac{V_{\text{REF}}}{2^N}$ | Calculating minimum detectable voltage for an $N$-bit ADC. |
