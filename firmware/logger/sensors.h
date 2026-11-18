#pragma once
#include <Arduino.h>
#include <Wire.h>
#include "config.h"

// Minimal non-blocking drivers for the Adafruit Feather nRF52840 Sense sensors
// on the main Wire bus: LSM6DS33 accelerometer (original board revision) and
// SHT3x / SHT4x temperature-humidity. The Adafruit sensor libraries are not
// used: they do not expose the FIFO and they block while a reading converts.

namespace i2c {

// The core's Wire RX buffer is 64 bytes, so one read returns at most 64 bytes.
const uint8_t MAX_READ = 64;

static inline bool write8(uint8_t addr, uint8_t reg, uint8_t val) {
  Wire.beginTransmission(addr);
  Wire.write(reg);
  Wire.write(val);
  return Wire.endTransmission() == 0;
}

static inline bool readN(uint8_t addr, uint8_t reg, uint8_t* buf, uint8_t n) {
  Wire.beginTransmission(addr);
  Wire.write(reg);
  if (Wire.endTransmission(false) != 0) return false;
  if (Wire.requestFrom(addr, n) != n) return false;
  for (uint8_t i = 0; i < n; i++) buf[i] = Wire.read();
  return true;
}

static inline int read8(uint8_t addr, uint8_t reg) {
  uint8_t v;
  return readN(addr, reg, &v, 1) ? v : -1;
}

}  // namespace i2c

