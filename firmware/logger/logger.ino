// Step 0 data logger for the Adafruit Feather nRF52840 Sense (LSM6DS33 revision).
//
// Streams accelerometer + gyroscope (833 Hz), magnetometer (300 Hz), optional
// microphone (16 kHz), temperature/humidity, pressure, ambient light, fan tach
// and commanded PWM to the host over USB serial using the framing in
// protocol.h. Controlled by ASCII line commands from the host:
//
//   INFO          send an INFO frame (firmware, sensors, measured IMU rate)
//   START         reset counters and start streaming IMU/gyro/mag (and audio if on)
//   STOP          stop streaming
//   PWM <0-1000>  set fan duty in permille
//   AUDIO <0|1>   enable / disable microphone streaming
//   PING          reply "PONG"
//
// STATUS frames (every STATUS_PERIOD_MS) and ENV frames (every ENV_PERIOD_MS)
// are sent whether or not streaming.

#include <Adafruit_TinyUSB.h>  // USB Serial on the Adafruit nRF52 core
#include <PDM.h>
#include "config.h"
#include "protocol.h"
#include "sensors.h"
#include "fan.h"

static bool imuOk = false;
static float imuRateHz = 0;
static bool streaming = false;
static bool audioOn = false;

static uint32_t imuIndex = 0;
static uint32_t imuOverruns = 0;
static uint32_t audioIndex = 0;
static uint32_t magIndex = 0;
static uint32_t magOverruns = 0;

static float tempC = NAN;
static float humidity = NAN;

// ---- IMU + gyro batching (same sample indices) ----------------------------
struct __attribute__((packed)) TripleFrame {
  ImuHeader hdr;
  int16_t xyz[IMU_BATCH][3];
};
static TripleFrame imuFrame, gyroFrame;
static uint16_t imuFill = 0;
static uint32_t imuBatchStart = 0;

static void flushImuBatch() {
  if (imuFill == 0) return;
  uint32_t now = micros();
  imuFrame.hdr.t_us = gyroFrame.hdr.t_us = now;
  imuFrame.hdr.first_index = gyroFrame.hdr.first_index = imuBatchStart;
  imuFrame.hdr.n = gyroFrame.hdr.n = imuFill;
  sendFrame(FT_IMU, &imuFrame, sizeof(ImuHeader) + imuFill * 6);
  if (imu::gyroOn) sendFrame(FT_GYRO, &gyroFrame, sizeof(ImuHeader) + imuFill * 6);
  imuFill = 0;
}

// ---- Magnetometer batching --------------------------------------------------
static struct __attribute__((packed)) {
  ImuHeader hdr;
  int16_t xyz[MAG_BATCH][3];
} magFrame;
static uint16_t magFill = 0;
static uint32_t magBatchStart = 0;
static uint32_t lastMagPoll = 0;

static void flushMagBatch() {
  if (magFill == 0) return;
  magFrame.hdr.t_us = micros();
  magFrame.hdr.first_index = magBatchStart;
  magFrame.hdr.n = magFill;
  sendFrame(FT_MAG, &magFrame, sizeof(ImuHeader) + magFill * 6);
  magFill = 0;
}

static void pollMag() {
  if (!mag::ok || !streaming) return;
  uint32_t now = micros();
  if (now - lastMagPoll < MAG_POLL_US) return;
  lastMagPoll = now;
  int16_t s[3];
  bool overrun = false;
  if (!mag::poll(s, &overrun)) return;
  if (overrun) magOverruns++;
  if (magFill == 0) magBatchStart = magIndex;
  memcpy(magFrame.xyz[magFill], s, sizeof(s));
  magFill++;
  magIndex++;
  if (magFill == MAG_BATCH) flushMagBatch();
}

static void pollImu() {
  static uint32_t lastPoll = 0;
  uint32_t now = micros();
  if (now - lastPoll < IMU_POLL_US) return;
  lastPoll = now;
  bool overrun = false;
  int n = imu::available(&overrun);
  if (overrun) imuOverruns++;
  int16_t acc[imu::MAX_BURST][3], gyr[imu::MAX_BURST][3];  // aligned; frames are packed
  while (n > 0) {
    if (imuFill == 0) imuBatchStart = imuIndex;
    int want = min(min(n, IMU_BATCH - (int)imuFill), imu::MAX_BURST);
    int got = imu::readSamples(acc, gyr, want);
    if (got == 0) break;
    memcpy(imuFrame.xyz[imuFill], acc, got * sizeof(acc[0]));
    memcpy(gyroFrame.xyz[imuFill], gyr, got * sizeof(gyr[0]));
    imuFill += got;
    imuIndex += got;
    n -= got;
    if (imuFill == IMU_BATCH) flushImuBatch();
    pollMag();  // the magnetometer has no FIFO: keep polling it between bursts
  }
}

// ---- Audio ring buffer (filled from the PDM callback) -------------------
static int16_t audioRing[AUDIO_RING];
static volatile uint32_t audioHead = 0;  // written by ISR
static volatile uint32_t audioTail = 0;  // read by loop
static volatile uint32_t audioDropped = 0;
static int16_t pdmScratch[512];

