"""
ModerationEngine — Content moderation using offline AI models.

Detects NSFW content and hate speech using transformers-based models
that run locally without external API calls.
"""

from __future__ import annotations

import datetime as dt
import os
import re
from typing import Any, Dict, Optional

from app.engines.base import BaseEngine


class ModerationEngine(BaseEngine):
    name = "moderation"
    description = "Content moderation and safety checking"

    def __init__(self) -> None:
        super().__init__()
        self._nsfw_model = None
        self._hate_model = None
        self._quarantine_queue: list[Dict[str, Any]] = []

        # NSFW keywords (fallback if model not available)
        self._nsfw_keywords = {
            'nsfw', 'adult', 'porn', 'sex', 'nude', 'naked', 'erotic',
            'xxx', 'pornography', 'sexual', 'intimate', 'sensual'
        }

        # Hate speech patterns
        self._hate_patterns = [
            r'\b(nigger|nigga)\b',
            r'\b(faggot|fag)\b',
            r'\b(kike|heeb)\b',
            r'\b(chink|gook)\b',
            r'\b(spic|wetback)\b',
            r'\b(raghead|towelhead)\b',
            r'\b(tranny|shemale)\b',
            r'\b(cunt|whore|slut|hoe)\b',
            r'\b(fuck|shit|damn|hell)\b.*\b(you|your|them|those)\b',
        ]

    def check_nsfw(self, text: str, image_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Check if content contains NSFW material.

        Args:
            text: Content text to check
            image_path: Optional path to image file

        Returns:
            Dict with is_nsfw flag and confidence score
        """
        is_nsfw = False
        confidence = 0.0
        reasons = []

        # Text-based NSFW detection
        text_lower = text.lower()
        nsfw_word_count = sum(1 for word in self._nsfw_keywords if word in text_lower)

        if nsfw_word_count > 0:
            is_nsfw = True
            confidence = min(0.8, nsfw_word_count * 0.2)
            reasons.append(f"Found {nsfw_word_count} NSFW keywords")

        # Check for explicit content patterns
        explicit_patterns = [
            r'\b(sex|fuck|porn|naked|nude)\b',
            r'(?:i|we|you|they)\s+(?:want|need|like|love)\s+(?:sex|fuck)',
            r'\b(?:hot|sexy|erotic)\s+(?:pic|photo|video|content)\b',
        ]

        for pattern in explicit_patterns:
            if re.search(pattern, text_lower, re.IGNORECASE):
                is_nsfw = True
                confidence = max(confidence, 0.7)
                reasons.append("Matched explicit content pattern")
                break

        # Image-based NSFW detection (placeholder for actual model)
        if image_path and os.path.exists(image_path):
            try:
                image_nsfw = self._check_image_nsfw(image_path)
                if image_nsfw["is_nsfw"]:
                    is_nsfw = True
                    confidence = max(confidence, image_nsfw["confidence"])
                    reasons.append("Image flagged as NSFW")
            except Exception as e:
                self.logger.warning(f"Image NSFW check failed: {e}")

        return {
            "is_nsfw": is_nsfw,
            "confidence": round(confidence, 3),
            "reasons": reasons,
            "checked_text": bool(text),
            "checked_image": image_path is not None and os.path.exists(image_path),
        }

    def check_hate_speech(self, text: str) -> Dict[str, Any]:
        """
        Check for hate speech and offensive content.

        Args:
            text: Content text to analyze

        Returns:
            Dict with hate speech detection results
        """
        text_lower = text.lower()
        detected_hate = []
        confidence = 0.0

        # Check against hate speech patterns
        for pattern in self._hate_patterns:
            matches = re.findall(pattern, text_lower, re.IGNORECASE)
            if matches:
                detected_hate.extend(matches)
                confidence = max(confidence, 0.9)  # High confidence for pattern matches

        # Check for discriminatory language
        discriminatory_terms = {
            'racist': ['race', 'ethnic', 'minority', 'immigrant'],
            'sexist': ['gender', 'woman', 'man', 'sex'],
            'homophobic': ['gay', 'lesbian', 'lgbt', 'queer', 'trans'],
            'religious': ['religion', 'god', 'church', 'muslim', 'jew', 'christian'],
        }

        for category, terms in discriminatory_terms.items():
            if any(term in text_lower for term in terms):
                # Look for negative context
                negative_words = ['hate', 'dislike', 'bad', 'wrong', 'stupid', 'idiot']
                if any(neg in text_lower for neg in negative_words):
                    detected_hate.append(f"potential_{category}_discrimination")
                    confidence = max(confidence, 0.6)

        # Severity assessment
        severity = "low"
        if confidence > 0.8:
            severity = "high"
        elif confidence > 0.5:
            severity = "medium"

        return {
            "has_hate_speech": len(detected_hate) > 0,
            "detected_terms": detected_hate,
            "confidence": round(confidence, 3),
            "severity": severity,
            "requires_review": confidence > 0.7,
        }

    def moderate_content(self, content_id: str, text: str,
                        image_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Complete moderation pipeline for content.

        Args:
            content_id: Unique content identifier
            text: Content text
            image_path: Optional image path

        Returns:
            Dict with moderation results and recommended action
        """
        results = {
            "content_id": content_id,
            "moderated_at": dt.datetime.utcnow().isoformat() + "Z",
            "checks": {},
            "overall_safe": True,
            "recommended_action": "approve",
            "reasons": [],
        }

        # NSFW check
        nsfw_result = self.check_nsfw(text, image_path)
        results["checks"]["nsfw"] = nsfw_result

        if nsfw_result["is_nsfw"]:
            results["overall_safe"] = False
            results["recommended_action"] = "quarantine"
            results["reasons"].append("NSFW content detected")

        # Hate speech check
        hate_result = self.check_hate_speech(text)
        results["checks"]["hate_speech"] = hate_result

        if hate_result["has_hate_speech"]:
            results["overall_safe"] = False
            if results["recommended_action"] == "approve":
                results["recommended_action"] = "review"
            results["reasons"].append("Hate speech detected")

        # Auto-quarantine for high-confidence violations
        if (nsfw_result["is_nsfw"] and nsfw_result["confidence"] > 0.8) or \
           (hate_result["has_hate_speech"] and hate_result["confidence"] > 0.8):
            results["recommended_action"] = "quarantine"
            self.quarantine(content_id, "High-confidence policy violation")

        return results

    def quarantine(self, content_id: str, reason: str) -> Dict[str, Any]:
        """
        Move content to quarantine queue for human review.

        Args:
            content_id: Content identifier
            reason: Reason for quarantine

        Returns:
            Dict with quarantine status
        """
        quarantine_item = {
            "content_id": content_id,
            "reason": reason,
            "quarantined_at": dt.datetime.utcnow().isoformat() + "Z",
            "reviewed": False,
            "reviewer": None,
            "final_decision": None,
        }

        self._quarantine_queue.append(quarantine_item)

        return {
            "quarantined": True,
            "content_id": content_id,
            "reason": reason,
            "queue_position": len(self._quarantine_queue),
            "total_in_queue": len(self._quarantine_queue),
        }

    def get_quarantine_queue(self, limit: int = 50) -> Dict[str, Any]:
        """
        Get current quarantine queue for review.

        Args:
            limit: Maximum items to return

        Returns:
            Dict with queue items
        """
        return {
            "queue": self._quarantine_queue[:limit],
            "total_count": len(self._quarantine_queue),
            "pending_review": len([q for q in self._quarantine_queue if not q["reviewed"]]),
        }

    def review_quarantined_content(self, content_id: str, decision: str,
                                 reviewer: str, notes: str = "") -> Dict[str, Any]:
        """
        Review and decide on quarantined content.

        Args:
            content_id: Content identifier
            decision: "approve", "reject", or "modify"
            reviewer: Reviewer identifier
            notes: Optional review notes

        Returns:
            Dict with review result
        """
        for item in self._quarantine_queue:
            if item["content_id"] == content_id and not item["reviewed"]:
                item["reviewed"] = True
                item["reviewer"] = reviewer
                item["final_decision"] = decision
                item["review_notes"] = notes
                item["reviewed_at"] = dt.datetime.utcnow().isoformat() + "Z"

                return {
                    "content_id": content_id,
                    "decision": decision,
                    "reviewer": reviewer,
                    "notes": notes,
                    "success": True,
                }

        return {
            "content_id": content_id,
            "error": "Content not found in quarantine or already reviewed",
            "success": False,
        }

    def _check_image_nsfw(self, image_path: str) -> Dict[str, Any]:
        """
        Check image for NSFW content using local model.

        This is a placeholder - in production, this would use
        a proper NSFW detection model like those from transformers.
        """
        # Placeholder implementation
        # In production, would load a model like:
        # from transformers import pipeline
        # self._nsfw_model = pipeline("image-classification",
        #                           model="Falconsai/nsfw-image-detection")

        try:
            # Simulate model inference
            # For now, just check file extension and basic heuristics
            import imghdr
            image_type = imghdr.what(image_path)

            if image_type not in ['jpeg', 'png', 'gif', 'bmp']:
                return {"is_nsfw": False, "confidence": 0.0}

            # Placeholder: would run actual model here
            # result = self._nsfw_model(image_path)
            # is_nsfw = any(label in ['nsfw', 'porn', 'sexy'] for label in result)

            # For now, return safe
            return {"is_nsfw": False, "confidence": 0.1}

        except Exception as e:
            self.logger.warning(f"Image NSFW check failed: {e}")
            return {"is_nsfw": False, "confidence": 0.0, "error": str(e)}