// ---- LSM6DS33 accelerometer ----------------------------------------------
// Gyro powered down. The accelerometer runs at IMU_ODR_CODE with the analog
// anti-alias filter set explicitly (XL_BW_SCAL_ODR = 1). Samples go through
// the 8 KB FIFO in continuous mode (X, Y, Z words per sample, ~1.6 s deep at
// 833 Hz) and are read in bursts. If the FIFO self-test fails, falls back to
// polling the data-ready flag, which needs the loop to run every ~1 ms.
namespace imu {

const uint8_t ADDR            = 0x6A;  // SA0 low on the Feather Sense
const uint8_t WHO_AM_I        = 0x0F;
const uint8_t WHO_AM_I_DS33   = 0x69;
const uint8_t FIFO_CTRL3      = 0x08;
const uint8_t FIFO_CTRL5      = 0x0A;
const uint8_t CTRL1_XL        = 0x10;
const uint8_t CTRL2_G         = 0x11;
const uint8_t CTRL3_C         = 0x12;
const uint8_t CTRL4_C         = 0x13;
const uint8_t STATUS_REG      = 0x1E;
const uint8_t OUTX_L_XL       = 0x28;
const uint8_t FIFO_STATUS1    = 0x3A;
const uint8_t FIFO_DATA_OUT_L = 0x3E;

const int MAX_BURST = i2c::MAX_READ / 6;  // samples per I2C read (10)

static int   whoAmI = -1;
static bool  useFifo = false;
static bool  burstOk = false;  // FIFO pops on every word of a multi-byte read
static float mgPerLsb = 0.122f;

// FIFO level in 16-bit words, overrun flag and pattern (index of the next
// word: 0 = X, 1 = Y, 2 = Z). Measured on the board: once the FIFO overflows
// (4096 words) the 12-bit level wraps to 0 and only OVER_RUN/FULL say so.
static bool fifoStatus(int* words, bool* overrun, int* pattern) {
  uint8_t s[4];
  if (!i2c::readN(ADDR, FIFO_STATUS1, s, 4)) return false;
  *words = s[0] | ((s[1] & 0x0F) << 8);
  if (overrun) *overrun = (s[1] & 0x40) || ((s[1] & 0x20) && *words == 0);
  if (pattern) *pattern = s[2] | ((s[3] & 0x03) << 8);
  return true;
}

// Empty the FIFO and start collecting again (bypass -> continuous).
static void restartFifo() {
  i2c::write8(ADDR, FIFO_CTRL5, 0x00);
  i2c::write8(ADDR, FIFO_CTRL5, (IMU_ODR_CODE << 3) | 0b110);
}

static inline bool popWord() {
  uint8_t b[2];
  return i2c::readN(ADDR, FIFO_DATA_OUT_L, b, 2);
}

static inline void decode(const uint8_t* b, int16_t out[3]) {
  for (int k = 0; k < 3; k++) out[k] = (int16_t)(b[2 * k] | (b[2 * k + 1] << 8));
}

// Number of unread samples. In polling mode this is 0 or 1. An overflowed
// FIFO is reset (its contents are already incomplete) and reported as one
// overrun event.
static int available(bool* overrun) {
  if (useFifo) {
    int words, pattern;
    bool ovr;
    if (!fifoStatus(&words, &ovr, &pattern)) return 0;
    if (overrun) *overrun = ovr;
    if (ovr) {
      restartFifo();
      return 0;
    }
    // Defensive: the read pointer should never sit mid-sample, but realign to X.
    if (pattern != 0) {
      for (int i = pattern; i < 3 && words > 0; i++, words--) popWord();
    }
    return words / 3;
  }
  if (overrun) *overrun = false;
  int s = i2c::read8(ADDR, STATUS_REG);
  return (s >= 0 && (s & 0x01)) ? 1 : 0;
}

// Read up to n (<= MAX_BURST) samples. Returns the number read.
static int readSamples(int16_t (*out)[3], int n) {
  if (n > MAX_BURST) n = MAX_BURST;
  uint8_t b[MAX_BURST * 6];
  if (!useFifo) {
    if (!i2c::readN(ADDR, OUTX_L_XL, b, 6)) return 0;
    decode(b, out[0]);
    return 1;
  }
  if (burstOk) {
    if (!i2c::readN(ADDR, FIFO_DATA_OUT_L, b, n * 6)) return 0;
  } else {
    for (int w = 0; w < n * 3; w++) {
      if (!i2c::readN(ADDR, FIFO_DATA_OUT_L, b + 2 * w, 2)) return w / 3;
    }
  }
  for (int i = 0; i < n; i++) decode(b + 6 * i, out[i]);
  return n;
}

// Discard everything buffered so far.
static void flush() {
  if (useFifo) {
    restartFifo();
  } else {
    int16_t tmp[1][3];
    if (available(nullptr)) readSamples(tmp, 1);
  }
}

// Let the FIFO fill, read one burst and check the level dropped by a whole
// burst. If the address does not roll over from FIFO_DATA_OUT_H back to _L,
// a burst pops only one word and the level barely moves.
static bool burstSelfTest() {
  delay(50);
  int before, after;
  if (!fifoStatus(&before, nullptr, nullptr) || before < MAX_BURST * 3 + 9) return false;
  uint8_t b[MAX_BURST * 6];
  if (!i2c::readN(ADDR, FIFO_DATA_OUT_L, b, MAX_BURST * 6)) return false;
  if (!fifoStatus(&after, nullptr, nullptr)) return false;
  // ~1.5 ms read at 400 kHz: at most a few new samples arrive meanwhile.
  int dropped = before - after;
  return dropped >= MAX_BURST * 3 - 9 && dropped <= MAX_BURST * 3;
}

// The FIFO is usable if words pop one at a time (level falls while reading).
static bool fifoSelfTest() {
  delay(50);
  int before, after;
  if (!fifoStatus(&before, nullptr, nullptr) || before < 60) return false;
  for (int i = 0; i < 24; i++) popWord();
  if (!fifoStatus(&after, nullptr, nullptr)) return false;
  return after <= before - 12;
}

static bool begin(int fsG) {
  Wire.begin();
  Wire.setClock(400000);
  whoAmI = i2c::read8(ADDR, WHO_AM_I);
  if (whoAmI != WHO_AM_I_DS33) return false;  // LSM6DS3TR-C boards need a new driver

  i2c::write8(ADDR, CTRL3_C, 0x01);  // SW_RESET
  delay(10);
  i2c::write8(ADDR, CTRL3_C, 0x44);  // BDU | IF_INC
  i2c::write8(ADDR, CTRL2_G, 0x00);  // gyro power-down
  i2c::write8(ADDR, CTRL4_C, 0x80);  // XL_BW_SCAL_ODR: filter from BW_XL, not ODR

  uint8_t fsBits;
  switch (fsG) {
    case 2:  fsBits = 0b00; mgPerLsb = 0.061f; break;
    case 8:  fsBits = 0b11; mgPerLsb = 0.244f; break;
    case 16: fsBits = 0b01; mgPerLsb = 0.488f; break;
    default: fsBits = 0b10; mgPerLsb = 0.122f; break;  // 4 g
  }
  i2c::write8(ADDR, CTRL1_XL, (IMU_ODR_CODE << 4) | (fsBits << 2) | IMU_BW_CODE);

  i2c::write8(ADDR, FIFO_CTRL3, 0x01);  // accelerometer in FIFO, no decimation; gyro out
  restartFifo();                        // FIFO ODR = sensor ODR, continuous mode
  useFifo = fifoSelfTest();
  if (useFifo) {
    burstOk = burstSelfTest();
    flush();
  } else {
    i2c::write8(ADDR, FIFO_CTRL5, 0x00);
  }
  return true;
}

// Count samples for ~1 s to report the real output rate (the internal
// oscillator is not exactly at the nominal ODR).
static float measureRateHz() {
  flush();
  uint32_t t0 = micros();
  uint32_t count = 0;
  int16_t tmp[MAX_BURST][3];
  while (micros() - t0 < 1000000UL) {
    for (int n = available(nullptr); n > 0;) {
      int got = readSamples(tmp, n);
      if (got == 0) break;
      count += got;
      n -= got;
      if (!useFifo) break;
    }
    if (useFifo) delay(5);
  }
  return count * 1e6f / (micros() - t0);
}

}  // namespace imu