static void onPdmData() {
  int bytes = PDM.available();
  if (bytes > (int)sizeof(pdmScratch)) bytes = sizeof(pdmScratch);
  PDM.read(pdmScratch, bytes);
  int n = bytes / 2;
  for (int i = 0; i < n; i++) {
    if (audioHead - audioTail >= AUDIO_RING) {
      audioDropped += n - i;
      break;
    }
    audioRing[audioHead % AUDIO_RING] = pdmScratch[i];
    audioHead++;
  }
}

static struct __attribute__((packed)) {
  AudioHeader hdr;
  int16_t pcm[AUDIO_CHUNK];
} audioFrame;

static void pollAudio() {
  while (audioHead - audioTail >= AUDIO_CHUNK) {
    for (int i = 0; i < AUDIO_CHUNK; i++) audioFrame.pcm[i] = audioRing[(audioTail + i) % AUDIO_RING];
    audioTail += AUDIO_CHUNK;
    audioFrame.hdr.t_us = micros();
    audioFrame.hdr.first_index = audioIndex;
    audioFrame.hdr.n = AUDIO_CHUNK;
    audioIndex += AUDIO_CHUNK;
    sendFrame(FT_AUDIO, &audioFrame, sizeof(audioFrame));
    pollMag();
  }
}

static bool setAudio(bool on) {
  if (on == audioOn) return true;
  if (on) {
    PDM.onReceive(onPdmData);
    if (!PDM.begin(1, AUDIO_RATE)) return false;
    PDM.setGain(AUDIO_GAIN);
  } else {
    PDM.end();
  }
  audioOn = on;
  return true;
}

// ---- Status, environment and info -----------------------------------------
static void sendStatus() {
  StatusPayload s;
  s.t_us = micros();
  s.imu_samples = imuIndex;
  s.imu_overruns = imuOverruns;
  s.audio_samples = audioIndex;
  s.audio_dropped = audioDropped;
  noInterrupts();
  s.tach_pulses = fan::tachPulses;
  s.tach_period_us = fan::tachPeriodUs;
  interrupts();
  s.pwm_permille = fan::dutyPermille;
  s.temp_centi_c = isnan(tempC) ? INT16_MIN : (int16_t)lroundf(tempC * 100);
  s.humidity_centi = isnan(humidity) ? 0xFFFF : (uint16_t)lroundf(humidity * 100);
  s.flags = (streaming ? STATUS_STREAMING : 0) | (audioOn ? STATUS_AUDIO_ON : 0) |
            (fan::pwmSet ? STATUS_PWM_SET : 0) | (th::ok ? STATUS_TH_OK : 0) |
            (imu::useFifo ? STATUS_IMU_FIFO : 0);
  s.reserved = 0;
  s.mag_samples = magIndex;
  s.mag_overruns = magOverruns;
  sendFrame(FT_STATUS, &s, sizeof(s));
}

static void sendEnv() {
  EnvPayload e;
  e.t_us = micros();
  e.flags = 0;
  uint32_t p;
  int16_t bt;
  if (baro::read(p, bt)) {
    e.flags |= 1;
    e.pressure_centi_pa = p;
    e.baro_temp_centi_c = bt;
  } else {
    e.pressure_centi_pa = 0;
    e.baro_temp_centi_c = INT16_MIN;
  }
  uint16_t crgb[4];
  if (light::read(crgb)) {
    e.flags |= 2;
  } else {
    crgb[0] = crgb[1] = crgb[2] = crgb[3] = 0xFFFF;
  }
  e.light_clear = crgb[0];
  e.light_red = crgb[1];
  e.light_green = crgb[2];
  e.light_blue = crgb[3];
  e.reserved = 0;
  sendFrame(FT_ENV, &e, sizeof(e));
}

static void sendInfo() {
  char buf[720];
  snprintf(buf, sizeof(buf),
           "fw=%s board=feather_nrf52840_sense imu=lsm6ds33 imu_whoami=0x%02X imu_ok=%d "
           "imu_fifo=%d imu_burst=%d imu_rate_hz=%.2f imu_odr_hz=%d imu_bw_hz=%d imu_fs_g=%d "
           "imu_mg_per_lsb=%.3f imu_batch=%d gyro=%d gyro_first=%d gyro_fs_dps=125 "
           "gyro_mdps_per_lsb=%.3f mag=lis3mdl mag_ok=%d mag_odr_hz=%d mag_fs_gauss=%d "
           "mag_lsb_per_gauss=%.0f baro=bmp280 baro_ok=%d light=apds9960 light_ok=%d "
           "th=%s th_ok=%d audio_rate=%d audio_gain=%d pwm_pin=%d tach_pin=%d pwm_invert=%d "
           "pwm_period_us=%d status_period_ms=%d env_period_ms=%d",
           FW_VERSION, imu::whoAmI & 0xFF, imuOk, imu::useFifo, imu::burstOk, imuRateHz,
           IMU_ODR_HZ, IMU_BW_HZ, IMU_FS_G, imu::mgPerLsb, IMU_BATCH, imu::gyroOn,
           imu::gyroFirst, imu::mdpsPerLsb, mag::ok, MAG_ODR_HZ, MAG_FS_GAUSS,
           mag::lsbPerGauss, baro::ok, light::ok, th::name(), th::ok, AUDIO_RATE, AUDIO_GAIN,
           PIN_FAN_PWM, PIN_FAN_TACH, FAN_PWM_INVERT, FAN_PWM_PERIOD_US, STATUS_PERIOD_MS,
           ENV_PERIOD_MS);
  sendText(FT_INFO, buf);
}

