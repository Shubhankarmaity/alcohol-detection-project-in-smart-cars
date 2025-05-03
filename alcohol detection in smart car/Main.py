import cv2
import face_recognition
import os
import serial
import time
import pickle
import json
from datetime import datetime, timedelta
import smtplib
import requests
from playsound import playsound  # <-- already imported

# Configure the serial connection to Arduino
ser = None
try:
    ser = serial.Serial('COM3', 9600, timeout=1)  # Change COM port as needed
    print("Connected to Arduino")
    # Play welcome audio after successful connection
    playsound(os.path.join('audio', 'welcome.mp3'))
    time.sleep(2)  # Allow connection to stabilize
except Exception as e:
    print(f"Error connecting to Arduino: {e}")
    exit(1)

# Create directories if they don't exist
face_data_dir = "driver_faces"
os.makedirs(face_data_dir, exist_ok=True)

# Database file paths
face_db_file = "driver_faces/face_database.pkl"
block_db_file = "driver_faces/blocked_drivers.json"

# Face data storage
blocked_face_encoding = None
blocked_timestamp = None
blocked_until = None
face_similarity_threshold = 0.5  # 50% similarity threshold

# Driver database
driver_database = []  # List of {encoding, timestamp, blocked_until} dictionaries

# Load existing face database if available
def load_face_database():
    global driver_database
    try:
        if os.path.exists(face_db_file):
            with open(face_db_file, 'rb') as f:
                driver_database = pickle.load(f)
                print(f"Loaded {len(driver_database)} driver records from database")
                
        if os.path.exists(block_db_file):
            with open(block_db_file, 'r') as f:
                block_data = json.load(f)
                # Update global variables for the most recently blocked driver
                if block_data.get('blocked_until'):
                    blocked_timestamp_str = block_data.get('blocked_timestamp')
                    blocked_until_str = block_data.get('blocked_until')
                    
                    if blocked_timestamp_str and blocked_until_str:
                        global blocked_timestamp, blocked_until, blocked_face_encoding
                        blocked_timestamp = datetime.fromisoformat(blocked_timestamp_str)
                        blocked_until = datetime.fromisoformat(blocked_until_str)
                        
                        # Load the most recently blocked face encoding
                        if os.path.exists(block_data.get('face_file', '')):

                            with open(block_data.get('face_file'), 'rb') as face_file:
                                blocked_face_encoding = pickle.load(face_file)
                                print("Loaded blocked driver's face encoding")
    except Exception as e:
        print(f"Error loading driver database: {e}")
        driver_database = []

# Save face database
def save_face_database():
    try:
        with open(face_db_file, 'wb') as f:
            pickle.dump(driver_database, f)
        
        if blocked_until and blocked_timestamp and blocked_face_encoding is not None:
            block_data = {
                'blocked_timestamp': blocked_timestamp.isoformat(),
                'blocked_until': blocked_until.isoformat(),
                'face_file': f"{face_data_dir}/latest_blocked_face.pkl"
            }
            
            # Save the blocked face separately
            with open(block_data['face_file'], 'wb') as face_file:
                pickle.dump(blocked_face_encoding, face_file)
                
            with open(block_db_file, 'w') as f:
                json.dump(block_data, f)
                
        print("Face database saved")
    except Exception as e:
        print(f"Error saving driver database: {e}")

