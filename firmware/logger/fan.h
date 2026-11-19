#pragma once
#include <Arduino.h>
#include <HardwarePWM.h>
#include "config.h"

// 4-pin PC fan: 25 kHz PWM speed control and tach pulse counting.
namespace fan {

static volatile uint32_t tachPulses = 0;
static volatile uint32_t tachPeriodUs = 0;
static volatile uint32_t lastEdgeUs = 0;   // tach clock time of the last accepted edge
static volatile uint32_t tachRejected = 0; // edges dropped by the glitch filter

// micros() on this core follows the 1024 Hz FreeRTOS tick (976 us steps). That made tach periods
// coarse and defeated the glitch filter (logger 0.3.0 counted ~1-1.5 % extra pulses under PWM).
// TIMER4 runs free at 1 MHz as the tach clock. TIMER0 belongs to the SoftDevice and the core
// keeps the bootloader version in TIMER2; CC[1] is only used from the tach ISR.
static NRF_TIMER_Type* const TACH_TIMER = NRF_TIMER4;

static inline uint32_t tachClockUs() {
  TACH_TIMER->TASKS_CAPTURE[1] = 1;
  return TACH_TIMER->CC[1];
}

// One nRF52 PWM module, claimed so analogWrite() cannot reconfigure it.
// 16 MHz clock / FAN_PWM_TOP counts = 25 kHz.
static const uint32_t PWM_OWNER = 0x46414E31;  // "FAN1"
static const uint16_t FAN_PWM_TOP = 16 * FAN_PWM_PERIOD_US;
static HardwarePWM* pwm = nullptr;
static uint16_t dutyPermille = 1000;  // unset PWM input = full speed per spec
static bool pwmSet = false;

static void onTachEdge() {
  uint32_t now = tachClockUs();
  uint32_t dt = now - lastEdgeUs;
  // PWM noise on the open-collector line makes extra falling edges, mostly while the line rises
  // slowly through the pull-up, about half a period after a real edge (measured: +1 % pulses).
  // Reject an edge if the line is already high again (a short dip), or if it comes sooner than
  // 3/4 of the previous period (the fan cannot speed up by a third within half a revolution).
  // After a stop (period > 200 ms) only the fixed minimum applies.
  uint32_t minDt = tachPeriodUs - tachPeriodUs / 4;
  if (minDt < TACH_MIN_PERIOD_US || tachPeriodUs > 200000) minDt = TACH_MIN_PERIOD_US;
  if (dt < minDt || digitalRead(PIN_FAN_TACH) == HIGH) {
    tachRejected++;
    return;
  }
  tachPeriodUs = dt;
  lastEdgeUs = now;
  tachPulses++;
}

static void begin() {
  TACH_TIMER->TASKS_STOP = 1;
  TACH_TIMER->MODE = TIMER_MODE_MODE_Timer;
  TACH_TIMER->BITMODE = TIMER_BITMODE_BITMODE_32Bit;
  TACH_TIMER->PRESCALER = 4;  // 16 MHz / 2^4 = 1 MHz
  TACH_TIMER->TASKS_CLEAR = 1;
  TACH_TIMER->TASKS_START = 1;
#if PIN_FAN_TACH >= 0
  // Tach is open-collector: pulled up to 3.3 V here. Never pull it up to 12 V.
  pinMode(PIN_FAN_TACH, INPUT_PULLUP);
  attachInterrupt(digitalPinToInterrupt(PIN_FAN_TACH), onTachEdge, FALLING);
#endif
}

#if PIN_FAN_PWM >= 0
static bool claimPwm() {
  for (int i = HWPWM_MODULE_NUM - 1; i >= 0; i--) {
    HardwarePWM* p = HwPWMx[i];
    if (!p->takeOwnership(PWM_OWNER)) continue;
    p->setClockDiv(PWM_PRESCALER_PRESCALER_DIV_1);
    p->setMaxValue(FAN_PWM_TOP);
    if (!p->addPin(PIN_FAN_PWM)) {
      p->releaseOwnership(PWM_OWNER);
      continue;
    }
    p->begin();
    pwm = p;
    return true;
  }
  return false;
}
#endif

// The PWM pin is left untouched until the first call, so the fan runs at
// full speed (its default) until the host asks for something else.
static bool setDuty(int permille) {
#if PIN_FAN_PWM >= 0
  permille = constrain(permille, 0, 1000);
  if (!pwm && !claimPwm()) return false;
  uint16_t value = (uint32_t)permille * FAN_PWM_TOP / 1000;
  pwm->writePin(PIN_FAN_PWM, value, FAN_PWM_INVERT);
  dutyPermille = permille;
  pwmSet = true;
  return true;
#else
  (void)permille;
  return false;
#endif
}

}  // namespace fan
