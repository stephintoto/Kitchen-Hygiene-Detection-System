
import win32event
import win32api
import sys
from winerror import ERROR_ALREADY_EXISTS
import tkinter as tk
from tkinter import ttk, messagebox
from PIL import ImageTk, Image
import cv2
import os
import time
from shutil import move
from ultralytics import YOLO
from firebase_admin import credentials, initialize_app, storage, firestore

# Check if an instance is already running
mutex = win32event.CreateMutex(None, False, 'name')
last_error = win32api.GetLastError()
if last_error == ERROR_ALREADY_EXISTS:
    sys.exit(0)

def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        base_path = sys._MEIPASS  # PyInstaller creates a temp folder and stores path in _MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

# Firebase initialization
cred_path = resource_path('resto-care-199fda-firebase-adminsdk-8jliy-50c292167b.json')
cred = credentials.Certificate(cred_path)
firebase_app = initialize_app(cred, {'storageBucket': 'resto-care-199fda.appspot.com'})
bucket = storage.bucket()
db = firestore.client()

# Set your image directory and processed directory paths here
image_directory = resource_path("capture")
processed_directory = resource_path("processed")
images_folder = processed_directory  # Update to use 'processed_directory' instead

# Create the processed directory if it doesn't exist
os.makedirs(processed_directory, exist_ok=True)

# YOLO model and classes
model = YOLO(resource_path('yolov8m42epoch.pt'))
violation_classes = ['no_apron', 'no_gloves', 'no_hairnet', 'lizard', 'rat', 'cockroach']

# Variable to store the running status
is_running = False

# Function to start the process
def start_process():
    global is_running
    if not is_running:
        is_running = True
        # Start the process after a delay of 10 seconds
        root.after(1000, capture_loop)

def stop_process():
    global is_running
    is_running = False

def capture_loop():
    if is_running:
        capture_images()
        # Check again after 10 seconds
        root.after(1000, capture_loop)

def capture_images():
    try:
        # Get the selected camera
        selected_camera = camera_var.get()
        # Convert selected camera to zero-based index
        camera_index = int(selected_camera.split()[-1]) if selected_camera != "No Camera" else None
        if camera_index is not None:
            capture_objects = [cv2.VideoCapture(camera_index)]
        else:
            messagebox.showerror("Error", "No camera selected.")
            return

        max_images_to_capture = 1  # Capture only one image
        images_captured = 0

        while images_captured < max_images_to_capture:
            start_time = time.time()
            while time.time() - start_time < 5:
                for i, cap in enumerate(capture_objects):
                    ret, frame = cap.read()
                    if not ret:
                        messagebox.showerror("Error", f"Failed to capture frame from camera {i}")
                        return
                    # Display live feed in the GUI
                    frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)  # Convert colors from BGR to RGB
                    frame = Image.fromarray(frame)
                    frame = ImageTk.PhotoImage(image=frame)
                    live_feed_label.configure(image=frame)
                    live_feed_label.image = frame
                    # Delay to control the frame rate
                    root.update_idletasks()
                    root.after(10)

            for i, cap in enumerate(capture_objects):
                ret, frame = cap.read()
                if not ret:
                    messagebox.showerror("Error", f"Failed to capture frame from camera {i}")
                    return
                frame = cv2.resize(frame, (640, 480))
                timestamp = int(time.time())
                image_filename = f"camera_{i}image{timestamp}.jpg"
                image_path = os.path.join(image_directory, image_filename)
                cv2.imwrite(image_path, frame)
                print(f"Image captured from camera {i} and saved as {image_filename}")
                images_captured += 1

            if len(capture_objects) == 1:
                key = cv2.waitKey(1)
                if key == ord('n'):
                    for cap in capture_objects:
                        cap.release()
                    # Switch to the next camera
                    selected_index = camera_dropdown.current()  # Fetch the current selection index
                    next_index = (selected_index + 1) % len(camera_options)
                    camera_var.set(camera_options[next_index])

            # Close all OpenCV windows
            cv2.destroyAllWindows()
            process_images()

    except Exception as e:
        messagebox.showerror("Error", f"An error occurred: {e}")

