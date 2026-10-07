#pragma once

#define FW_VERSION "logger-0.1.0"

// ---- Fan (12 V PC fan) --------------------------------------------------
// Set a pin to -1 if that wire is not connected (e.g. 3-pin fan: no PWM).
#define PIN_FAN_PWM        3     // fan pin 4 (PWM, usually blue)
#define PIN_FAN_TACH       2     // fan pin 3 (tach, usually green/yellow)
#define FAN_PWM_INVERT     0     // 1 when driving PWM through an NPN/MOSFET stage
#define FAN_PWM_PERIOD_US  40    // 25 kHz, per the 4-pin fan spec
#define TACH_MIN_PERIOD_US 500   // ignore edges closer than this (PWM noise)

// ---- IMU (LSM9DS1 accelerometer, accel-only mode at 952 Hz) -------------
#define IMU_FS_G           4     // full scale: 2, 4, 8 or 16 g
#define IMU_BATCH          32    // samples per IMU frame

// ---- Microphone (PDM) ---------------------------------------------------
#define AUDIO_RATE         16000
#define AUDIO_GAIN         20
#define AUDIO_CHUNK        256   // samples per audio frame
#define AUDIO_RING         8192  // samples buffered between ISR and loop

// ---- Housekeeping -------------------------------------------------------
#define STATUS_PERIOD_MS   250
#define HTS_PERIOD_MS      1000
