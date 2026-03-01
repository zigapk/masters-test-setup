const int outputPin = 7;

void setup() {
  // Configure the Uno pin to send a signal
  pinMode(outputPin, OUTPUT);

  // Seed the random generator by reading an unconnected analog pin.
  randomSeed(analogRead(0));
}

void loop() {
  // Set high (simulating estop released)
  digitalWrite(outputPin, LOW);

  // Wait anywhere from 0 to 1s to make this unpredictable
  int randomWait = random(0, 1001);
  delay(randomWait);

  // Set low (simulating estop press)
  digitalWrite(outputPin, HIGH);

  // Wait 100ms to reset everything in the
  delay(200);
}