# Face capture and recognition functions
def capture_face_with_preview(caption="Capture Face", timeout=5):
    """Capture an image from the camera with a preview window"""
    print(f"Opening camera for {caption}...")
    cap = cv2.VideoCapture(0)  # Use default camera
    if not cap.isOpened():
        print("Error: Could not open camera")
        return None
    
    # Start time for timeout
    start_time = time.time()
    face_found = False
    frame = None
    
    print(f"Please look at the camera - {timeout} seconds to capture")
    
    while time.time() - start_time < timeout:
        ret, frame = cap.read()
        if not ret:
            continue
            
        # Check if a face is in the frame
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        face_locations = face_recognition.face_locations(rgb_frame)
        
        # Display the frame with face rectangle if detected
        display_frame = frame.copy()
        if face_locations:
            face_found = True
            for (top, right, bottom, left) in face_locations:
                cv2.rectangle(display_frame, (left, top), (right, bottom), (0, 255, 0), 2)
            cv2.putText(display_frame, "Face Detected!", (10, 30), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        else:
            cv2.putText(display_frame, "No Face Detected - Please look at camera", 
                       (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
        
        # Show countdown timer
        remaining = int(timeout - (time.time() - start_time))
        cv2.putText(display_frame, f"Time: {remaining}s", (10, 60), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 0, 0), 2)
                   

        # Show the frame
        cv2.imshow(caption, display_frame)
        
        # Break the loop if face found and key pressed or timeout reached
        key = cv2.waitKey(1) & 0xFF
        if (face_found and key == ord('c')) or (face_found and remaining < 2):
            print("Face captured!")
            # Play face_saved.mp3 when face is detected and captured
            try:
                playsound(os.path.join('audio', 'face_saved.mp3'))
            except Exception as e:
                print(f"Could not play face_saved.mp3: {e}")
            break
        
        # Exit on ESC key
        if key == 27:  # ESC key
            face_found = False
            break
    
    # Cleanup
    cap.release()
    cv2.destroyAllWindows()
    
    if face_found and frame is not None:
        return frame
    else:
        print("No face was detected or capture was cancelled.")
        return None

def detect_and_encode_face(image):
    """Detect a face in the image and return its encoding"""
    if image is None:
        return None
        
    # Convert to RGB (face_recognition uses RGB)
    rgb_image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    
    # Find faces in the image
    face_locations = face_recognition.face_locations(rgb_image)
    
    if not face_locations:
        print("No face detected in image")
        return None
    
    # Get face encodings
    face_encodings = face_recognition.face_encodings(rgb_image, face_locations)
    
    if not face_encodings:
        return None
        
    return face_encodings[0]

def capture_blocked_driver():
    """Capture the face of the blocked driver"""
    global blocked_face_encoding, blocked_timestamp, blocked_until
    
    print("Capturing blocked driver's face...")
    frame = capture_face_with_preview("Blocked Driver - CAPTURE", timeout=5)
    
    if frame is not None:
        # Save the image
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{face_data_dir}/blocked_driver_{timestamp}.jpg"
        cv2.imwrite(filename, frame)
        
        # Get face encoding
        blocked_face_encoding = detect_and_encode_face(frame)
        blocked_timestamp = datetime.now()
        blocked_until = datetime.now() + timedelta(hours=3)
        
        if blocked_face_encoding is not None:
            print(f"Blocked driver's face captured and saved as {filename}")
            return True
    
    print("Failed to capture blocked driver's face")
    return False

def check_new_driver():
    """Check if the current driver is different from the blocked driver"""
    global blocked_face_encoding
    
    if blocked_face_encoding is None:
        print("No blocked driver face on record")
        return True
    
    print("Capturing new driver's face...")
    frame = capture_face_with_preview("New Driver - VERIFICATION", timeout=5)
    
    if frame is not None:
        # Save the image
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{face_data_dir}/new_driver_{timestamp}.jpg"
        cv2.imwrite(filename, frame)
        
        # Get face encoding
        new_face_encoding = detect_and_encode_face(frame)
        
        if new_face_encoding is not None:
            # Compare faces
            face_distance = face_recognition.face_distance([blocked_face_encoding], new_face_encoding)[0]
            match_percentage = (1 - face_distance) * 100
            
            print(f"Face match: {match_percentage:.2f}%")
            
            # Return True if face is different (match < 50%)
            return match_percentage < 50
    
    print("Failed to properly analyze new driver's face")
    return False

def block_car():
    """Block the car by sending command to Arduino"""
    ser.write(b"OFF\n")
    print("[INFO] Car is blocked for 3 hours.")

def unblock_car():
    """Unblock the car by sending command to Arduino"""
    ser.write(b"ON\n")
    print("[INFO] Car is unblocked.")

def is_driver_blocked(face_encoding):
    """Check if the driver is currently blocked"""
    global blocked_face_encoding, blocked_until
    
    # If no one is blocked or block period has expired
    if blocked_face_encoding is None or blocked_until is None:
        return False
    
    # If block period has expired
    if datetime.now() > blocked_until:
        return False
    
    # Compare face with blocked driver
    if face_encoding is not None:
        face_distance = face_recognition.face_distance([blocked_face_encoding], face_encoding)[0]
        match_percentage = (1 - face_distance) * 100
        print(f"Face match with blocked driver: {match_percentage:.2f}%")
        
        # Return True if face matches blocked driver (>= 50% match)
        return match_percentage >= 50
    
    return False

def verify_driver():
    """Verify the driver is not blocked before starting the car"""
    print("Verifying driver's face...")
    frame = capture_face_with_preview("Driver Verification", timeout=5)
    
    if frame is not None:
        # Save the image
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{face_data_dir}/driver_verification_{timestamp}.jpg"
        cv2.imwrite(filename, frame)
        
        # Get face encoding
        driver_encoding = detect_and_encode_face(frame)
        
        if driver_encoding is not None:
            # Check if driver is blocked
            if is_driver_blocked(driver_encoding):
                print("Driver is currently blocked! Car cannot start until block period expires.")
                return False
            else:
                # Add to driver database for future reference
                driver_record = {
                    'timestamp': datetime.now(),
                    'blocked_until': None,
                    'encoding': driver_encoding
                }
                driver_database.append(driver_record)
                save_face_database()
                print("Driver verified and allowed to drive")
                return True
    
    print("Failed to verify driver's face")
    return False

def send_alcohol_alert_email():
    """Send an email alert with location when alcohol is detected"""
    print("[INFO] Sending email alert to vehicle owner...")
    
    # Load email credentials
    email = "ranjan705b@gmail.com"
    password = "ajzs ehqm jpgh jzdq"

    # Fetch current location (approximate, based on IP)
    try:
        response = requests.get("https://ipinfo.io/json")
        data = response.json()
        ip = data.get("ip", "Unknown")
        city = data.get("city", "Unknown")
        region = data.get("region", "Unknown")
        country = data.get("country", "Unknown")
        loc = data.get("loc", "Unknown, Unknown")
        latitude, longitude = loc.split(",") if "," in loc else ("Unknown", "Unknown")
        org = data.get("org", "Unknown")
        postal = data.get("postal", "Unknown")
        timezone = data.get("timezone", "Unknown")
    except Exception:
        ip = city = region = country = org = postal = timezone = "Unknown"
        latitude = longitude = "Unknown"

    # Email details
    to_email = "indiavivo956@gmail.com"  # Owner email
    subject = "Urgent: Alcohol Detected in Vehicle - Driver Safety Alert"
    body = (
        "Dear Relative,\n\n"
        "This is an automated alert from your vehicle's Alcohol Detection System.\n\n"
        "Alcohol has been detected in the breath of your vehicle's driver. "
        "For safety reasons, the car's movement has been blocked to prevent any possible accidents.\n\n"
        "Current Location Details of the Vehicle:\n"
        f"IP Address: {ip}\n"
        f"City: {city}\n"
        f"Region: {region}\n"
        f"Country: {country}\n"
        f"Latitude: {latitude}\n"
        f"Longitude: {longitude}\n"
        f"Organization: {org}\n"
        f"Postal Code: {postal}\n"
        f"Timezone: {timezone}\n\n"
        "Please take immediate action to ensure the safety of the driver and others.\n\n"
        "Thank you for your attention.\n"
        "Vehicle Alcohol Detection System"
    )

    # Connect to the SMTP server and send the email
    try:
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()  # Enable security
            server.login(email, password)
            message = f"Subject: {subject}\n\n{body}"
            server.sendmail(email, to_email, message)
        print("[INFO] Email alert sent successfully!")
    except Exception as e:
        print(f"[ERROR] Failed to send email alert: {e}")

def main():
    """Main loop to read from Arduino and respond to commands"""
    global blocked_until, blocked_face_encoding, blocked_timestamp
    
    if ser is None:
        print("No serial connection")
        return
    
    # Load existing face database
    load_face_database()
    
    print("SonerSense system is now running. Waiting for commands...")
    
    # Keep track of alcohol level for later checks
    last_alcohol_value = 0
    waiting_for_face_check = False
    
    while True:
        try:
            if ser.in_waiting > 0:
                line = ser.readline().decode('utf-8').strip()
                print(f"Arduino says: {line}")
                
                # Extract alcohol value from readings
                if line.startswith("ALCOHOL:"):
                    try:
                        last_alcohol_value = int(line.split(":")[1])
                    except:
                        pass
                
                # Verify driver on startup or button press
                elif "CMD:VERIFY_DRIVER" in line:
                    print("[INFO] Verifying driver before starting car...")
                    
                    # First check if there's a blocked driver with an active block period
                    if blocked_face_encoding is not None and blocked_until is not None and datetime.now() < blocked_until:
                        print("[INFO] There is an active block in place. Checking if this is the blocked driver...")
                        
                        # This will verify if it's a different driver from the blocked one
                        if verify_driver():
                            print("[INFO] New driver verified - car can start")
                            ser.write(b"FACE:ALLOWED\n")
                        else:
                            print("[INFO] Driver is blocked or verification failed")
                            ser.write(b"FACE:BLOCKED\n")
                    else:
                        # No active block, just verify the driver normally
                        if verify_driver():
                            print("[INFO] Driver verified - car can start")
                            ser.write(b"FACE:ALLOWED\n")
                        else:
                            print("[INFO] Driver verification failed")
                            ser.write(b"FACE:ERROR\n")
                
                # Handle alcohol detection and blocking
                elif "BLOCKED" in line:
                    print("[INFO] Alcohol detected. Starting face capture...")
                    if capture_blocked_driver():
                        print("Blocked driver's face stored")
                        block_car()
                        # Send email alert to owner
                        send_alcohol_alert_email()
                        save_face_database()  # Save the updated database
                    else:
                        print("Failed to store blocked driver's face - trying again...")
                        if capture_blocked_driver():
                            print("Blocked driver's face stored on second attempt")
                            block_car()
                            # Send email alert to owner
                            send_alcohol_alert_email()
                            save_face_database()
                        else:
                            print("Failed to store blocked driver's face after retry")
                
                # Handle recheck button pressed
                elif "RECHECK" in line:
                    print("[INFO] Recheck button pressed. Waiting for alcohol check result...")
                    waiting_for_face_check = True
                
                # When CMD:CHECK_FACE is received after RECHECK
                elif "CMD:CHECK_FACE" in line:
                    if waiting_for_face_check:
                        waiting_for_face_check = False
                        print("[INFO] Alcohol test passed. Starting face verification...")
                        
                        if blocked_face_encoding is None:
                            print("[INFO] No blocked driver face on record. Allowing access.")
                            ser.write(b"FACE:ALLOWED\n")
                            unblock_car()
                        else:
                            # We need to check if this is a different driver
                            is_different = check_new_driver()
                            
                            if is_different:
                                print("[INFO] New driver detected - unblocking")
                                ser.write(b"FACE:DIFFERENT\n")
                                unblock_car()
                                time.sleep(0.5)
                            else:
                                print("[INFO] Same driver detected - remaining blocked")
                                ser.write(b"FACE:SAME\n")
                                time.sleep(0.5)
                                print("[INFO] Please have a different driver try again. Original driver is blocked for 3 hours.")
                
                # Auto-unblock after time expired (if Arduino asks)
                elif "UNBLOCKED" in line:
                    blocked_until = None
                    blocked_face_encoding = None
                    print("[INFO] Block period expired.")
                    save_face_database()  # Save the updated database
                
            # Check if block period has expired
            if blocked_until and datetime.now() > blocked_until:
                blocked_until = None
                blocked_face_encoding = None
                print("[INFO] Block period expired.")
                save_face_database()  # Save the updated database
                
            time.sleep(0.1)  # Small delay to reduce CPU usage
            
        except KeyboardInterrupt:
            print("Exiting program")
            save_face_database()
            break
        except Exception as e:
            print(f"Error in main loop: {e}")
            print(f"Error details: {type(e).__name__}, {str(e)}")
            try:
                ser.write(b"FACE:ERROR\n")
            except:
                pass
            time.sleep(1)

if __name__ == "__main__":
    main()
