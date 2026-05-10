import cv2
import numpy as np
import base64
import io
from PIL import Image

def preprocess_engineering_drawing(data_uri: str) -> str:
    """
    OpenCV preprocessing pipeline for engineering drawings:
    1. Grayscale
    2. Denoise
    3. Adaptive Thresholding (Binarize)
    4. Deskew
    Takes a base64 data URI and returns a processed base64 data URI.
    """
    if data_uri.startswith("data:"):
        header, encoded = data_uri.split(",", 1)
    else:
        encoded = data_uri
        
    image_bytes = base64.b64decode(encoded)
    np_arr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
    
    if img is None:
        return data_uri  # fallback to original if decode fails

    # 1. Grayscale
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # 2. Denoise
    denoised = cv2.fastNlMeansDenoising(gray, h=30)

    # 3. Binarize (Adaptive Thresholding)
    binarized = cv2.adaptiveThreshold(
        denoised, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2
    )

    # 4. Deskew
    coords = np.column_stack(np.where(binarized > 0))
    angle = cv2.minAreaRect(coords)[-1]
    if angle < -45:
        angle = -(90 + angle)
    else:
        angle = -angle

    (h, w) = binarized.shape[:2]
    center = (w // 2, h // 2)
    M = cv2.getRotationMatrix2D(center, angle, 1.0)
    rotated = cv2.warpAffine(binarized, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)

    # Convert back to PIL Image and then base64
    pil_img = Image.fromarray(rotated)
    buffered = io.BytesIO()
    pil_img.save(buffered, format="JPEG")
    img_str = base64.b64encode(buffered.getvalue()).decode("utf-8")
    
    return f"data:image/jpeg;base64,{img_str}"
