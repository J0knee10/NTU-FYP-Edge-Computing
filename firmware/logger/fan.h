#pragma once
#include <Arduino.h>
#include <mbed.h>
#include "config.h"

// 4-pin PC fan: 25 kHz PWM speed control and tach pulse counting.
namespace fan {

static volatile uint32_t tachPulses = 0;
static volatile uint32_t tachPeriodUs = 0;
static volatile uint32_t lastEdgeUs = 0;

static mbed::PwmOut* pwm = nullptr;
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

// The PWM pin is left untouched until the first call, so the fan runs at
// full speed (its default) until the host asks for something else.
static bool setDuty(int permille) {
#if PIN_FAN_PWM >= 0
  permille = constrain(permille, 0, 1000);
  if (!pwm) {
    pwm = new mbed::PwmOut(digitalPinToPinName(PIN_FAN_PWM));
    pwm->period_us(FAN_PWM_PERIOD_US);
  }
  float d = permille / 1000.0f;
  pwm->write(FAN_PWM_INVERT ? 1.0f - d : d);
  dutyPermille = permille;
  pwmSet = true;
  return true;
#else
  (void)permille;
  return false;
#endif
}

}  // namespace fan
