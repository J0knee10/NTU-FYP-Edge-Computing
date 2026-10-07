#pragma once
#include <Arduino.h>
#include <Wire.h>

// Minimal non-blocking drivers for the Nano 33 BLE Sense Rev1 sensors on Wire1.
// The Arduino_LSM9DS1 library fixes the accelerometer at 119 Hz and the
// Arduino_HTS221 library busy-waits on every read, so neither is used here.

namespace i2c {

static inline bool write8(uint8_t addr, uint8_t reg, uint8_t val) {
  Wire1.beginTransmission(addr);
  Wire1.write(reg);
  Wire1.write(val);
  return Wire1.endTransmission() == 0;
}

static inline bool readN(uint8_t addr, uint8_t reg, uint8_t* buf, uint8_t n) {
  Wire1.beginTransmission(addr);
  Wire1.write(reg);
  if (Wire1.endTransmission(false) != 0) return false;
  if (Wire1.requestFrom(addr, n) != n) return false;
  for (uint8_t i = 0; i < n; i++) buf[i] = Wire1.read();
  return true;
}

static inline int read8(uint8_t addr, uint8_t reg) {
  uint8_t v;
  return readN(addr, reg, &v, 1) ? v : -1;
}

}  // namespace i2c

// ---- LSM9DS1 accelerometer ----------------------------------------------
// Gyro is powered down, which puts the chip in accelerometer-only mode where
// CTRL_REG6_XL alone sets the output rate (952 Hz). Samples are buffered in
// the 32-deep FIFO in continuous mode, so the loop may be up to ~33 ms late.
namespace imu {

const uint8_t ADDR         = 0x6B;
const uint8_t WHO_AM_I     = 0x0F;
const uint8_t CTRL_REG1_G  = 0x10;
const uint8_t CTRL_REG6_XL = 0x20;
const uint8_t CTRL_REG8    = 0x22;
const uint8_t CTRL_REG9    = 0x23;
const uint8_t STATUS_REG   = 0x27;
const uint8_t OUT_X_L_XL   = 0x28;
const uint8_t FIFO_CTRL    = 0x2E;
const uint8_t FIFO_SRC     = 0x2F;

static bool  useFifo = false;
static float mgPerLsb = 0.122f;

static inline bool readSample(int16_t out[3]) {
  uint8_t b[6];
  if (!i2c::readN(ADDR, OUT_X_L_XL, b, 6)) return false;
  for (int k = 0; k < 3; k++) out[k] = (int16_t)(b[2 * k] | (b[2 * k + 1] << 8));
  return true;
}

// Number of unread samples. In polling mode this is 0 or 1.
static inline int available(bool* overrun) {
  if (useFifo) {
    int s = i2c::read8(ADDR, FIFO_SRC);
    if (s < 0) return 0;
    if (overrun) *overrun = s & 0x40;
    return s & 0x3F;
  }
  if (overrun) *overrun = false;
  int s = i2c::read8(ADDR, STATUS_REG);
  return (s >= 0 && (s & 0x01)) ? 1 : 0;
}

static inline void flush() {
  int16_t tmp[3];
  for (int n = available(nullptr); n > 0; n--) readSample(tmp);
}

// FIFO only works if reading OUT_X_XL pops it. Let it fill, read 8 samples
// (~2.5 ms, so at most ~3 new ones arrive) and check that the level dropped.
static bool fifoSelfTest() {
  delay(50);
  int before = available(nullptr);
  int16_t tmp[3];
  for (int i = 0; i < 8; i++) readSample(tmp);
  int after = available(nullptr);
  return before >= 30 && after <= before - 4;
}

static bool begin(int fsG) {
  Wire1.begin();
  Wire1.setClock(400000);
  if (i2c::read8(ADDR, WHO_AM_I) != 0x68) return false;

  i2c::write8(ADDR, CTRL_REG8, 0x05);  // SW_RESET | IF_ADD_INC
  delay(10);
  i2c::write8(ADDR, CTRL_REG1_G, 0x00);  // gyro power-down -> accel-only mode

  uint8_t fsBits;
  switch (fsG) {
    case 2:  fsBits = 0b00; mgPerLsb = 0.061f; break;
    case 8:  fsBits = 0b11; mgPerLsb = 0.244f; break;
    case 16: fsBits = 0b01; mgPerLsb = 0.732f; break;
    default: fsBits = 0b10; mgPerLsb = 0.122f; break;  // 4 g
  }
  // ODR_XL = 110 (952 Hz); anti-alias bandwidth chosen automatically from ODR.
  i2c::write8(ADDR, CTRL_REG6_XL, (0b110 << 5) | (fsBits << 3));
  i2c::write8(ADDR, CTRL_REG8, 0x44);  // BDU | IF_ADD_INC

  i2c::write8(ADDR, FIFO_CTRL, 0x00);  // bypass (clears FIFO)
  i2c::write8(ADDR, CTRL_REG9, 0x02);  // FIFO_EN
  i2c::write8(ADDR, FIFO_CTRL, 0xC0);  // continuous mode
  useFifo = true;

  if (!fifoSelfTest()) {
    i2c::write8(ADDR, FIFO_CTRL, 0x00);
    i2c::write8(ADDR, CTRL_REG9, 0x00);
    useFifo = false;
  }
  return true;
}

// Count samples for ~1 s to report the real output rate (the internal
// oscillator is not exactly 952 Hz).
static float measureRateHz() {
  flush();
  uint32_t t0 = micros();
  uint32_t count = 0;
  int16_t tmp[3];
  while (micros() - t0 < 1000000UL) {
    for (int n = available(nullptr); n > 0; n--) {
      readSample(tmp);
      count++;
    }
    if (useFifo) delay(5);
  }
  return count * 1e6f / (micros() - t0);
}

}  // namespace imu

