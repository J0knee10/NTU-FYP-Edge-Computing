// Step 0 data logger for the Adafruit Feather nRF52840 Sense (LSM6DS33 revision).
//
// Streams accelerometer (833 Hz), optional microphone (16 kHz), temperature,
// fan tach and commanded PWM to the host over USB serial using the framing in
// protocol.h. Controlled by ASCII line commands from the host:
//
//   INFO          send an INFO frame (firmware, sensors, measured IMU rate)
//   START         reset counters and start streaming IMU (and audio if on)
//   STOP          stop streaming
//   PWM <0-1000>  set fan duty in permille
//   AUDIO <0|1>   enable / disable microphone streaming
//   PING          reply "PONG"
//
// STATUS frames are sent every STATUS_PERIOD_MS whether or not streaming.

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

static float tempC = NAN;
static float humidity = NAN;

// ---- IMU batching -------------------------------------------------------
static struct __attribute__((packed)) {
  ImuHeader hdr;
  int16_t xyz[IMU_BATCH][3];
} imuFrame;
static uint16_t imuFill = 0;
static uint32_t imuBatchStart = 0;

static void flushImuBatch() {
  if (imuFill == 0) return;
  imuFrame.hdr.t_us = micros();
  imuFrame.hdr.first_index = imuBatchStart;
  imuFrame.hdr.n = imuFill;
  sendFrame(FT_IMU, &imuFrame, sizeof(ImuHeader) + imuFill * 6);
  imuFill = 0;
}

static void pollImu() {
  bool overrun = false;
  int n = imu::available(&overrun);
  if (overrun) imuOverruns++;
  int16_t buf[imu::MAX_BURST][3];  // aligned; imuFrame is packed
  while (n > 0) {
    if (imuFill == 0) imuBatchStart = imuIndex;
    int want = min(min(n, IMU_BATCH - (int)imuFill), imu::MAX_BURST);
    int got = imu::readSamples(buf, want);
    if (got == 0) break;
    memcpy(imuFrame.xyz[imuFill], buf, got * sizeof(buf[0]));
    imuFill += got;
    imuIndex += got;
    n -= got;
    if (imuFill == IMU_BATCH) flushImuBatch();
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

// ---- Status and info ----------------------------------------------------
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
  sendFrame(FT_STATUS, &s, sizeof(s));
}

static void sendInfo() {
  char buf[400];
  snprintf(buf, sizeof(buf),
           "fw=%s board=feather_nrf52840_sense imu=lsm6ds33 imu_whoami=0x%02X imu_ok=%d "
           "imu_fifo=%d imu_burst=%d imu_rate_hz=%.2f imu_odr_hz=%d imu_bw_hz=%d imu_fs_g=%d "
           "imu_mg_per_lsb=%.3f imu_batch=%d th=%s th_ok=%d audio_rate=%d audio_gain=%d "
           "pwm_pin=%d tach_pin=%d pwm_invert=%d pwm_period_us=%d status_period_ms=%d",
           FW_VERSION, imu::whoAmI & 0xFF, imuOk, imu::useFifo, imu::burstOk, imuRateHz,
           IMU_ODR_HZ, IMU_BW_HZ, IMU_FS_G, imu::mgPerLsb, IMU_BATCH, th::name(), th::ok,
           AUDIO_RATE, AUDIO_GAIN, PIN_FAN_PWM, PIN_FAN_TACH, FAN_PWM_INVERT,
           FAN_PWM_PERIOD_US, STATUS_PERIOD_MS);
  sendText(FT_INFO, buf);
}

// ---- Commands -----------------------------------------------------------
static void startStreaming() {
  imu::flush();
  imuIndex = 0;
  imuOverruns = 0;
  imuFill = 0;
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
  } else if (strcmp(line, "START") == 0) {
    startStreaming();
    sendText(FT_TEXT, imuOk ? "OK START" : "ERR START imu not found");
  } else if (strcmp(line, "STOP") == 0) {
    flushImuBatch();
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
  th::begin();
  fan::begin();
}

void loop() {
  static uint32_t lastStatus = 0;
  static uint32_t lastTh = 0;
  uint32_t now = millis();

  pollSerial();

  if (streaming && imuOk) pollImu();
  if (streaming && audioOn) pollAudio();

  if (now - lastTh >= TH_PERIOD_MS) {
    lastTh = now;
    th::read(tempC, humidity);
  }
  if (now - lastStatus >= STATUS_PERIOD_MS) {
    lastStatus = now;
    sendStatus();
    digitalWrite(LED_BUILTIN, streaming ? !digitalRead(LED_BUILTIN) : LOW);
  }
}
