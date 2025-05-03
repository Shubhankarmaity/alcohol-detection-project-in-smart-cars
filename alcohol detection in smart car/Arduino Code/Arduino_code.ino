#include <Wire.h>
#include <LiquidCrystal_I2C.h>

// Initialize LCD with proper address and dimensions
LiquidCrystal_I2C lcd(0x27, 16, 2); // Address 0x27, 16 cols, 2 rows

// Pin Definitions
const int mq3Pin = A0;       // MQ3 Alcohol Sensor
const int relayPin = 8;      // Relay to control motor
const int buttonPin = 9;     // Button to trigger recheck
const int buzzerPin = 7;     // Buzzer on D7

// Threshold Value for Alcohol Detection
const int alcoholThreshold = 500;  // Adjust as per your MQ3 readings

// Block Timing
unsigned long blockStartTime = 0;
const unsigned long blockDuration = 3UL * 60UL * 60UL * 1000UL; // 3 hours in milliseconds
bool isBlocked = false;

// Variables to track face check status
bool waitingForFaceResult = false;
unsigned long faceCheckStartTime = 0;
const unsigned long faceCheckTimeout = 30000; // 30 seconds timeout
bool carStarted = false;
bool initialFaceCheckDone = false;

void setup() {
  Serial.begin(9600);

  // Correct LCD initialization
  lcd.init();             // Initialize the LCD
  lcd.backlight();        // Turn on the backlight

  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print("SonorSense Init");
  tone(7,1000);
  delay(1000);
  noTone(7);
  lcd.clear();

  pinMode(mq3Pin, INPUT);
  pinMode(relayPin, OUTPUT);
  pinMode(buttonPin, INPUT_PULLUP);  // Button with pull-up resistor
  pinMode(buzzerPin, OUTPUT);        // Buzzer pin

  digitalWrite(relayPin, HIGH); // Motor OFF initially until face check

  // Request face verification before starting car
  lcd.setCursor(0, 0);
  lcd.print("Driver Check");
  lcd.setCursor(0, 1);
  lcd.print("Look at camera...");
  Serial.println("CMD:VERIFY_DRIVER");
  waitingForFaceResult = true;
  faceCheckStartTime = millis();
}

void loop() {
  int alcoholValue = analogRead(mq3Pin);
  bool buttonPressed = digitalRead(buttonPin) == LOW;

  // First check for messages from Python - this ensures we process responses immediately
  checkSerialMessages();

  // Display Alcohol Level
  lcd.setCursor(0, 0);
  lcd.print("Alcohol:");
  lcd.print(alcoholValue);
  lcd.print("   "); // clear extra digits

  Serial.print("ALCOHOL:");
  Serial.println(alcoholValue);

  // Don't proceed until initial face check is complete
  if (!initialFaceCheckDone && !waitingForFaceResult) {
    initialFaceCheckDone = true;
  }

  if (initialFaceCheckDone) {
    // Check for alcohol
    if (!isBlocked && alcoholValue > alcoholThreshold) {
      isBlocked = true;
      blockStartTime = millis();
      digitalWrite(relayPin, HIGH); // Motor OFF
      // Buzzer ON for 2 seconds
      digitalWrite(buzzerPin, HIGH);
      lcd.setCursor(0, 1);
      lcd.print("Driver Blocked  ");
      Serial.println("BLOCKED");
      delay(2000);
      digitalWrite(buzzerPin, LOW);
      carStarted = false;
    }

    // If driver is blocked
    if (isBlocked) {
      unsigned long elapsed = millis() - blockStartTime;

      // Auto-unblock after 3 hours
      if (elapsed >= blockDuration) {
        isBlocked = false;
        digitalWrite(relayPin, LOW); // Motor ON
        // Buzzer ON for 1 second
        digitalWrite(buzzerPin, HIGH);
        lcd.setCursor(0, 1);
        lcd.print("Auto Unblocked  ");
        Serial.println("UNBLOCKED");
        delay(1000);
        digitalWrite(buzzerPin, LOW);
        delay(1000);
      }
      // Manual Recheck - only if not already waiting for face result
      else if (buttonPressed && !waitingForFaceResult) {
        lcd.setCursor(0, 1);
        lcd.print("Rechecking...   ");
        Serial.println("RECHECK:" + String(alcoholValue));
        delay(1500);

        int recheckValue = analogRead(mq3Pin);
        Serial.print("RECHECK:");
        Serial.println(recheckValue);

        if (recheckValue < alcoholThreshold) {
          // Passed alcohol test, now check face - MUST be different driver
          lcd.setCursor(0, 1);
          lcd.print("Face check...   ");

          // Request face check from Python
          Serial.println("CMD:CHECK_FACE");
          waitingForFaceResult = true;
          faceCheckStartTime = millis();
        } else {
          // Buzzer ON for 0.5 second for failed recheck
          digitalWrite(buzzerPin, HIGH);
          lcd.setCursor(0, 1);
          lcd.print("Still Drunk     ");
          Serial.println("STILL_BLOCKED");
          delay(500);
          digitalWrite(buzzerPin, LOW);
          delay(1500);
        }
      }

      // Check for face check timeout
      if (waitingForFaceResult && (millis() - faceCheckStartTime > faceCheckTimeout)) {
        waitingForFaceResult = false;
        // Buzzer ON for 0.5 second for timeout
        digitalWrite(buzzerPin, HIGH);
        lcd.setCursor(0, 1);
        lcd.print("Face check failed");
        delay(500);
        digitalWrite(buzzerPin, LOW);
        delay(1500);
      }
    } else if (!carStarted) {
      // Car is not started yet, waiting for button press to trigger driver verification
      if (buttonPressed && !waitingForFaceResult) {
        lcd.setCursor(0, 1);
        lcd.print("Starting car... ");
        Serial.println("CMD:VERIFY_DRIVER");
        waitingForFaceResult = true;
        faceCheckStartTime = millis();
      } else {
        lcd.setCursor(0, 1);
        lcd.print("Press to Start  ");
      }
    } else {
      lcd.setCursor(0, 1);
      lcd.print("Driver Allowed  ");
    }
  }

  delay(100); // 100ms delay for better responsiveness
}

