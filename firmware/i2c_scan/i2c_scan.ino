// I2C bring-up scan for the Adafruit Feather nRF52840 Sense.
// Lists every device on the main Wire bus and reads the ID register of the
// known onboard sensors, so the board revision (IMU part) can be identified.
// Repeats every 3 s, so the serial monitor can be opened at any time.

#include <Arduino.h>
#include <Wire.h>

static int read8(uint8_t addr, uint8_t reg) {
  Wire.beginTransmission(addr);
  Wire.write(reg);
  if (Wire.endTransmission(false) != 0) return -1;
  if (Wire.requestFrom(addr, (uint8_t)1) != 1) return -1;
  return Wire.read();
}

static void describe(uint8_t addr) {
  int id;
  switch (addr) {
    case 0x6A:
    case 0x6B:
      id = read8(addr, 0x0F);
      Serial.print(F("  IMU WHO_AM_I=0x")); Serial.print(id, HEX);
      if (id == 0x69)      Serial.print(F(" -> LSM6DS33 (original Feather Sense)"));
      else if (id == 0x6A) Serial.print(F(" -> LSM6DS3TR-C (newer Feather Sense)"));
      else if (id == 0x6C) Serial.print(F(" -> LSM6DSOX"));
      else                 Serial.print(F(" -> unknown IMU"));
      break;
    case 0x1C:
    case 0x1E:
      id = read8(addr, 0x0F);
      Serial.print(F("  magnetometer WHO_AM_I=0x")); Serial.print(id, HEX);
      if (id == 0x3D) Serial.print(F(" -> LIS3MDL"));
      break;
    case 0x39:
      id = read8(addr, 0x92);
      Serial.print(F("  ID=0x")); Serial.print(id, HEX);
      if (id == 0xAB) Serial.print(F(" -> APDS9960 (proximity/light/gesture)"));
      break;
    case 0x76:
    case 0x77:
      id = read8(addr, 0xD0);
      Serial.print(F("  chip_id=0x")); Serial.print(id, HEX);
      if (id == 0x58)      Serial.print(F(" -> BMP280 (pressure)"));
      else if (id == 0x60) Serial.print(F(" -> BME280"));
      break;
    case 0x44:
    case 0x45:
      Serial.print(F("  -> SHT3x/SHT4x temperature/humidity"));
      break;
    default:
      break;
  }
}

void setup() {
  Serial.begin(115200);
  uint32_t t0 = millis();
  while (!Serial && millis() - t0 < 5000) delay(10);
  Wire.begin();
  Wire.setClock(100000);
}

void loop() {
  Serial.println(F("--- i2c_scan (Wire) ---"));
  int found = 0;
  for (uint8_t addr = 1; addr < 127; addr++) {
    Wire.beginTransmission(addr);
    if (Wire.endTransmission() == 0) {
      Serial.print(F("0x"));
      if (addr < 16) Serial.print('0');
      Serial.print(addr, HEX);
      describe(addr);
      Serial.println();
      found++;
    }
  }
  Serial.print(F("devices found: ")); Serial.println(found);
  delay(3000);
}
