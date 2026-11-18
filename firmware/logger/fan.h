#pragma once
#include <Arduino.h>
#include <HardwarePWM.h>
#include "config.h"

// 4-pin PC fan: 25 kHz PWM speed control and tach pulse counting.
namespace fan {

static volatile uint32_t tachPulses = 0;
static volatile uint32_t tachPeriodUs = 0;
static volatile uint32_t lastEdgeUs = 0;

// One nRF52 PWM module, claimed so analogWrite() cannot reconfigure it.
// 16 MHz clock / FAN_PWM_TOP counts = 25 kHz.
static const uint32_t PWM_OWNER = 0x46414E31;  // "FAN1"
static const uint16_t FAN_PWM_TOP = 16 * FAN_PWM_PERIOD_US;
static HardwarePWM* pwm = nullptr;
static uint16_t dutyPermille = 1000;  // unset PWM input = full speed per spec
static bool pwmSet = false;

static void onTachEdge() {
  uint32_t now = micros();
  uint32_t dt = now - lastEdgeUs;
  if (dt < TACH_MIN_PERIOD_US) return;
  tachPeriodUs = dt;
  lastEdgeUs = now;
  tachPulses++;
}

static void begin() {
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
