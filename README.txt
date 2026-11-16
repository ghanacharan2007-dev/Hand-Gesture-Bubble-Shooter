# Hand Gesture Bubble Shooter

## Features
- 60-second game, medium difficulty
- Randomly generated bubbles rise from the bottom
- Bubble sizes and colours vary
- Smaller bubbles award more points: small 50, medium 30, large 10, extra-large 5
- Score report after 30 seconds and a final report at 60 seconds
- Top 10 scores saved in `high_scores.json` with date and time
- OpenCV + MediaPipe hand tracking
- Index finger aims; pinch thumb and index finger to shoot
- Mouse click is included as a fallback for testing

## Setup (Windows)
1. Install Python 3.10 or 3.11 (recommended for MediaPipe compatibility).
2. Open Command Prompt in this folder.
3. Run: `python -m pip install -r requirements.txt`
4. Run: `python main.py`
5. Allow webcam access when prompted.

If installation of MediaPipe fails, use a compatible 64-bit Python 3.10/3.11 installation.
