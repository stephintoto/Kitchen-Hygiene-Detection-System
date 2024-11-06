# RestoCare

RestoCare is a desktop application designed for restaurant hygiene monitoring using computer vision and machine learning. It detects safety violations such as the absence of aprons, gloves, hairnets, and the presence of pests (e.g., lizards, rats, cockroaches) through a camera feed. The app captures, processes, and uploads images to Firebase, ensuring restaurant owners or managers can maintain high standards of hygiene.

## Features
- **Live Camera Feed**: View real-time video feed from selected cameras.
- **Violation Detection**: Utilizes a trained YOLO model to identify hygiene violations.
- **Image Capture and Processing**: Captures images from the feed, processes them for violations, and uploads flagged results.
- **Firebase Integration**: Stores processed data, including images and details of detected violations, in Firestore and Firebase Storage.
- **Graphical User Interface (GUI)**: User-friendly Tkinter-based interface for easy interaction.
