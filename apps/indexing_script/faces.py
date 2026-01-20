import cv2
import numpy as np

prototxt_path = "models/face_detector/deploy.prototxt.txt"
model_path = "models/face_detector/res10_300x300_ssd_iter_140000.caffemodel"

net = cv2.dnn.readNetFromCaffe(prototxt_path, model_path)

def detect_faces_dnn(image):
    (h, w) = image.shape[:2]

    blob = cv2.dnn.blobFromImage(
        cv2.resize(image, (300, 300)),
        scalefactor=1.0,
        size=(300, 300),
        mean=(104.0, 177.0, 123.0)
    )
    net.setInput(blob)
    detections = net.forward()

    boxes = []

    for i in range(0, detections.shape[2]):
        confidence = detections[0, 0, i, 2]
        if confidence < 0.5:
            continue

        box = detections[0, 0, i, 3:7] * np.array([w, h, w, h])
        (x1, y1, x2, y2) = box.astype("int")

        boxes.append({
            "confidence": float(confidence),
            "x": int(x1),
            "y": int(y1),
            "width": int(x2 - x1),
            "height": int(y2 - y1),
        })

    return boxes

# Example usage
image = cv2.imread("/mnt/photo/0 tmp/thumb1.jpg")
faces = detect_faces_dnn(image)

for f in faces:
    print(f)
    cv2.rectangle(
        image,
        (f["x"], f["y"]),
        (f["x"] + f["width"], f["y"] + f["height"]),
        (0, 255, 0),
        2
    )

cv2.imshow("DNN Faces", image)
cv2.waitKey(0)
cv2.destroyAllWindows()