def process_images():
    try:
        images_processed = 0
        previous_violations = set()
        image_files = [f for f in os.listdir(image_directory) if f.endswith(".jpg")]

        # Check if no images are captured
        if not image_files:
            print("No images captured. Continuing capture loop...")
            return

        for image_file in image_files:
            image_path = os.path.join(image_directory, image_file)
            # Check if the file exists before processing
            if not os.path.exists(image_path):
                continue

            frame = cv2.imread(image_path)
            results = model(frame, show=False)
            boxes = results[0].boxes.xyxy.tolist()
            classes = results[0].boxes.cls.tolist()
            names = results[0].names
            confidences = results[0].boxes.conf.tolist()
            detected_classes = []  # List to store detected violation classes

            for box, cls, conf in zip(boxes, classes, confidences):
                x1, y1, x2, y2 = box
                confidence = conf
                class_index = int(cls)
                class_name = names[class_index]

                if class_name in previous_violations:
                    continue

                if class_name in violation_classes and confidence > 0.4:
                    detected_classes.append(class_name)  # Add detected class to the list
                    previous_violations.add(class_name)

            # Join detected classes into a single string separated by commas
            violation_classes_str = ', '.join(detected_classes)

            # Get the selected hotel name from the dropdown menu
            hotel_name = hotel_var.get()

            # Delete the image if no violations are detected
            if not detected_classes:
                print(f"No violations detected in {image_file}. Deleting the image.")
                os.remove(image_path)
                continue

            # Move the image to the processed folder
            processed_image_path = os.path.join(processed_directory, image_file)
            move(image_path, processed_image_path)
            print(f"Image {image_file} moved to processed folder.")

            # Proceed with uploading violation details to Firestore
            upload_to_firestore(image_file, violation_classes_str, hotel_name)
            images_processed += 1

    except Exception as e:
        messagebox.showerror("Error", f"An error occurred: {e}")

def upload_to_firestore(image_filename, violation_classes_str, hotel_name):
    try:
        image_path = os.path.join(images_folder, image_filename)
        blob = bucket.blob(image_filename)
        blob.upload_from_filename(image_path)
        blob.make_public()
        image_url = blob.public_url
        timestamp = int(time.time())
        violation_ref = db.collection('ViolationList')
        violation_doc = violation_ref.add({
            'DateTime': time.strftime('%B %d, %Y at %I:%M:%S %p', time.localtime(timestamp)),
            'image': image_url,
            'name': 'Hygiene Violation',
            'violationclass': violation_classes_str,
            'hotelname': hotel_name
        })
        print(f"Violation details uploaded to Firestore: {image_filename}")
        os.remove(image_path)

    except Exception as e:
        messagebox.showerror("Error", f"An error occurred: {e}")

# Create the GUI window
root = tk.Tk()
root.title("RestoCare")

# Function to center the window on the screen
def center_window(window, width, height):
    screen_width = window.winfo_screenwidth()
    screen_height = window.winfo_screenheight()
    x_coordinate = (screen_width / 2) - (width / 2)
    y_coordinate = (screen_height / 2) - (height / 2)
    window.geometry("%dx%d+%d+%d" % (width, height, x_coordinate, y_coordinate))

# Set window size and center it on the screen
window_width = 900  # Increased window width to accommodate the live feed
window_height = 500
center_window(root, window_width, window_height)

# Add padding
root.configure(padx=10, pady=0)

# Load the image
image_path = resource_path("restocare.png")
img = Image.open(image_path)
img = img.resize((200, 200))
photo = ImageTk.PhotoImage(img)

# Create a label to display the image
image_label = tk.Label(root, image=photo)
image_label.image = photo
image_label.grid(row=0, column=0, columnspan=2, padx=10, pady=10)

# Add a heading label
company_name = "RestoCare"
heading_label = tk.Label(root, text=company_name, font=("Helvetica", 20, "bold"), fg="green")
heading_label.grid(row=0, column=1, padx=5, pady=5, sticky="w")

# Add a hotel name dropdown label and dropdown menu
hotel_label = tk.Label(root, text="Select Hotel:", font=("Helvetica", 12))
hotel_label.grid(row=1, column=0, sticky="w")

# Replace with your list of hotel names
hotel_options = ["Sample Hotel", "Hotel A", "Hotel B", "Hotel C"]
hotel_var = tk.StringVar(value=hotel_options[0])  # Default selection
hotel_dropdown = ttk.Combobox(root, textvariable=hotel_var, values=hotel_options)
hotel_dropdown.grid(row=1, column=1, sticky="w")

# Add a camera dropdown label and dropdown menu
camera_label = tk.Label(root, text="Select Camera:", font=("Helvetica", 12))
camera_label.grid(row=2, column=0, sticky="w")

# Replace with available camera options
camera_options = ["No Camera", "Camera 0", "Camera 1", "Camera 2"]
camera_var = tk.StringVar(value=camera_options[0])  # Default selection
camera_dropdown = ttk.Combobox(root, textvariable=camera_var, values=camera_options)
camera_dropdown.grid(row=2, column=1, sticky="w")

# Add Start and Stop buttons
start_button = ttk.Button(root, text="Start", command=start_process)
start_button.grid(row=3, column=0, pady=10)

stop_button = ttk.Button(root, text="Stop", command=stop_process)
stop_button.grid(row=3, column=1, pady=10, sticky="w")

# Add a live feed label for displaying the camera feed
live_feed_label = tk.Label(root)
live_feed_label.grid(row=4, column=0, columnspan=2)

# Start the GUI event loop
root.mainloop()
