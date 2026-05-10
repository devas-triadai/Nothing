import logging
from typing import List, Union
import numpy as np
from PIL import Image

logger = logging.getLogger("agra.clip")

_clip_model = None
_clip_processor = None

def load_clip():
    """Lazy load CLIP model for cross-modal retrieval."""
    global _clip_model, _clip_processor
    if _clip_model is None:
        try:
            from transformers import CLIPProcessor, CLIPModel
            logger.info("Loading CLIP model (openai/clip-vit-base-patch32) for cross-modal search...")
            _clip_model = CLIPModel.from_pretrained("openai/clip-vit-base-patch32")
            _clip_processor = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32")
            logger.info("CLIP model loaded successfully.")
        except Exception as e:
            logger.error("Failed to load CLIP model: %s", e)

def embed_image(image_path: str) -> List[float]:
    """Embed an image into a 512D vector."""
    load_clip()
    if not _clip_model:
        return []
        
    try:
        image = Image.open(image_path).convert("RGB")
        inputs = _clip_processor(images=image, return_tensors="pt")
        image_features = _clip_model.get_image_features(**inputs)
        image_features = image_features / image_features.norm(p=2, dim=-1, keepdim=True)
        return image_features.squeeze(0).detach().numpy().tolist()
    except Exception as e:
        logger.error("Error embedding image %s: %s", image_path, e)
        return []

def embed_text_for_image_search(text: str) -> List[float]:
    """Embed a text query into a 512D vector for image retrieval."""
    load_clip()
    if not _clip_model:
        return []
        
    try:
        inputs = _clip_processor(text=[text], return_tensors="pt", padding=True, truncation=True)
        text_features = _clip_model.get_text_features(**inputs)
        text_features = text_features / text_features.norm(p=2, dim=-1, keepdim=True)
        return text_features.squeeze(0).detach().numpy().tolist()
    except Exception as e:
        logger.error("Error embedding text for CLIP: %s", e)
        return []
