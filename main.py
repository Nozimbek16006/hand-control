import cv2
import pyautogui
import numpy as np
import mediapipe as mp
import sys
import os

# Pyautogui tezlik va xavfsizlik sozlamalari
pyautogui.PAUSE = 0
pyautogui.FAILSAFE = False


class SoloHandMaster:
    def __init__(self):
        self.cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
        self.cap.set(3, 640)
        self.cap.set(4, 480)

        self.mp_hands = mp.solutions.hands
        # FAQAT BITTA QO'LNI ANIQLASH
        self.hands = self.mp_hands.Hands(
            max_num_hands=1,
            model_complexity=0,
            min_detection_confidence=0.8,
            min_tracking_confidence=0.8
        )
        self.mp_draw = mp.solutions.drawing_utils

        self.screen_w, self.screen_h = pyautogui.size()
        self.plocX, self.plocY = 0, 0
        self.l_clicked = False
        self.r_clicked = False
        self.smoothing = 4
        self.win_name = "Nozim AI - Solo Hand"
        self.prev_y8 = 0

    def start(self):
        cv2.namedWindow(self.win_name, cv2.WINDOW_NORMAL)
        cv2.setWindowProperty(self.win_name, cv2.WND_PROP_TOPMOST, 1)
        cv2.resizeWindow(self.win_name, 280, 210)

        while True:
            # X TUGMASI BILAN TO'LIQ CHIQISH
            if cv2.getWindowProperty(self.win_name, cv2.WND_PROP_VISIBLE) < 1:
                break

            success, img = self.cap.read()
            if not success: break
            img = cv2.flip(img, 1)
            h, w, _ = img.shape
            results = self.hands.process(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))

            if results.multi_hand_landmarks:
                lms = results.multi_hand_landmarks[0].landmark

                # Koordinata olish
                def get_c(i):
                    return int(lms[i].x * w), int(lms[i].y * h)

                x4, y4 = get_c(4)  # Bosh barmoq
                x8, y8 = get_c(8)  # Ko'rsatkich
                x12, y12 = get_c(12)  # O'rta
                x20, y20 = get_c(20)  # Jimjiloq (Kursor)
                x5, y5 = get_c(5)  # Ko'rsatkich asosi
                x0, y0 = get_c(0)  # Bilak

                limit = np.hypot(x5 - x0, y5 - y0) * 0.4

                # 1. KURSOR (Jimjiloq)
                fx = np.interp(x20, (120, w - 120), (0, self.screen_w))
                fy = np.interp(y20, (120, h - 120), (0, self.screen_h))
                self.plocX += (fx - self.plocX) / self.smoothing
                self.plocY += (fy - self.plocY) / self.smoothing
                pyautogui.moveTo(self.plocX, self.plocY, _pause=False)

                # 2. CHAP CLICK / BURCHAKDAN USHLASH (Bosh+Ko'rsatkich)
                # Oynani burchagidan ushlab tortish uchun kursorni burchakka qo'yib, barmoqlarni yoping
                if np.hypot(x4 - x8, y4 - y8) < limit:
                    if not self.l_clicked:
                        pyautogui.mouseDown(button='left')
                        self.l_clicked = True
                    cv2.circle(img, (x8, y8), 15, (0, 255, 0), cv2.FILLED)
                else:
                    if self.l_clicked:
                        pyautogui.mouseUp(button='left')
                        self.l_clicked = False

                # 3. O'NG CLICK (Bosh+O'rta)
                if np.hypot(x4 - x12, y4 - y12) < limit:
                    if not self.r_clicked:
                        pyautogui.click(button='right')
                        self.r_clicked = True
                else:
                    self.r_clicked = False

                # 4. SCROLL (Ko'rsatkich+O'rta birlashsa)
                if np.hypot(x8 - x12, y8 - y12) < limit * 0.7:
                    if y8 < 180:
                        pyautogui.scroll(120)
                    elif y8 > 300:
                        pyautogui.scroll(-120)

                # 5. OVOZ (O'rta yopiq + Ko'rsatkich harakati)
                if lms[12].y > lms[10].y:
                    if y8 < self.prev_y8 - 12:
                        pyautogui.press('volumeup')
                    elif y8 > self.prev_y8 + 12:
                        pyautogui.press('volumedown')
                self.prev_y8 = y8

                self.mp_draw.draw_landmarks(img, results.multi_hand_landmarks[0], self.mp_hands.HAND_CONNECTIONS)

            cv2.imshow(self.win_name, img)
            if cv2.waitKey(1) & 0xFF == ord('q'): break

        self.cap.release()
        cv2.destroyAllWindows()
        os._exit(0)


if __name__ == "__main__":
    try:
        SoloHandMaster().start()
    except Exception:
        os._exit(0)