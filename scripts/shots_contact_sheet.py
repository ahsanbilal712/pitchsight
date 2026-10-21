import sys, cv2, numpy as np
from pathlib import Path
src, out = Path(sys.argv[1]), sys.argv[2]
imgs = []
for p in sorted(src.glob("shot_*.jpg")):
    im = cv2.imread(str(p)); cv2.putText(im, p.stem[9:], (4, 14), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 255), 1); imgs.append(im)
cols = 8
while len(imgs) % cols: imgs.append(np.zeros_like(imgs[0]))
rows = [np.hstack(imgs[i:i+cols]) for i in range(0, len(imgs), cols)]
cv2.imwrite(out, np.vstack(rows))