// ---- Commands -----------------------------------------------------------
static void startStreaming() {
  imu::flush();
  imuIndex = 0;
  imuOverruns = 0;
  imuFill = 0;
  magIndex = 0;
  magOverruns = 0;
  magFill = 0;
  noInterrupts();
  audioTail = audioHead;
  audioDropped = 0;
  interrupts();
  audioIndex = 0;
  streaming = true;
}

static void handleCommand(char* line) {
  char reply[64];
  int value;
  if (strcmp(line, "INFO") == 0) {
    sendInfo();
  } else if (strcmp(line, "PING") == 0) {
    sendText(FT_TEXT, "PONG");
  } else if (strcmp(line, "REGS") == 0) {
    // Diagnostic: IMU configuration and FIFO state, as hex register values.
    uint8_t c[8], f[4];
    i2c::readN(imu::ADDR, 0x10, c, 8);  // CTRL1_XL .. CTRL8_XL
    i2c::readN(imu::ADDR, imu::FIFO_STATUS1, f, 4);
    char buf[200];
    snprintf(buf, sizeof(buf),
             "REGS ctrl1_xl=%02X ctrl2_g=%02X ctrl3_c=%02X ctrl4_c=%02X ctrl6_c=%02X ctrl7_g=%02X "
             "fifo_ctrl3=%02X fifo_ctrl5=%02X fifo_status=%02X %02X %02X %02X selftest=%d/%d",
             c[0], c[1], c[2], c[3], c[5], c[6], i2c::read8(imu::ADDR, imu::FIFO_CTRL3),
             i2c::read8(imu::ADDR, imu::FIFO_CTRL5), f[0], f[1], f[2], f[3],
             imu::selfTestBefore, imu::selfTestAfter);
    sendText(FT_TEXT, buf);
  } else if (strcmp(line, "START") == 0) {
    startStreaming();
    sendText(FT_TEXT, imuOk ? "OK START" : "ERR START imu not found");
  } else if (strcmp(line, "STOP") == 0) {
    flushImuBatch();
    flushMagBatch();
    streaming = false;
    sendText(FT_TEXT, "OK STOP");
  } else if (sscanf(line, "PWM %d", &value) == 1) {
    bool ok = fan::setDuty(value);
    snprintf(reply, sizeof(reply), ok ? "OK PWM %d" : "ERR PWM no pwm pin", fan::dutyPermille);
    sendText(FT_TEXT, reply);
  } else if (sscanf(line, "AUDIO %d", &value) == 1) {
    bool ok = setAudio(value != 0);
    if (ok && streaming && audioOn) {
      noInterrupts();
      audioTail = audioHead;
      interrupts();
    }
    snprintf(reply, sizeof(reply), ok ? "OK AUDIO %d" : "ERR AUDIO pdm begin failed", audioOn);
    sendText(FT_TEXT, reply);
  } else {
    snprintf(reply, sizeof(reply), "ERR unknown command: %.40s", line);
    sendText(FT_TEXT, reply);
  }
}

static void pollSerial() {
  static char line[64];
  static uint8_t len = 0;
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n' || c == '\r') {
      if (len > 0) {
        line[len] = '\0';
        handleCommand(line);
        len = 0;
      }
    } else if (len < sizeof(line) - 1) {
      line[len++] = c;
    }
  }
}

// ---- Main ---------------------------------------------------------------
void setup() {
  Serial.begin(115200);
  pinMode(LED_BUILTIN, OUTPUT);

  imuOk = imu::begin(IMU_FS_G);
  if (imuOk) imuRateHz = imu::measureRateHz();
#if MAG_ENABLE
  mag::begin();
#endif
  baro::begin();
  light::begin();
  th::begin();
  fan::begin();
}

void loop() {
  static uint32_t lastStatus = 0;
  static uint32_t lastTh = 0;
  static uint32_t lastEnv = 0;
  uint32_t now = millis();

  pollSerial();

  if (streaming && imuOk) pollImu();
  pollMag();
  if (streaming && audioOn) pollAudio();

  if (now - lastTh >= TH_PERIOD_MS) {
    lastTh = now;
    th::read(tempC, humidity);
  }
  if (now - lastEnv >= ENV_PERIOD_MS) {
    lastEnv = now;
    sendEnv();
  }
  if (now - lastStatus >= STATUS_PERIOD_MS) {
    lastStatus = now;
    sendStatus();
    digitalWrite(LED_BUILTIN, streaming ? !digitalRead(LED_BUILTIN) : LOW);
  }
}
