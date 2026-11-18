// Step 0 smoke test: is on-device training of the default anomaly model
// cheap enough on the nRF52840?
//
// Runs a 48-16-8-16-48 MLP autoencoder (ReLU hidden layers, linear output,
// MSE loss, plain SGD) with statically allocated weights, and reports:
//   - model memory (weights + cached activations)
//   - forward-only time and full train-step time per window
//   - loss on a fixed input before/after training (should fall)
//
// Open the serial monitor; the benchmark runs on connect and on any key.
// This is a feasibility check, not the real engine (that is step 5).

#include <Arduino.h>
#ifdef USE_TINYUSB
#include <Adafruit_TinyUSB.h>  // Adafruit nRF52 core: provides USB Serial
#endif

template <int IN, int OUT>
struct Dense {
  float W[OUT][IN];
  float b[OUT];
  float x[IN];   // input cached for backward
  float y[OUT];  // output (post-activation) cached for backward

  void init(uint32_t& seed) {
    float limit = sqrtf(6.0f / IN);  // He-uniform
    for (int o = 0; o < OUT; o++) {
      for (int i = 0; i < IN; i++) W[o][i] = limit * (2.0f * nextUniform(seed) - 1.0f);
      b[o] = 0.0f;
    }
  }

  const float* forward(const float* in, bool relu) {
    memcpy(x, in, sizeof(x));
    for (int o = 0; o < OUT; o++) {
      float s = b[o];
      for (int i = 0; i < IN; i++) s += W[o][i] * x[i];
      y[o] = (relu && s < 0.0f) ? 0.0f : s;
    }
    return y;
  }

  // dy: gradient w.r.t. this layer's output; overwritten. dx may be null.
  void backwardSgd(float* dy, float* dx, bool relu, float lr) {
    if (relu)
      for (int o = 0; o < OUT; o++)
        if (y[o] <= 0.0f) dy[o] = 0.0f;
    if (dx) memset(dx, 0, IN * sizeof(float));
    for (int o = 0; o < OUT; o++) {
      float g = dy[o];
      for (int i = 0; i < IN; i++) {
        if (dx) dx[i] += W[o][i] * g;  // uses W before its update
        W[o][i] -= lr * g * x[i];
      }
      b[o] -= lr * g;
    }
  }

  static float nextUniform(uint32_t& s) {
    s = s * 1664525u + 1013904223u;
    return (s >> 8) * (1.0f / 16777216.0f);
  }
};

constexpr int D = 48;
static Dense<48, 16> l0;
static Dense<16, 8> l1;
static Dense<8, 16> l2;
static Dense<16, 48> l3;
static float g48[48], g16a[16], g8[8], g16b[16];

static const float* forward(const float* x) {
  return l3.forward(l2.forward(l1.forward(l0.forward(x, true), true), true), false);
}

static float loss(const float* x) {
  const float* out = forward(x);
  float s = 0;
  for (int i = 0; i < D; i++) s += (out[i] - x[i]) * (out[i] - x[i]);
  return s / D;
}

static float trainStep(const float* x, float lr) {
  const float* out = forward(x);
  float s = 0;
  for (int i = 0; i < D; i++) {
    float e = out[i] - x[i];
    s += e * e;
    g48[i] = 2.0f * e / D;
  }
  l3.backwardSgd(g48, g16b, false, lr);
  l2.backwardSgd(g16b, g8, true, lr);
  l1.backwardSgd(g8, g16a, true, lr);
  l0.backwardSgd(g16a, nullptr, true, lr);
  return s / D;
}

static void runBenchmark() {
  uint32_t seed = 12345;
  l0.init(seed); l1.init(seed); l2.init(seed); l3.init(seed);

  float x[D];
  for (int i = 0; i < D; i++) x[i] = Dense<1, 1>::nextUniform(seed);

  const int N = 1000;
  uint32_t t0 = micros();
  volatile float sink = 0;
  for (int k = 0; k < N; k++) sink += forward(x)[0];
  uint32_t fwdUs = micros() - t0;

  float lossBefore = loss(x);
  t0 = micros();
  for (int k = 0; k < N; k++) trainStep(x, 0.01f);
  uint32_t trainUs = micros() - t0;
  float lossAfter = loss(x);

  size_t params = 48 * 16 + 16 + 16 * 8 + 8 + 8 * 16 + 16 + 16 * 48 + 48;
  size_t modelBytes = sizeof(l0) + sizeof(l1) + sizeof(l2) + sizeof(l3);
  size_t gradBytes = sizeof(g48) + sizeof(g16a) + sizeof(g8) + sizeof(g16b);

  Serial.println(F("--- smoke_train: 48-16-8-16-48 MLP autoencoder, float32, SGD ---"));
  Serial.print(F("parameters:            ")); Serial.println(params);
  Serial.print(F("model RAM (W,b,x,y):   ")); Serial.print(modelBytes); Serial.println(F(" bytes"));
  Serial.print(F("gradient scratch RAM:  ")); Serial.print(gradBytes); Serial.println(F(" bytes"));
  Serial.print(F("forward per window:    ")); Serial.print(fwdUs / (float)N, 1); Serial.println(F(" us"));
  Serial.print(F("train step per window: ")); Serial.print(trainUs / (float)N, 1); Serial.println(F(" us"));
  Serial.print(F("loss before / after:   ")); Serial.print(lossBefore, 6);
  Serial.print(F(" / ")); Serial.println(lossAfter, 6);
  Serial.println(lossAfter < lossBefore ? F("result: OK (loss decreased)") : F("result: FAIL (loss did not decrease)"));
  Serial.println(F("press any key to re-run"));
}

void setup() {
  Serial.begin(115200);
  while (!Serial) {}
  runBenchmark();
}

void loop() {
  if (Serial.available()) {
    while (Serial.available()) Serial.read();
    runBenchmark();
  }
}
