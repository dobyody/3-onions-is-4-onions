"""Find the ROI (x,y,w,h) of the blinking patch in a phone clip.

Automatic: pixels whose brightness changes most over time are the patch.
    python3 04-demo/roi.py --video clips/A-01.mov
Manual (draw a box with the mouse, then press Enter):
    python3 04-demo/roi.py --video clips/A-01.mov --pick

Prints the ROI and writes <video>.roi.png so you can check it by eye.
"""
import argparse
import sys

import cv2
import numpy as np


def auto_roi(video, max_frames=900, step=2, shrink=0.15):
    cap = cv2.VideoCapture(video)
    if not cap.isOpened():
        sys.exit("cannot open " + video)
    s = s2 = None
    n = i = 0
    first = None
    while n < max_frames:
        ok, f = cap.read()
        if not ok:
            break
        i += 1
        if i % step:
            continue
        g = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY).astype(np.float32)
        if first is None:
            first = f
            s = np.zeros_like(g)
            s2 = np.zeros_like(g)
        s += g
        s2 += g * g
        n += 1
    cap.release()
    if n < 10:
        sys.exit("clip too short to find the patch automatically; use --pick")
    std = np.sqrt(np.maximum(s2 / n - (s / n) ** 2, 0))
    std = cv2.GaussianBlur(std, (0, 0), 5)
    mask = (std > 0.5 * std.max()).astype(np.uint8)
    cnt, lab, stats, _ = cv2.connectedComponentsWithStats(mask)
    if cnt < 2:
        sys.exit("no blinking area found; use --pick")
    k = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    x, y, w, h = [int(v) for v in stats[k, :4]]
    # stay inside the patch, away from blurry edges
    dx, dy = int(w * shrink), int(h * shrink)
    return first, (x + dx, y + dy, max(1, w - 2 * dx), max(1, h - 2 * dy))


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--video", required=True)
    p.add_argument("--pick", action="store_true", help="draw the ROI by hand")
    a = p.parse_args()

    if a.pick:
        cap = cv2.VideoCapture(a.video)
        cap.set(cv2.CAP_PROP_POS_FRAMES, 30)
        ok, first = cap.read()
        cap.release()
        if not ok:
            sys.exit("cannot read " + a.video)
        h0, w0 = first.shape[:2]
        scale = min(1.0, 1200.0 / max(h0, w0))
        small = cv2.resize(first, None, fx=scale, fy=scale)
        r = cv2.selectROI("Draw the patch, then Enter", small, showCrosshair=True)
        cv2.destroyAllWindows()
        roi = tuple(int(round(v / scale)) for v in r)
        if roi[2] == 0 or roi[3] == 0:
            sys.exit("no ROI selected")
    else:
        first, roi = auto_roi(a.video)

    x, y, w, h = roi
    prev = first.copy()
    cv2.rectangle(prev, (x, y), (x + w, y + h), (0, 0, 255), max(2, prev.shape[1] // 300))
    cv2.imwrite(a.video + ".roi.png", prev)
    print("frame size: %dx%d" % (first.shape[1], first.shape[0]))
    print("ROI: %d,%d,%d,%d" % roi)
    print("check: open \"%s.roi.png\"" % a.video)


if __name__ == "__main__":
    main()