// Process messages from Python
void checkSerialMessages() {
  if (Serial.available() > 0) {
    String message = Serial.readStringUntil('\n');
    message.trim();

    if (message == "FACE:ALLOWED" || message == "FACE:DIFFERENT") {
      // Driver is allowed to drive - either a new driver or no blocked driver
      if (waitingForFaceResult) {
        waitingForFaceResult = false;
        isBlocked = false;
        carStarted = true;
        digitalWrite(relayPin, LOW); // Motor ON
        // Buzzer ON for 1 second for allowed
        digitalWrite(buzzerPin, HIGH);
        lcd.setCursor(0, 1);
        lcd.print("Driver Verified ");
        delay(1000);
        digitalWrite(buzzerPin, LOW);
        delay(1000);
      }
    }
    else if (message == "FACE:BLOCKED") {
      // Driver is blocked
      if (waitingForFaceResult) {
        waitingForFaceResult = false;
        isBlocked = true;
        carStarted = false;
        digitalWrite(relayPin, HIGH); // Motor OFF
        // Buzzer ON for 2 seconds for block
        digitalWrite(buzzerPin, HIGH);
        lcd.setCursor(0, 1);
        lcd.print("Driver Blocked  ");
        delay(2000);
        digitalWrite(buzzerPin, LOW);
        lcd.setCursor(0, 1);
        lcd.print("3-Hour Timeout  ");
        delay(2000);
      }
    }
    else if (message == "FACE:SAME") {
      // Same driver detected - remain blocked
      if (waitingForFaceResult) {
        waitingForFaceResult = false;
        isBlocked = true;
        carStarted = false;
        digitalWrite(relayPin, HIGH); // Motor OFF
        // Buzzer ON for 0.5 second for same driver
        digitalWrite(buzzerPin, HIGH);
        lcd.setCursor(0, 1);
        lcd.print("Same Driver!    ");
        delay(500);
        digitalWrite(buzzerPin, LOW);
        delay(1500);
        lcd.setCursor(0, 1);
        lcd.print("Find new driver ");
        delay(2000);
      }
    }
    else if (message == "FACE:ERROR") {
      // Error in face recognition
      if (waitingForFaceResult) {
        waitingForFaceResult = false;
        // Buzzer ON for 0.5 second for error
        digitalWrite(buzzerPin, HIGH);
        lcd.setCursor(0, 1);
        lcd.print("Face Error      ");
        delay(500);
        digitalWrite(buzzerPin, LOW);
        delay(1500);
      }
    }
    // Handle ON/OFF commands for the relay
    else if (message == "ON") {
      digitalWrite(relayPin, LOW); // Motor ON
      carStarted = true;
      // Buzzer ON for 0.5 second for manual ON
      digitalWrite(buzzerPin, HIGH);
      delay(500);
      digitalWrite(buzzerPin, LOW);
    }
    else if (message == "OFF") {
      digitalWrite(relayPin, HIGH); // Motor OFF
      carStarted = false;
      // Buzzer ON for 0.5 second for manual OFF
      digitalWrite(buzzerPin, HIGH);
      delay(500);
      digitalWrite(buzzerPin, LOW);
    }
  }
}
