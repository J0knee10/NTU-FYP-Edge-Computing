#pragma once
#include <Arduino.h>

// Binary framing over USB serial. All integers little-endian.
//
//   0xA5 0x5A | type u8 | seq u8 | len u16 | payload[len] | crc16 u16
//
// crc16 is CRC-16/CCITT-FALSE (poly 0x1021, init 0xFFFF) over type..payload.
// Must stay in sync with host/fanlog/protocol.py.

enum FrameType : uint8_t {
  FT_IMU    = 1,  // ImuHeader + n * int16[3] raw accelerometer counts
  FT_AUDIO  = 2,  // AudioHeader + n * int16 PCM
  FT_STATUS = 3,  // StatusPayload
  FT_INFO   = 4,  // ASCII key=value pairs describing firmware and config
  FT_TEXT   = 5,  // ASCII command acknowledgements and errors
  FT_GYRO   = 6,  // ImuHeader + n * int16[3] raw gyro counts (same indices as FT_IMU)
  FT_MAG    = 7,  // ImuHeader + n * int16[3] raw magnetometer counts (own index)
  FT_ENV    = 8,  // EnvPayload: pressure and ambient light, ~1 Hz
};

struct __attribute__((packed)) ImuHeader {
  uint32_t t_us;         // micros() when the frame was sent
  uint32_t first_index;  // sample index of the first sample since START
  uint16_t n;
};

struct __attribute__((packed)) AudioHeader {
  uint32_t t_us;
  uint32_t first_index;
  uint16_t n;
};

struct __attribute__((packed)) StatusPayload {
  uint32_t t_us;
  uint32_t imu_samples;      // since START
  uint32_t imu_overruns;     // FIFO overrun events since START
  uint32_t audio_samples;    // since START
  uint32_t audio_dropped;    // samples dropped (ring full) since START
  uint32_t tach_pulses;      // since boot
  uint32_t tach_period_us;   // last tach period (1 us clock since 0.3.1), 0 if none yet
  uint16_t pwm_permille;     // commanded duty, 1000 = full speed
  int16_t  temp_centi_c;     // SHT3x/SHT4x, INT16_MIN if unavailable
  uint16_t humidity_centi;   // SHT3x/SHT4x, 0xFFFF if unavailable
  uint8_t  flags;            // see STATUS_* below
  uint8_t  reserved;
  uint32_t mag_samples;      // since START
  uint32_t mag_overruns;     // magnetometer samples missed (ZYXOR) since START
  // logger >= 0.3.1. Speed between two STATUS frames = d(tach_pulses) / d(tach_edge_us).
  uint32_t tach_edge_us;     // 1 MHz tach clock at the last accepted edge (wraps after 71 min)
  uint32_t tach_rejected;    // tach edges dropped by the glitch filter, since boot
};

struct __attribute__((packed)) EnvPayload {
  uint32_t t_us;
  uint32_t pressure_centi_pa;  // BMP280, 0 if unavailable
  int16_t  baro_temp_centi_c;  // BMP280 die temperature, INT16_MIN if unavailable
  uint16_t light_clear;        // APDS9960 raw counts, 0xFFFF if unavailable
  uint16_t light_red;
  uint16_t light_green;
  uint16_t light_blue;
  uint8_t  flags;              // bit 0: baro ok, bit 1: light ok
  uint8_t  reserved;
};

enum : uint8_t {
  STATUS_STREAMING = 1 << 0,
  STATUS_AUDIO_ON  = 1 << 1,
  STATUS_PWM_SET   = 1 << 2,
  STATUS_TH_OK     = 1 << 3,  // temperature/humidity sensor found
  STATUS_IMU_FIFO  = 1 << 4,
};

static inline uint16_t crc16Update(uint16_t crc, const uint8_t* data, size_t n) {
  for (size_t i = 0; i < n; i++) {
    crc ^= (uint16_t)data[i] << 8;
    for (int b = 0; b < 8; b++) crc = (crc & 0x8000) ? (crc << 1) ^ 0x1021 : crc << 1;
  }
  return crc;
}

static uint8_t g_frameSeq = 0;

static inline void sendFrame(uint8_t type, const void* payload, uint16_t len) {
  uint8_t hdr[6] = {0xA5, 0x5A, type, g_frameSeq++, (uint8_t)(len & 0xFF), (uint8_t)(len >> 8)};
  uint16_t crc = crc16Update(0xFFFF, hdr + 2, 4);
  crc = crc16Update(crc, (const uint8_t*)payload, len);
  uint8_t tail[2] = {(uint8_t)(crc & 0xFF), (uint8_t)(crc >> 8)};
  Serial.write(hdr, sizeof(hdr));
  Serial.write((const uint8_t*)payload, len);
  Serial.write(tail, sizeof(tail));
}

static inline void sendText(uint8_t type, const char* s) {
  sendFrame(type, s, (uint16_t)strlen(s));
}