// ---- SHT3x / SHT4x temperature and humidity ------------------------------
// One measurement is triggered per read(); the next read (TH_PERIOD_MS later)
// fetches it, so nothing waits for the ~15 ms conversion.
namespace th {

const uint8_t ADDR = 0x44;
enum Kind : uint8_t { NONE, SHT3X, SHT4X };
static Kind kind = NONE;
static bool ok = false;

static uint8_t crc8(const uint8_t* d, int n) {
  uint8_t crc = 0xFF;
  for (int i = 0; i < n; i++) {
    crc ^= d[i];
    for (int b = 0; b < 8; b++) crc = (crc & 0x80) ? (crc << 1) ^ 0x31 : crc << 1;
  }
  return crc;
}

static bool command(uint16_t cmd, bool twoBytes) {
  Wire.beginTransmission(ADDR);
  if (twoBytes) Wire.write((uint8_t)(cmd >> 8));
  Wire.write((uint8_t)(cmd & 0xFF));
  return Wire.endTransmission() == 0;
}

// Read n bytes made of (msb, lsb, crc) triplets; checks every CRC.
static bool readWords(uint8_t* buf, uint8_t n) {
  if (Wire.requestFrom(ADDR, n) != n) return false;
  for (uint8_t i = 0; i < n; i++) buf[i] = Wire.read();
  for (uint8_t i = 0; i < n; i += 3)
    if (crc8(buf + i, 2) != buf[i + 2]) return false;
  return true;
}

static bool trigger() {
  return kind == SHT3X ? command(0x2400, true)    // single shot, high repeatability
                       : command(0xFD, false);    // SHT4x: high precision
}

static const char* name() {
  return kind == SHT3X ? "sht3x" : kind == SHT4X ? "sht4x" : "none";
}

static bool begin() {
  uint8_t b[6];
  if (command(0xF32D, true) && (delay(2), readWords(b, 3))) {
    kind = SHT3X;  // answered "read status register"
  } else if (command(0x89, false) && (delay(2), readWords(b, 6))) {
    kind = SHT4X;  // answered "read serial number"
  } else {
    return false;
  }
  ok = trigger();
  return ok;
}

static bool read(float& tempC, float& humidity) {
  if (!ok) return false;
  uint8_t b[6];
  bool got = readWords(b, 6);
  trigger();
  if (!got) return false;
  float t = (b[0] << 8 | b[1]) / 65535.0f;
  float h = (b[3] << 8 | b[4]) / 65535.0f;
  tempC = -45.0f + 175.0f * t;
  humidity = constrain(kind == SHT3X ? 100.0f * h : -6.0f + 125.0f * h, 0.0f, 100.0f);
  return true;
}

}  // namespace th
