import cv2
import mediapipe as mp
import tkinter as tk
from tkinter import messagebox
from PIL import Image, ImageTk
import random
import math
import json
import time
import threading
from datetime import datetime
from pathlib import Path

# Hand Gesture Bubble Shooter
# Aim with your index finger; pinch thumb + index finger to shoot.
# Rising bubbles are targets. Smaller targets award more points.

WIDTH, HEIGHT = 900, 620
GAME_SECONDS = 60
REPORT_EVERY = 30
HIGH_SCORE_FILE = Path(__file__).with_name("high_scores.json")

COLORS = ["#ff4d6d", "#ffd166", "#06d6a0", "#4cc9f0", "#b388ff", "#ff9f1c"]

SIZES = [
    # radius, points
    (17, 50),   # small
    (29, 30),   # medium
    (43, 10),   # large
    (57, 5),    # extra large
]

class HandTracker:
    def __init__(self):
        self.lock = threading.Lock()
        self.aim = (WIDTH / 2, HEIGHT / 2)
        self.pinch_event = False
        self.running = True
        self.frame = None
        self.error = None
        self.thread = threading.Thread(target=self._camera_loop, daemon=True)
        self.thread.start()

    def _camera_loop(self):
        cap = cv2.VideoCapture(0)
        # Request a clear webcam frame before resizing it for the preview.
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        if not cap.isOpened():
            self.error = "Webcam not found. Check camera permissions."
            return

        hands_module = mp.solutions.hands
        hands = hands_module.Hands(
            static_image_mode=False,
            max_num_hands=1,
            min_detection_confidence=0.6,
            min_tracking_confidence=0.6
        )
        was_pinching = False

        while self.running:
            ok, frame = cap.read()
            if not ok:
                self.error = "Could not read from webcam."
                time.sleep(0.1)
                continue

            frame = cv2.flip(frame, 1)
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            result = hands.process(rgb)

            pinch_now = False
            if result.multi_hand_landmarks:
                hand = result.multi_hand_landmarks[0]
                index_tip = hand.landmark[8]
                thumb_tip = hand.landmark[4]

                # Convert camera position into game coordinates.
                aim_x = max(0, min(WIDTH, int(index_tip.x * WIDTH)))
                aim_y = max(0, min(HEIGHT - 100, int(index_tip.y * HEIGHT)))
                distance = math.hypot(index_tip.x - thumb_tip.x,
                                      index_tip.y - thumb_tip.y)
                pinch_now = distance < 0.055

                with self.lock:
                    self.aim = (aim_x, aim_y)
                    self.pinch_event = pinch_now and not was_pinching

                mp.solutions.drawing_utils.draw_landmarks(
                    frame, hand, hands_module.HAND_CONNECTIONS
                )
            else:
                with self.lock:
                    self.pinch_event = False

            was_pinching = pinch_now
            with self.lock:
                self.frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        hands.close()
        cap.release()

    def read(self):
        with self.lock:
            frame = self.frame.copy() if self.frame is not None else None
            aim = self.aim
            shoot = self.pinch_event
            self.pinch_event = False
        return frame, aim, shoot

    def close(self):
        self.running = False


class Bubble:
    def __init__(self):
        self.radius, self.points = random.choice(SIZES)
        self.x = random.randint(self.radius + 8, WIDTH - self.radius - 8)
        self.y = HEIGHT + self.radius
        # Medium difficulty: steady upward movement.
        self.speed = random.uniform(1.25, 2.25)
        self.color = random.choice(COLORS)


class Shot:
    def __init__(self, x, y, target_x, target_y):
        self.x = x
        self.y = y
        dx, dy = target_x - x, target_y - y
        length = math.hypot(dx, dy) or 1
        self.vx = dx / length * 10
        self.vy = dy / length * 10
        self.radius = 7


