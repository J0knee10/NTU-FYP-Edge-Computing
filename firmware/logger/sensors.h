#pragma once
#include <Arduino.h>
#include <Wire.h>
#include "config.h"

// Minimal non-blocking drivers for the Adafruit Feather nRF52840 Sense sensors
// on the main I2C bus (TWIM0): LSM6DS33 accelerometer + gyroscope (original
// board revision), LIS3MDL magnetometer, SHT3x/SHT4x temperature-humidity,
// BMP280 pressure and APDS9960 ambient light. The Adafruit sensor libraries
// are not used: they do not expose the FIFO and they block while converting.

namespace i2c {

// IMU register access as hardware-sequenced TWIM transactions, chained by
// SHORTS: write -> stop, or write reg -> repeated start -> read n -> stop.
//
// Wire.requestFrom() is not used for these: it waits for LASTRX and then
// triggers STOP in software. An interrupt in that ~22 us window (e.g. the PDM
// callback) lets the TWIM clock extra bytes, which pops extra words from the
// IMU FIFO. Measured 18 Nov: 1.1 % corrupted IMU samples with audio on.
//
// Wire (TWIM0) stays configured as it was. Every TWIM event is cleared before
// and after, because Wire polls events without clearing them first: a stale
// LASTTX/LASTRX from here would make Wire's next transfer stop early.
static uint8_t txBuf[2];  // DMA source must be in RAM

static inline void clearEvents(NRF_TWIM_Type* t) {
  t->EVENTS_STOPPED = 0;
  t->EVENTS_ERROR = 0;
  t->EVENTS_SUSPENDED = 0;
  t->EVENTS_RXSTARTED = 0;
  t->EVENTS_TXSTARTED = 0;
  t->EVENTS_LASTRX = 0;
  t->EVENTS_LASTTX = 0;
  t->ERRORSRC = t->ERRORSRC;  // write-1-to-clear
}

static bool transfer(uint8_t addr, uint8_t ntx, uint8_t* rx, uint16_t nrx) {
  NRF_TWIM_Type* t = NRF_TWIM0;
  t->ADDRESS = addr;
  t->TXD.PTR = (uint32_t)txBuf;
  t->TXD.MAXCNT = ntx;
  t->RXD.PTR = (uint32_t)rx;
  t->RXD.MAXCNT = nrx;
  clearEvents(t);
  t->SHORTS = nrx ? (TWIM_SHORTS_LASTTX_STARTRX_Msk | TWIM_SHORTS_LASTRX_STOP_Msk)
                  : TWIM_SHORTS_LASTTX_STOP_Msk;
  t->TASKS_RESUME = 1;
  t->TASKS_STARTTX = 1;
  bool error = false;
  uint32_t t0 = micros();
  while (!t->EVENTS_STOPPED) {
    if ((t->EVENTS_ERROR || micros() - t0 > 20000) && !error) {
      error = true;
      t->TASKS_STOP = 1;
    }
    if (micros() - t0 > 40000) break;  // bus stuck; give up
  }
  t->SHORTS = 0;
  bool ok = !error && t->TXD.AMOUNT == ntx && (nrx == 0 || t->RXD.AMOUNT == nrx);
  clearEvents(t);
  return ok;
}

static bool write8(uint8_t addr, uint8_t reg, uint8_t val) {
  txBuf[0] = reg;
  txBuf[1] = val;
  return transfer(addr, 2, nullptr, 0);
}

static bool readN(uint8_t addr, uint8_t reg, uint8_t* buf, uint16_t n) {
  txBuf[0] = reg;
  return transfer(addr, 1, buf, n);
}

static inline int read8(uint8_t addr, uint8_t reg) {
  uint8_t v;
  return readN(addr, reg, &v, 1) ? v : -1;
}

}  // namespace i2c

// ---- LSM6DS33 accelerometer + gyroscope -----------------------------------
// Both run at IMU_ODR_CODE and are interleaved in the 8 KB FIFO (continuous
// mode): 6 words per sample with the gyro on (~0.8 s deep at 833 Hz), 3 with
// it off. The accelerometer's analog anti-alias filter is set explicitly
// (XL_BW_SCAL_ODR = 1). Samples are read in bursts. If the FIFO self-test
// fails, falls back to polling the data-ready flag (needs a ~1 ms loop).
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
const uint8_t OUTX_L_G        = 0x22;
const uint8_t FIFO_STATUS1    = 0x3A;
const uint8_t FIFO_DATA_OUT_L = 0x3E;