// ---- HTS221 temperature / humidity --------------------------------------
// Runs continuously at 1 Hz; read() only fetches the latest result.
namespace hts {

const uint8_t ADDR = 0x5F;
static bool ok = false;
static float tSlope, tZero, hSlope, hZero;

static int16_t read16(uint8_t reg) {
  int lo = i2c::read8(ADDR, reg);
  int hi = i2c::read8(ADDR, reg + 1);
  return (int16_t)((hi << 8) | lo);
}

static bool begin() {
  if (i2c::read8(ADDR, 0x0F) != 0xBC) return false;
  // Factory calibration, as in the HTS221 datasheet / Arduino_HTS221.
  uint8_t h0rH = i2c::read8(ADDR, 0x30);
  uint8_t h1rH = i2c::read8(ADDR, 0x31);
  uint8_t msb = i2c::read8(ADDR, 0x35);
  uint16_t t0degC = i2c::read8(ADDR, 0x32) | ((msb & 0x03) << 8);
  uint16_t t1degC = i2c::read8(ADDR, 0x33) | ((msb & 0x0C) << 6);
  int16_t h0Out = read16(0x36);
  int16_t h1Out = read16(0x3A);
  int16_t t0Out = read16(0x3C);
  int16_t t1Out = read16(0x3E);
  hSlope = (h1rH - h0rH) / (2.0f * (h1Out - h0Out));
  hZero = h0rH / 2.0f - hSlope * h0Out;
  tSlope = (t1degC - t0degC) / (8.0f * (t1Out - t0Out));
  tZero = t0degC / 8.0f - tSlope * t0Out;

  i2c::write8(ADDR, 0x20, 0x85);  // CTRL_REG1: power on, BDU, 1 Hz
  ok = true;
  return true;
}

static bool read(float& tempC, float& humidity) {
  if (!ok) return false;
  int st = i2c::read8(ADDR, 0x27);
  if (st < 0 || (st & 0x03) != 0x03) return false;
  humidity = constrain(read16(0x28) * hSlope + hZero, 0.0f, 100.0f);
  tempC = read16(0x2A) * tSlope + tZero;
  return true;
}

}  // namespace hts