class BubbleShooter:
    def __init__(self, root):
        self.root = root
        self.root.title("Hand Gesture Bubble Shooter")
        self.root.resizable(False, False)
        self.root.configure(bg="#101522")

        self.tracker = HandTracker()
        self.running = False
        self.game_over = False
        self.score = 0
        self.shots = 0
        self.hit_counts = {"Small": 0, "Medium": 0, "Large": 0, "Extra large": 0}
        self.bubbles = []
        self.shots_list = []
        self.start_time = None
        self.last_spawn = 0
        self.last_report = 0
        self.last_aim = (WIDTH / 2, HEIGHT / 2)
        self.camera_photo = None
        self.high_scores = self.load_high_scores()

        header = tk.Frame(root, bg="#101522")
        header.pack(fill="x", padx=12, pady=(10, 4))
        tk.Label(header, text="HAND BUBBLE SHOOTER", fg="white",
                 bg="#101522", font=("Arial", 19, "bold")).pack(side="left")
        self.score_label = tk.Label(header, text="Score: 0", fg="#ffd166",
                                    bg="#101522", font=("Arial", 14, "bold"))
        self.score_label.pack(side="right", padx=12)
        self.time_label = tk.Label(header, text="Time: 60s", fg="#7ee7ff",
                                   bg="#101522", font=("Arial", 14, "bold"))
        self.time_label.pack(side="right", padx=12)

        body = tk.Frame(root, bg="#101522")
        body.pack(padx=12, pady=6)

        self.canvas = tk.Canvas(body, width=WIDTH, height=HEIGHT,
                                bg="#121c32", highlightthickness=2,
                                highlightbackground="#344563")
        self.canvas.grid(row=0, column=0, rowspan=2)
        self.canvas.bind("<Button-1>", self.mouse_shoot)

        side = tk.Frame(body, bg="#1b263b", width=1140, height=HEIGHT)
        side.grid(row=0, column=1, sticky="ns", padx=(10, 0))
        side.grid_propagate(False)

        tk.Label(side, text="WEBCAM / HAND TRACKING", fg="white",
                 bg="#1b263b", font=("Arial", 10, "bold")).pack(pady=(10, 5))
        self.camera_label = tk.Label(side, bg="#080d18", width=138, height=50,
                                     text="Starting camera...", fg="white")
        self.camera_label.pack(padx=8)

        tk.Label(side, text="CONTROLS", fg="#ffd166", bg="#1b263b",
                 font=("Arial", 12, "bold")).pack(pady=(14, 5))
        controls = ("1. Point with your INDEX finger to aim\n"
                    "2. PINCH thumb + index finger to shoot\n"
                    "3. Smaller bubbles = more points\n"
                    "Mouse click also shoots for testing")
        tk.Label(side, text=controls, fg="#e6edf7", bg="#1b263b",
                 justify="left", font=("Arial", 9), wraplength=1080).pack(padx=10)

        tk.Label(side, text="LATEST SCORE REPORT", fg="#ffd166",
                 bg="#1b263b", font=("Arial", 11, "bold")).pack(pady=(15, 5))
        self.report_label = tk.Label(side, text="Your 30-second report will appear here.",
                                     fg="#e6edf7", bg="#1b263b", justify="left",
                                     wraplength=1080, font=("Arial", 9))
        self.report_label.pack(padx=10)

        tk.Label(side, text="TOP HIGH SCORES", fg="#ffd166", bg="#1b263b",
                 font=("Arial", 11, "bold")).pack(pady=(15, 5))
        self.leaderboard = tk.Label(side, text="", fg="#e6edf7", bg="#1b263b",
                                    justify="left", font=("Arial", 9))
        self.leaderboard.pack(padx=10)
        self.refresh_leaderboard()

        footer = tk.Frame(root, bg="#101522")
        footer.pack(fill="x", padx=12, pady=(4, 10))
        self.status_label = tk.Label(footer, text="Press START GAME. Allow webcam access.",
                                     fg="#b9c7dc", bg="#101522", font=("Arial", 10))
        self.status_label.pack(side="left")
        self.start_button = tk.Button(footer, text="START GAME", command=self.start_game,
                                      bg="#06d6a0", fg="#07131b", font=("Arial", 10, "bold"),
                                      padx=15, relief="flat")
        self.start_button.pack(side="right", padx=5)
        tk.Button(footer, text="QUIT", command=self.quit,
                  bg="#344563", fg="white", padx=15, relief="flat").pack(side="right")

        self.root.protocol("WM_DELETE_WINDOW", self.quit)
        self.draw_idle_screen()
        self.update_loop()

    def load_high_scores(self):
        try:
            if HIGH_SCORE_FILE.exists():
                data = json.loads(HIGH_SCORE_FILE.read_text(encoding="utf-8"))
                return sorted(data, key=lambda x: x.get("score", 0), reverse=True)[:10]
        except Exception:
            pass
        return []

    def save_high_scores(self):
        try:
            HIGH_SCORE_FILE.write_text(json.dumps(self.high_scores, indent=2),
                                       encoding="utf-8")
        except OSError:
            self.status_label.config(text="Could not save high scores file.")

    def refresh_leaderboard(self):
        if not self.high_scores:
            text = "No scores yet.\nPlay a game to set a record!"
        else:
            lines = []
            for i, item in enumerate(self.high_scores[:5], 1):
                lines.append(f"{i}. {item['score']} pts  |  {item['duration']}s")
                lines.append(f"   {item['date']}")
            text = "\n".join(lines)
        self.leaderboard.config(text=text)

    def draw_idle_screen(self):
        self.canvas.delete("all")
        self.canvas.create_text(WIDTH/2, 210, text="READY TO POP?",
                                fill="white", font=("Arial", 30, "bold"))
        self.canvas.create_text(WIDTH/2, 265,
                                text="Bubbles rise from the bottom. Aim and pinch to shoot!",
                                fill="#b9c7dc", font=("Arial", 14))
        for x, y, r, c in [(180, 450, 20, COLORS[0]), (310, 510, 40, COLORS[1]),
                           (480, 430, 28, COLORS[2]), (650, 500, 55, COLORS[3]),
                           (770, 420, 16, COLORS[4])]:
            self.canvas.create_oval(x-r, y-r, x+r, y+r, fill=c, outline="white", width=2)

    def start_game(self):
        if self.running:
            return
        self.running = True
        self.game_over = False
        self.score = 0
        self.shots = 0
        self.hit_counts = {"Small": 0, "Medium": 0, "Large": 0, "Extra large": 0}
        self.bubbles.clear()
        self.shots_list.clear()
        self.start_time = time.monotonic()
        self.last_spawn = self.start_time
        self.last_report = 0
        self.start_button.config(state="disabled")
        self.report_label.config(text="Game started! First report in 30 seconds.")
        self.status_label.config(text="Point with index finger; pinch thumb and index to shoot.")
        self.update_labels()

    def mouse_shoot(self, event):
        if self.running:
            self.fire_shot(event.x, event.y)

    def fire_shot(self, target_x, target_y):
        if not self.running:
            return
        self.shots += 1
        self.shots_list.append(Shot(WIDTH / 2, HEIGHT - 35, target_x, target_y))

    def update_labels(self):
        self.score_label.config(text=f"Score: {self.score}")
        if self.running:
            elapsed = time.monotonic() - self.start_time
            remaining = max(0, int(GAME_SECONDS - elapsed + 0.999))
            self.time_label.config(text=f"Time: {remaining}s")

    def show_report(self, elapsed):
        total_hits = sum(self.hit_counts.values())
        report = (f"At {int(elapsed)} seconds\n"
                  f"Score: {self.score}\n"
                  f"Hits: {total_hits} / Shots: {self.shots}\n"
                  f"Small: {self.hit_counts['Small']}  "
                  f"Medium: {self.hit_counts['Medium']}\n"
                  f"Large: {self.hit_counts['Large']}  "
                  f"XL: {self.hit_counts['Extra large']}")
        self.report_label.config(text=report)
        self.status_label.config(text=f"30-second score report: {self.score} points.")

    def end_game(self):
        self.running = False
        self.game_over = True
        played = int(time.monotonic() - self.start_time)
        record = {
            "score": self.score,
            "duration": played,
            "date": datetime.now().strftime("%d %b %Y %H:%M:%S")
        }
        self.high_scores.append(record)
        self.high_scores.sort(key=lambda x: x.get("score", 0), reverse=True)
        self.high_scores = self.high_scores[:10]
        self.save_high_scores()
        self.refresh_leaderboard()
        self.start_button.config(state="normal")
        self.status_label.config(text=f"Game over! Final score: {self.score}.")
        self.report_label.config(
            text=f"FINAL REPORT\nScore: {self.score}\nTime: {played}s\n"
                 f"Shots: {self.shots}\nHits: {sum(self.hit_counts.values())}\n"
                 f"Small: {self.hit_counts['Small']}  Medium: {self.hit_counts['Medium']}\n"
                 f"Large: {self.hit_counts['Large']}  XL: {self.hit_counts['Extra large']}"
        )
        self.canvas.create_rectangle(245, 220, 655, 390, fill="#101522",
                                     outline="#ffd166", width=3)
        self.canvas.create_text(WIDTH/2, 270, text="TIME'S UP!",
                                fill="#ffd166", font=("Arial", 30, "bold"))
        self.canvas.create_text(WIDTH/2, 325, text=f"FINAL SCORE: {self.score}",
                                fill="white", font=("Arial", 22, "bold"))
        self.canvas.create_text(WIDTH/2, 360, text="Press START GAME to play again",
                                fill="#b9c7dc", font=("Arial", 12))

    def update_loop(self):
        frame, aim, shoot = self.tracker.read()
        self.last_aim = aim

        if frame is not None:
            try:
                # Larger webcam preview (width x height).
                small = cv2.resize(frame, (1100, 725), interpolation=cv2.INTER_AREA)
                image = Image.fromarray(small)
                self.camera_photo = ImageTk.PhotoImage(image)
                self.camera_label.config(image=self.camera_photo, text="")
            except Exception:
                pass
        elif self.tracker.error:
            self.camera_label.config(text=self.tracker.error, image="")

        if self.running:
            now = time.monotonic()
            elapsed = now - self.start_time
            if elapsed >= GAME_SECONDS:
                self.update_labels()
                self.end_game()
            else:
                if shoot:
                    self.fire_shot(*aim)

                if now - self.last_spawn >= 0.85:
                    self.bubbles.append(Bubble())
                    self.last_spawn = now

                if elapsed >= REPORT_EVERY and self.last_report < REPORT_EVERY:
                    self.show_report(elapsed)
                    self.last_report = REPORT_EVERY

                for bubble in self.bubbles:
                    bubble.y -= bubble.speed
                self.bubbles = [b for b in self.bubbles if b.y + b.radius > -10]

                for shot in self.shots_list:
                    shot.x += shot.vx
                    shot.y += shot.vy
                self.shots_list = [s for s in self.shots_list
                                   if -20 < s.x < WIDTH+20 and -20 < s.y < HEIGHT+20]

                # Detect projectile-to-bubble collisions.
                remaining_shots = []
                for shot in self.shots_list:
                    hit_index = None
                    for i, bubble in enumerate(self.bubbles):
                        if math.hypot(shot.x - bubble.x, shot.y - bubble.y) <= bubble.radius + shot.radius:
                            hit_index = i
                            break
                    if hit_index is not None:
                        bubble = self.bubbles.pop(hit_index)
                        self.score += bubble.points
                        if bubble.radius <= 20:
                            self.hit_counts["Small"] += 1
                        elif bubble.radius <= 32:
                            self.hit_counts["Medium"] += 1
                        elif bubble.radius <= 46:
                            self.hit_counts["Large"] += 1
                        else:
                            self.hit_counts["Extra large"] += 1
                    else:
                        remaining_shots.append(shot)
                self.shots_list = remaining_shots

                self.update_labels()

        self.draw_game()
        self.root.after(25, self.update_loop)

    def draw_game(self):
        self.canvas.delete("all")
        # Subtle guide line and launcher.
        self.canvas.create_line(0, HEIGHT-1, WIDTH, HEIGHT-1, fill="#344563")
        self.canvas.create_oval(WIDTH/2-18, HEIGHT-18, WIDTH/2+18, HEIGHT+18,
                                fill="#e6edf7", outline="#7ee7ff", width=2)
        for bubble in self.bubbles:
            r = bubble.radius
            self.canvas.create_oval(bubble.x-r, bubble.y-r, bubble.x+r, bubble.y+r,
                                    fill=bubble.color, outline="white", width=2)
            self.canvas.create_oval(bubble.x-r*0.55, bubble.y-r*0.65,
                                    bubble.x-r*0.15, bubble.y-r*0.25,
                                    fill="#ffffff", outline="")
            self.canvas.create_text(bubble.x, bubble.y, text=str(bubble.points),
                                    fill="#101522", font=("Arial", max(8, r//2), "bold"))
        for shot in self.shots_list:
            self.canvas.create_oval(shot.x-7, shot.y-7, shot.x+7, shot.y+7,
                                    fill="#ffffff", outline="#7ee7ff", width=2)

        ax, ay = self.last_aim
        if self.running:
            self.canvas.create_line(WIDTH/2, HEIGHT-35, ax, ay,
                                    fill="#7ee7ff", width=2, dash=(5, 4))
            self.canvas.create_oval(ax-11, ay-11, ax+11, ay+11,
                                    outline="#ffffff", width=2)
            self.canvas.create_text(12, 12, anchor="nw",
                                    text="AIM: INDEX FINGER  |  SHOOT: PINCH",
                                    fill="#b9c7dc", font=("Arial", 10, "bold"))

    def quit(self):
        self.tracker.close()
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    app = BubbleShooter(root)
    root.mainloop()