// Samples per I2C read. Kept short (~1.4 ms with the gyro on) so the
// magnetometer, which has no FIFO, can be polled between bursts.
const int MAX_BURST = 5;

static int   whoAmI = -1;
static bool  gyroOn = IMU_GYRO;
static bool  useFifo = false;
static bool  burstOk = false;   // FIFO pops on every word of a multi-byte read
static bool  gyroFirst = true;  // FIFO order within a sample (detected at boot)
static float mgPerLsb = 0.122f;
static float mdpsPerLsb = 4.375f;  // +-125 dps

static inline int words() { return gyroOn ? 6 : 3; }

// FIFO level in 16-bit words, overrun flag and pattern (index of the next
// word within a sample). Measured on the board: once the FIFO overflows
// (4096 words) the 12-bit level wraps to 0 and only OVER_RUN/FULL say so.
static bool fifoStatus(int* level, bool* overrun, int* pattern) {
  uint8_t s[4];
  if (!i2c::readN(ADDR, FIFO_STATUS1, s, 4)) return false;
  *level = s[0] | ((s[1] & 0x0F) << 8);
  if (overrun) *overrun = (s[1] & 0x40) || ((s[1] & 0x20) && *level == 0);
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

static inline void decode3(const uint8_t* b, int16_t out[3]) {
  for (int k = 0; k < 3; k++) out[k] = (int16_t)(b[2 * k] | (b[2 * k + 1] << 8));
}

// Split one sample's raw bytes into accelerometer and gyro triples.
static inline void decodeSample(const uint8_t* b, int16_t acc[3], int16_t gyr[3]) {
  if (!gyroOn) {
    decode3(b, acc);
    gyr[0] = gyr[1] = gyr[2] = 0;
  } else if (gyroFirst) {
    decode3(b, gyr);
    decode3(b + 6, acc);
  } else {
    decode3(b, acc);
    decode3(b + 6, gyr);
  }
}

// Number of unread samples. In polling mode this is 0 or 1. An overflowed
// FIFO is reset (its contents are already incomplete) and reported as one
// overrun event.
static int available(bool* overrun) {
  if (useFifo) {
    int level, pattern;
    bool ovr;
    if (!fifoStatus(&level, &ovr, &pattern)) return 0;
    if (overrun) *overrun = ovr;
    if (ovr) {
      restartFifo();
      return 0;
    }
    // Defensive: the read pointer should never sit mid-sample, but realign.
    if (pattern != 0) {
      for (int i = pattern; i < words() && level > 0; i++, level--) popWord();
    }
    return level / words();
  }
  if (overrun) *overrun = false;
  int s = i2c::read8(ADDR, STATUS_REG);
  int need = gyroOn ? 0x03 : 0x01;  // XLDA (| GDA)
  return (s >= 0 && (s & need) == need) ? 1 : 0;
}

// Read up to n (<= MAX_BURST) samples. Returns the number read.
static int readSamples(int16_t (*acc)[3], int16_t (*gyr)[3], int n) {
  if (n > MAX_BURST) n = MAX_BURST;
  uint8_t b[MAX_BURST * 12];
  const int bytes = 2 * words();
  if (!useFifo) {
    // Output registers: gyro 0x22-0x27 then accel 0x28-0x2D.
    if (!i2c::readN(ADDR, OUTX_L_G, b, 12)) return 0;
    decode3(b + 6, acc[0]);
    if (gyroOn) decode3(b, gyr[0]); else gyr[0][0] = gyr[0][1] = gyr[0][2] = 0;
    return 1;
  }
  if (burstOk) {
    if (!i2c::readN(ADDR, FIFO_DATA_OUT_L, b, n * bytes)) return 0;
  } else {
    for (int w = 0; w < n * words(); w++) {
      if (!i2c::readN(ADDR, FIFO_DATA_OUT_L, b + 2 * w, 2)) return w / words();
    }
  }
  for (int i = 0; i < n; i++) decodeSample(b + bytes * i, acc[i], gyr[i]);
  return n;
}

// Discard everything buffered so far.
static void flush() {
  if (useFifo) {
    restartFifo();
  } else {
    int16_t a[1][3], g[1][3];
    if (available(nullptr)) readSamples(a, g, 1);
  }
}

// Let the FIFO fill, read one burst and check the level dropped by a whole
// burst. If the address does not roll over from FIFO_DATA_OUT_H back to _L,
// a burst pops only one word and the level barely moves.
static bool burstSelfTest() {
  delay(50);
  int before, after;
  const int burstWords = MAX_BURST * words();
  if (!fifoStatus(&before, nullptr, nullptr) || before < burstWords + 3 * words()) return false;
  uint8_t b[MAX_BURST * 12];
  if (!i2c::readN(ADDR, FIFO_DATA_OUT_L, b, 2 * burstWords)) return false;
  if (!fifoStatus(&after, nullptr, nullptr)) return false;
  // ~1.5 ms read at 400 kHz: at most a couple of new samples arrive meanwhile.
  int dropped = before - after;
  return dropped >= burstWords - 3 * words() && dropped <= burstWords;
}

// The FIFO is usable if words pop one at a time (level falls while reading).
static int selfTestBefore = -1, selfTestAfter = -1;  // for the REGS diagnostic

static bool fifoSelfTest() {
  delay(50);
  int before, after;
  bool ok = fifoStatus(&before, nullptr, nullptr);
  selfTestBefore = ok ? before : -2;
  if (!ok || before < 60) return false;
  // Single-word pops (~150 us each) barely outpace arrivals with the gyro on
  // (6 words per sample), so allow for the words that arrive meanwhile.
  uint32_t t0 = micros();
  for (int i = 0; i < 24; i++) popWord();
  uint32_t dt = micros() - t0;
  if (!fifoStatus(&after, nullptr, nullptr)) return false;
  selfTestAfter = after;
  int arrived = (int)((uint64_t)dt * IMU_ODR_HZ * words() / 1000000ULL);
  return after <= before - 24 + arrived + words();
}

// Which triple in each FIFO sample is the accelerometer? The board is at
// rest-ish on the fan, so the accelerometer triple carries gravity (~1 g)
// while the gyro triple is near zero. The datasheet order is gyro first.
static void detectOrder() {
  if (!gyroOn || !useFifo) return;
  restartFifo();
  delay(60);  // > 40 samples
  int16_t a[MAX_BURST][3], g[MAX_BURST][3];
  bool saved = gyroFirst;
  gyroFirst = true;  // read raw: "a" = second triple, "g" = first triple
  float n1 = 0, n2 = 0;
  for (int k = 0; k < 4; k++) {
    int got = readSamples(a, g, MAX_BURST);
    for (int i = 0; i < got; i++) {
      n1 += sqrtf((float)g[i][0] * g[i][0] + (float)g[i][1] * g[i][1] + (float)g[i][2] * g[i][2]);
      n2 += sqrtf((float)a[i][0] * a[i][0] + (float)a[i][1] * a[i][1] + (float)a[i][2] * a[i][2]);
    }
  }
  if (n1 == 0 && n2 == 0) gyroFirst = saved;
  else gyroFirst = n2 >= n1;  // second triple is the big one -> accel second -> gyro first
}

static bool begin(int fsG) {
  Wire.begin();
  Wire.setClock(400000);
  whoAmI = i2c::read8(ADDR, WHO_AM_I);
  if (whoAmI != WHO_AM_I_DS33) return false;  // LSM6DS3TR-C boards need a new driver

  i2c::write8(ADDR, CTRL3_C, 0x01);  // SW_RESET
  delay(10);
  i2c::write8(ADDR, CTRL3_C, 0x44);  // BDU | IF_INC
  i2c::write8(ADDR, CTRL4_C, 0x80);  // XL_BW_SCAL_ODR: filter from BW_XL, not ODR

  uint8_t fsBits;
  switch (fsG) {
    case 2:  fsBits = 0b00; mgPerLsb = 0.061f; break;
    case 8:  fsBits = 0b11; mgPerLsb = 0.244f; break;
    case 16: fsBits = 0b01; mgPerLsb = 0.488f; break;
    default: fsBits = 0b10; mgPerLsb = 0.122f; break;  // 4 g
  }
  i2c::write8(ADDR, CTRL1_XL, (IMU_ODR_CODE << 4) | (fsBits << 2) | IMU_BW_CODE);
  // Gyro: same ODR, +-125 dps (FS_125) for the finest resolution.
  i2c::write8(ADDR, CTRL2_G, gyroOn ? ((IMU_ODR_CODE << 4) | 0x02) : 0x00);
  if (gyroOn) delay(100);  // gyro turn-on time

  // FIFO_CTRL3: DEC_FIFO_GYRO [5:3], DEC_FIFO_XL [2:0]; 001 = in FIFO, no decimation.
  i2c::write8(ADDR, FIFO_CTRL3, gyroOn ? 0x09 : 0x01);
  restartFifo();  // FIFO ODR = sensor ODR, continuous mode
  useFifo = fifoSelfTest();
  if (useFifo) {
    burstOk = burstSelfTest();
    detectOrder();
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
  int16_t a[MAX_BURST][3], g[MAX_BURST][3];
  while (micros() - t0 < 1000000UL) {
    for (int n = available(nullptr); n > 0;) {
      int got = readSamples(a, g, n);
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

// ---- LIS3MDL magnetometer ---------------------------------------------------
// The fan's BLDC rotor magnets and coil currents make a magnetic signature at
// the rotation / electrical frequency. No FIFO: the loop polls the data-ready
// flag every MAG_POLL_US. A missed sample sets ZYXOR, counted as an overrun.
namespace mag {

const uint8_t ADDR = 0x1C;
const uint8_t AUTO_INC = 0x80;  // multi-byte reads need the sub-address MSB set
static bool ok = false;
static int whoAmI = -1;
static float lsbPerGauss = 3421.0f;

static bool begin() {
  whoAmI = i2c::read8(ADDR, 0x0F);
  if (whoAmI != 0x3D) return false;
  uint8_t fs;
  switch (MAG_FS_GAUSS) {
    case 4:  fs = 0b00; lsbPerGauss = 6842.0f; break;
    case 12: fs = 0b10; lsbPerGauss = 2281.0f; break;
    case 16: fs = 0b11; lsbPerGauss = 1711.0f; break;
    default: fs = 0b01; lsbPerGauss = 3421.0f; break;  // 8 gauss
  }
  // CTRL_REG1: OM (X/Y operating mode) + FAST_ODR. With FAST_ODR the mode sets
  // the rate: LP 1000 Hz, MP 560 Hz, HP 300 Hz, UHP 155 Hz.
  uint8_t om = MAG_ODR_HZ >= 1000 ? 0b00 : MAG_ODR_HZ >= 560 ? 0b01 : MAG_ODR_HZ >= 300 ? 0b10 : 0b11;
  i2c::write8(ADDR, 0x20, (om << 5) | 0x02);
  i2c::write8(ADDR, 0x21, fs << 5);
  i2c::write8(ADDR, 0x22, 0x00);      // continuous conversion
  i2c::write8(ADDR, 0x23, om << 2);   // Z axis mode = X/Y mode
  i2c::write8(ADDR, 0x24, 0x40);      // BDU
  ok = true;
  return true;
}

// Returns true with a new sample in out; *overrun when one was missed.
static bool poll(int16_t out[3], bool* overrun) {
  uint8_t b[7];
  if (!i2c::readN(ADDR, 0x27 | AUTO_INC, b, 7)) return false;  // STATUS + OUT_X..Z
  *overrun = b[0] & 0x80;  // ZYXOR
  if (!(b[0] & 0x08)) return false;  // ZYXDA
  for (int k = 0; k < 3; k++) out[k] = (int16_t)(b[1 + 2 * k] | (b[2 + 2 * k] << 8));
  return true;
}

}  // namespace mag

// ---- BMP280 pressure (+ its own temperature) ------------------------------
// Normal mode, pressure x16 / temperature x2 oversampling, IIR x16,
// a new result every second. Integer compensation from the datasheet.
namespace baro {

const uint8_t ADDR = 0x77;
static bool ok = false;
static uint16_t T1, P1;
static int16_t T2, T3, P2, P3, P4, P5, P6, P7, P8, P9;

static bool begin() {
  if (i2c::read8(ADDR, 0xD0) != 0x58) return false;
  uint8_t c[24];
  if (!i2c::readN(ADDR, 0x88, c, 24)) return false;
  auto u16 = [&](int i) { return (uint16_t)(c[i] | (c[i + 1] << 8)); };
  T1 = u16(0); T2 = (int16_t)u16(2); T3 = (int16_t)u16(4);
  P1 = u16(6); P2 = (int16_t)u16(8); P3 = (int16_t)u16(10); P4 = (int16_t)u16(12);
  P5 = (int16_t)u16(14); P6 = (int16_t)u16(16); P7 = (int16_t)u16(18);
  P8 = (int16_t)u16(20); P9 = (int16_t)u16(22);
  i2c::write8(ADDR, 0xF5, (0b101 << 5) | (0b100 << 2));        // t_sb 1000 ms, IIR x16
  i2c::write8(ADDR, 0xF4, (0b010 << 5) | (0b101 << 2) | 0b11);  // T x2, P x16, normal
  ok = true;
  return true;
}

// Pressure in Pa x 100 and temperature in 0.01 C. False if not available.
static bool read(uint32_t& pressureCentiPa, int16_t& tempCentiC) {
  if (!ok) return false;
  uint8_t d[6];
  if (!i2c::readN(ADDR, 0xF7, d, 6)) return false;
  int32_t adcP = ((int32_t)d[0] << 12) | ((int32_t)d[1] << 4) | (d[2] >> 4);
  int32_t adcT = ((int32_t)d[3] << 12) | ((int32_t)d[4] << 4) | (d[5] >> 4);
  if (adcT == 0x80000) return false;  // no measurement yet
  int32_t v1 = ((((adcT >> 3) - ((int32_t)T1 << 1))) * (int32_t)T2) >> 11;
  int32_t v2 = (((((adcT >> 4) - (int32_t)T1) * ((adcT >> 4) - (int32_t)T1)) >> 12) * (int32_t)T3) >> 14;
  int32_t tFine = v1 + v2;
  tempCentiC = (int16_t)((tFine * 5 + 128) >> 8);
  int64_t a = (int64_t)tFine - 128000;
  int64_t b = a * a * (int64_t)P6;
  b += (a * (int64_t)P5) << 17;
  b += ((int64_t)P4) << 35;
  a = ((a * a * (int64_t)P3) >> 8) + ((a * (int64_t)P2) << 12);
  a = ((((int64_t)1) << 47) + a) * (int64_t)P1 >> 33;
  if (a == 0) return false;
  int64_t p = 1048576 - adcP;
  p = (((p << 31) - b) * 3125) / a;
  int64_t c1 = ((int64_t)P9 * (p >> 13) * (p >> 13)) >> 25;
  int64_t c2 = ((int64_t)P8 * p) >> 19;
  p = ((p + c1 + c2) >> 8) + (((int64_t)P7) << 4);  // Pa in Q24.8
  pressureCentiPa = (uint32_t)((p * 100) >> 8);
  return true;
}

}  // namespace baro

// ---- APDS9960 ambient light (clear, red, green, blue) ---------------------
// Context only (room lights on/off). Proximity and gesture are left off.
namespace light {

const uint8_t ADDR = 0x39;
static bool ok = false;

static bool begin() {
  if (i2c::read8(ADDR, 0x92) != 0xAB) return false;
  i2c::write8(ADDR, 0x81, 0xB6);  // ATIME: 72 cycles, ~200 ms integration
  i2c::write8(ADDR, 0x8F, 0x01);  // AGAIN 4x
  i2c::write8(ADDR, 0x80, 0x03);  // PON | AEN
  ok = true;
  return true;
}

static bool read(uint16_t crgb[4]) {
  if (!ok) return false;
  uint8_t d[8];
  if (!i2c::readN(ADDR, 0x94, d, 8)) return false;
  for (int k = 0; k < 4; k++) crgb[k] = d[2 * k] | (d[2 * k + 1] << 8);
  return true;
}

}  // namespace light

// ---- SHT3x / SHT4x temperature and humidity ------------------------------
// One measurement is triggered per read(); the next read (TH_PERIOD_MS later)
// fetches it, so nothing waits for the ~15 ms conversion. Uses Wire; the
// readings are CRC-checked.
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
