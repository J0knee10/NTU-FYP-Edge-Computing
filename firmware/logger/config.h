#pragma once

#define FW_VERSION "logger-0.3.1"

// Board: Adafruit Feather nRF52840 Sense (original revision, LSM6DS33 IMU).
// FQBN adafruit:nrf52:feather52840sense

// ---- Fan (12 V PC fan) --------------------------------------------------
// Set a pin to -1 if that wire is not connected (e.g. 3-pin fan: no PWM).
// Use header pins only: D3 is not connected on this board, D2 is an NFC pad,
// D4/D13 drive the LEDs and D7/D8 are the button and NeoPixel.
#define PIN_FAN_PWM        5     // fan pin 4 (PWM, usually blue)
#define PIN_FAN_TACH       6     // fan pin 3 (tach, usually green/yellow)
#define FAN_PWM_INVERT     0     // 1 when driving PWM through an NPN/MOSFET stage
#define FAN_PWM_PERIOD_US  40    // 25 kHz, per the 4-pin fan spec
#define TACH_MIN_PERIOD_US 500   // ignore edges closer than this (PWM noise)

// ---- IMU (LSM6DS33 accelerometer + gyroscope) ---------------------------
// ODR codes: 0b0110 = 416 Hz, 0b0111 = 833 Hz, 0b1000 = 1.66 kHz.
// Anti-alias filter: 0b00 = 400 Hz, 0b01 = 200 Hz, 0b10 = 100 Hz, 0b11 = 50 Hz.
// 400 Hz is the widest filter, so 833 Hz already captures the full bandwidth.
#define IMU_ODR_CODE       0b0111
#define IMU_ODR_HZ         833
#define IMU_BW_CODE        0b00
#define IMU_BW_HZ          400
#define IMU_FS_G           4     // full scale: 2, 4, 8 or 16 g
#define IMU_GYRO           1     // 1: gyro on at the same ODR, interleaved in the FIFO
#define IMU_BATCH          32    // samples per IMU (and GYRO) frame
#define IMU_POLL_US        4000  // FIFO read interval (FIFO holds ~0.8 s with gyro on)

// ---- Magnetometer (LIS3MDL, no FIFO: polled) ----------------------------
#define MAG_ENABLE         1
#define MAG_ODR_HZ         300   // high-performance mode with FAST_ODR
#define MAG_FS_GAUSS       8     // 4, 8, 12 or 16 gauss
#define MAG_BATCH          32
#define MAG_POLL_US        1000

// ---- Microphone (PDM) ---------------------------------------------------
#define AUDIO_RATE         16000
#define AUDIO_GAIN         20
#define AUDIO_CHUNK        256   // samples per audio frame
#define AUDIO_RING         8192  // samples buffered between ISR and loop

// ---- Housekeeping -------------------------------------------------------
#define STATUS_PERIOD_MS   250
#define TH_PERIOD_MS       1000  // temperature / humidity (SHT3x)
#define ENV_PERIOD_MS      1000  // pressure (BMP280) and ambient light (APDS9960)
