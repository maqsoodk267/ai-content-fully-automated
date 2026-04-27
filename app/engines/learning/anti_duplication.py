"""
AntiDuplicationEngine — prevents duplicate text/image/video posts.

Text: Sentence Transformers embeddings + vector similarity search.
Image: average-hash perceptual fingerprint.
Video: frame-grab perceptual hash via ffmpeg if available.
Persistence: Vector DB (Chroma/Qdrant) for text, in-memory LRU for images/videos.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import tempfile
import uuid
from collections import OrderedDict
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from app.core.vector_db import get_vector_db, get_embedding_model
from app.engines.base import BaseEngine


def _probe_duration(path: str) -> float:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe or not os.path.exists(path):
        return 0.0
    try:
        out = subprocess.check_output(
            [ffprobe, "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", path],
            stderr=subprocess.DEVNULL, timeout=15,
        ).decode().strip()
        return float(out or 0.0)
    except Exception:
        return 0.0


def _normalize(text: str) -> str:
    import re
    text = (text or "").lower()
    text = re.sub(r"http\S+", "", text)
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


class AntiDuplicationEngine(BaseEngine):
    name = "anti_duplication"
    description = "Detect duplicate text/image/video against history"

    def __init__(self, history_size: int = 5000):
        super().__init__()
        self._image_hashes: OrderedDict[str, int] = OrderedDict()
        self._video_hashes: OrderedDict[str, int] = OrderedDict()
        self._text_hashes: set[str] = set()
        self._cap = history_size
        self._vector_db = None
        self._embedding_model = None
        self._collection_name = "text_duplicates"
        self._init_vector_db()

    def _init_vector_db(self) -> None:
        try:
            self._vector_db = get_vector_db()
            self._embedding_model = get_embedding_model()
            if hasattr(self._vector_db, "create_collection"):
                try:
                    self._vector_db.create_collection(name=self._collection_name)
                except Exception:
                    pass
        except Exception as exc:
            self.logger.warning("Vector DB initialization failed: %s", exc)
            self._vector_db = None
            self._embedding_model = None

    def run(self, kind: str = "text", **kwargs: Any) -> Dict[str, Any]:
        if kind == "text":
            return self.check_text(
                kwargs.get("text", ""),
                threshold=kwargs.get("threshold", 0.88),
                register=kwargs.get("register", True),
                account_id=kwargs.get("account_id"),
                cross_account=kwargs.get("cross_account", True),
                category=kwargs.get("category"),
                platform=kwargs.get("platform"),
            )
        if kind == "image":
            return self.check_image(
                kwargs.get("path", ""),
                threshold=kwargs.get("threshold", 6),
                register=kwargs.get("register", True),
            )
        if kind == "video":
            return self.check_video(
                kwargs.get("path", ""),
                threshold=kwargs.get("threshold", 8),
                register=kwargs.get("register", True),
            )
        if kind == "before_generation":
            return self.check_before_generation(
                kwargs.get("script", ""),
                kwargs.get("category", ""),
                kwargs.get("platform", ""),
                account_id=kwargs.get("account_id"),
                check_window_days=kwargs.get("check_window_days", 30),
            )
        raise ValueError("kind must be text|image|video|before_generation")

    # ------------------------------------------------------------------
    def check_text(
        self,
        text: str,
        *,
        threshold: float = 0.88,
        register: bool = True,
        account_id: Optional[str] = None,
        cross_account: bool = True,
        category: Optional[str] = None,
        platform: Optional[str] = None,
    ) -> Dict[str, Any]:
        normalized = _normalize(text)
        if not normalized:
            return {"is_duplicate": False, "reason": "empty"}

        if self._embedding_model and self._vector_db:
            return self._check_text_vector(normalized, threshold, register, account_id, cross_account, category, platform)
        return self._check_text_hash(normalized, threshold, register)

    def _check_text_vector(
        self,
        text: str,
        threshold: float,
        register: bool,
        account_id: Optional[str],
        cross_account: bool,
        category: Optional[str],
        platform: Optional[str],
    ) -> Dict[str, Any]:
        try:
            embedding = self._embedding_model.encode([text])[0].tolist()
            metadata = {"account_id": account_id} if account_id else {}
            if category:
                metadata["category"] = category
            if platform:
                metadata["platform"] = platform
            metadata["timestamp"] = datetime.utcnow().isoformat()
            query_kwargs: Dict[str, Any] = {}

            if hasattr(self._vector_db, "query"):
                if not cross_account and account_id:
                    query_kwargs["where"] = {"account_id": account_id}
                results = self._vector_db.query(
                    collection_name=self._collection_name,
                    query_embeddings=[embedding],
                    n_results=5,
                    **query_kwargs,
                )
                if results and results.get("distances"):
                    min_distance = min(results["distances"][0])
                    similarity = max(0.0, min(1.0, 1 - min_distance))
                    is_dup = similarity >= threshold
                    match_id = results["ids"][0][0] if results.get("ids") and results["ids"][0] else None
                    if register and not is_dup:
                        doc_id = str(uuid.uuid4())
                        add_kwargs = {"collection_name": self._collection_name,
                                      "embeddings": [embedding],
                                      "documents": [text],
                                      "ids": [doc_id]}
                        if metadata:
                            add_kwargs["metadatas"] = [metadata]
                        self._vector_db.add(**add_kwargs)
                    return {
                        "is_duplicate": is_dup,
                        "similarity": round(similarity, 4),
                        "match_id": match_id if is_dup else None,
                        "threshold": threshold,
                        "method": "chroma",
                    }
            elif hasattr(self._vector_db, "search"):
                try:
                    from qdrant_client.models import Filter, FieldCondition, MatchValue
                except Exception:
                    Filter = None
                if not cross_account and account_id and Filter is not None:
                    query_filter = Filter(must=[
                        FieldCondition(key="account_id", match=MatchValue(value=account_id))
                    ])
                else:
                    query_filter = None
                results = self._vector_db.search(
                    collection_name=self._collection_name,
                    query_vector=embedding,
                    limit=5,
                    query_filter=query_filter,
                )
                if results:
                    best = max(results, key=lambda item: getattr(item, "score", 0.0))
                    similarity = getattr(best, "score", 0.0)
                    similarity = max(0.0, min(1.0, similarity))
                    is_dup = similarity >= threshold
                    match_id = getattr(best, "id", None)
                    if register and not is_dup:
                        doc_id = str(uuid.uuid4())
                        point = {
                            "id": doc_id,
                            "vector": embedding,
                            "payload": {
                                "text": text,
                                "timestamp": datetime.utcnow().timestamp(),
                                **({"account_id": account_id} if account_id else {}),
                                **({"category": category} if category else {}),
                                **({"platform": platform} if platform else {}),
                            },
                        }
                        self._vector_db.upsert(collection_name=self._collection_name, points=[point])
                    return {
                        "is_duplicate": is_dup,
                        "similarity": round(similarity, 4),
                        "match_id": match_id if is_dup else None,
                        "threshold": threshold,
                        "method": "qdrant",
                    }
        except Exception as exc:
            self.logger.warning("Vector search failed: %s", exc)

        return self._check_text_hash(text, threshold, register)

    def _check_text_hash(self, text: str, threshold: float, register: bool) -> Dict[str, Any]:
        digest = hashlib.sha1(text.encode()).hexdigest()
        is_dup = digest in self._text_hashes
        if register and not is_dup:
            self._text_hashes.add(digest)
        return {
            "is_duplicate": is_dup,
            "similarity": 1.0 if is_dup else 0.0,
            "match_id": digest if is_dup else None,
            "threshold": threshold,
            "method": "hash_fallback",
        }

    def check_image(self, path: str, *, threshold: int = 6,
                    register: bool = True) -> Dict[str, Any]:
        if not os.path.exists(path):
            return {"is_duplicate": False, "reason": "missing_file"}
        ahash = self._average_hash(path)
        best_id, best_dist = None, 64
        for iid, prior in self._image_hashes.items():
            dist = bin(ahash ^ prior).count("1")
            if dist < best_dist:
                best_dist, best_id = dist, iid
        is_dup = best_dist <= threshold
        if register and not is_dup:
            new_id = hashlib.sha1(path.encode()).hexdigest()[:10]
            self._image_hashes[new_id] = ahash
            self._evict()
        return {
            "is_duplicate": is_dup,
            "hamming_distance": best_dist,
            "match_id": best_id if is_dup else None,
            "threshold": threshold,
            "method": "image_hash",
        }

    def check_video(self, path: str, *, threshold: int = 32,
                    register: bool = True) -> Dict[str, Any]:
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            return {"is_duplicate": False, "reason": "ffmpeg_missing"}
        if not os.path.exists(path):
            return {"is_duplicate": False, "reason": "missing_file"}
        
        fingerprint = self._video_fingerprint(path)
        if fingerprint is None:
            return {"is_duplicate": False, "reason": "fingerprint_failed"}
        
        best_id, best_dist = None, 320  # max possible for 5 frames * 64 bits
        for vid, prior in self._video_hashes.items():
            dist = bin(fingerprint ^ prior).count("1")
            if dist < best_dist:
                best_dist, best_id = dist, vid
        is_dup = best_dist <= threshold
        if register and not is_dup:
            new_id = hashlib.sha1(path.encode()).hexdigest()[:10]
            self._video_hashes[new_id] = fingerprint
            self._evict()
        return {
            "is_duplicate": is_dup,
            "hamming_distance": best_dist,
            "match_id": best_id if is_dup else None,
            "threshold": threshold,
            "method": "video_fingerprint",
        }

    def check_before_generation(
        self,
        script: str,
        category: str,
        platform: str,
        account_id: Optional[str] = None,
        check_window_days: int = 30,
    ) -> Dict[str, Any]:
        """
        Check if similar content already published recently.
        Returns {'is_duplicate': bool, 'similarity': float, 'existing_id': str}
        """
        normalized = _normalize(script)
        if not normalized:
            return {"is_duplicate": False, "similarity": 0.0, "existing_id": None}

        if not self._embedding_model or not self._vector_db:
            # Fallback to simple hash check
            return self._check_recent_hash(normalized, account_id, check_window_days)

        try:
            embedding = self._embedding_model.encode([normalized])[0].tolist()
            cutoff_date = datetime.utcnow() - timedelta(days=check_window_days)
            
            query_kwargs: Dict[str, Any] = {"n_results": 10}
            
            if hasattr(self._vector_db, "query"):
                # Chroma
                where_conditions = {"$and": []}
                if account_id:
                    where_conditions["$and"].append({"account_id": account_id})
                where_conditions["$and"].append({"timestamp": {"$gte": cutoff_date.isoformat()}})
                if category:
                    where_conditions["$and"].append({"category": category})
                if platform:
                    where_conditions["$and"].append({"platform": platform})
                query_kwargs["where"] = where_conditions
                
                results = self._vector_db.query(
                    collection_name=self._collection_name,
                    query_embeddings=[embedding],
                    **query_kwargs,
                )
                if results and results.get("distances"):
                    min_distance = min(results["distances"][0])
                    similarity = max(0.0, min(1.0, 1 - min_distance))
                    is_dup = similarity >= 0.88
                    match_id = results["ids"][0][0] if results.get("ids") and results["ids"][0] else None
                    return {
                        "is_duplicate": is_dup,
                        "similarity": round(similarity, 4),
                        "existing_id": match_id,
                        "method": "vector_recent",
                    }
            elif hasattr(self._vector_db, "search"):
                # Qdrant
                try:
                    from qdrant_client.models import Filter, FieldCondition, MatchValue, Range
                except Exception:
                    Filter = None
                if Filter:
                    conditions = []
                    if account_id:
                        conditions.append(FieldCondition(key="account_id", match=MatchValue(value=account_id)))
                    conditions.append(FieldCondition(key="timestamp", range=Range(gte=cutoff_date.timestamp())))
                    if category:
                        conditions.append(FieldCondition(key="category", match=MatchValue(value=category)))
                    if platform:
                        conditions.append(FieldCondition(key="platform", match=MatchValue(value=platform)))
                    query_filter = Filter(must=conditions)
                    query_kwargs["query_filter"] = query_filter
                
                results = self._vector_db.search(
                    collection_name=self._collection_name,
                    query_vector=embedding,
                    **query_kwargs,
                )
                if results:
                    best = max(results, key=lambda item: getattr(item, "score", 0.0))
                    similarity = getattr(best, "score", 0.0)
                    similarity = max(0.0, min(1.0, similarity))
                    is_dup = similarity >= 0.88
                    match_id = getattr(best, "id", None)
                    return {
                        "is_duplicate": is_dup,
                        "similarity": round(similarity, 4),
                        "existing_id": match_id,
                        "method": "vector_recent",
                    }
        except Exception as exc:
            self.logger.warning("Vector search for recent content failed: %s", exc)

        return self._check_recent_hash(normalized, account_id, check_window_days)

    def _check_recent_hash(self, text: str, account_id: Optional[str], check_window_days: int) -> Dict[str, Any]:
        # Simple fallback: check if exact hash exists (assuming recent registration)
        digest = hashlib.sha1(text.encode()).hexdigest()
        # For simplicity, assume registered content is recent
        is_dup = digest in self._text_hashes
        return {
            "is_duplicate": is_dup,
            "similarity": 1.0 if is_dup else 0.0,
            "existing_id": digest if is_dup else None,
            "method": "hash_recent_fallback",
        }

    def _video_fingerprint(self, path: str, num_frames: int = 5) -> Optional[int]:
        """Extract perceptual hash from multiple frames and combine."""
        duration = _probe_duration(path)
        if duration <= 0:
            return None
        
        frames = []
        for i in range(num_frames):
            timestamp = (duration / (num_frames + 1)) * (i + 1)
            frame_hash = self._extract_frame_hash(path, timestamp)
            if frame_hash is None:
                continue
            frames.append(frame_hash)
        
        if not frames:
            return None
        
        # Combine: concatenate as binary strings, then to int
        combined_bits = ''.join(bin(h)[2:].zfill(64) for h in frames)
        # Since 5*64=320 bits, too big for int, use hashlib.sha256
        combined = hashlib.sha256(combined_bits.encode()).hexdigest()
        # Convert hex to int for hamming distance
        return int(combined, 16)

    def _extract_frame_hash(self, path: str, timestamp: float) -> Optional[int]:
        """Extract single frame hash using FFmpeg."""
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            return None
        
        with tempfile.TemporaryDirectory() as tmp:
            frame = os.path.join(tmp, "f.png")
            try:
                subprocess.run(
                    [ffmpeg, "-y", "-ss", str(timestamp), "-i", path, "-frames:v", "1", frame],
                    check=True, capture_output=True, timeout=30,
                )
            except Exception:
                return None
            return self._average_hash(frame)

    # ------------------------------------------------------------------
    @staticmethod
    def _average_hash(path: str, size: int = 8) -> int:
        from PIL import Image

        img = Image.open(path).convert("L").resize((size, size), Image.LANCZOS)
        pixels = list(img.getdata())
        avg = sum(pixels) / len(pixels)
        bits = 0
        for i, p in enumerate(pixels):
            if p > avg:
                bits |= 1 << i
        return bits

    def _evict(self) -> None:
        for store in (self._image_hashes, self._video_hashes):
            while len(store) > self._cap:
                store.popitem(last=False)
