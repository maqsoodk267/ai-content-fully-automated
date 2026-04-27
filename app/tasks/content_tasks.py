"""
Content generation tasks - AI-powered content creation.
"""

import logging
from datetime import datetime
from celery import shared_task
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models import Post, User
import random
import time

logger = logging.getLogger(__name__)


# ============================================================================
# Content Generation Task
# ============================================================================

@shared_task(bind=True, name='app.tasks.content_tasks.generate_content')
def generate_content(self, user_id: int, topic: str, content_type: str, 
                    platforms: list, tone: str = "professional", 
                    language: str = "english"):
    """
    Generate AI-powered content for user.
    
    Args:
        user_id: User ID
        topic: Content topic/keyword
        content_type: Type of content (reel, short, carousel, etc.)
        platforms: List of target platforms
        tone: Tone of content (professional, casual, funny, inspirational)
        language: Content language
    
    Returns:
        dict: Generated content with scripts, hooks, hashtags, captions
    """
    db = SessionLocal()
    
    try:
        self.update_state(state='PROCESSING', meta={'progress': 10})
        
        # Verify user exists
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise ValueError(f"User {user_id} not found")
        
        logger.info(f"Generating content for user {user_id}: {topic}")
        
        # Check for duplicate content before generation
        from app.engines import get_engine
        anti_dup_engine = get_engine("anti_duplication")
        
        # Use first platform for duplicate check (can be enhanced later)
        primary_platform = platforms[0] if platforms else "general"
        
        dup_check = anti_dup_engine.check_before_generation(
            script=f"{topic} {content_type} {tone}",  # Simplified script for check
            category=tone,
            platform=primary_platform,
            account_id=str(user_id),
            check_window_days=30,
        )
        
        if dup_check.get("is_duplicate", False):
            logger.warning(f"Duplicate content detected for user {user_id}, topic: {topic}")
            self.update_state(state='FAILURE', meta={
                'error': 'Duplicate content detected',
                'similarity': dup_check.get('similarity', 0.0),
                'existing_id': dup_check.get('existing_id')
            })
            raise ValueError(f"Content too similar to existing content (similarity: {dup_check.get('similarity', 0.0)})")
        
        self.update_state(state='PROCESSING', meta={'progress': 30, 'stage': 'generating_content'})
        
        # Simulate AI content generation (replace with real AI service)
        time.sleep(2)  # Simulate processing time
        
        # Mock AI generation
        generated_data = {
            "script": f"Engaging content about {topic}. "
                     f"This is a {content_type} optimized for {', '.join(platforms)}. "
                     f"Tone: {tone}.",
            "title": f"{topic} - {content_type.title()}",
            "hooks": [
                f"Did you know about {topic}?",
                f"{topic} is trending right now",
                f"Explore the world of {topic}",
            ],
            "hashtags": [
                f"#{topic.replace(' ', '')}",
                "#trending",
                "#content",
                "#viral",
            ],
            "ctas": [
                "Follow for more",
                "Share this",
                "Comment below",
            ],
            "captions": {
                platform: f"{topic} content for {platform}" 
                for platform in platforms
            },
            "quality_score": random.uniform(75, 95),
            "virality_potential": random.uniform(60, 90),
        }
        
        self.update_state(state='PROCESSING', meta={'progress': 70, 'stage': 'saving_to_db'})
        
        # Save to database
        post = Post(
            user_id=user_id,
            title=generated_data["title"],
            script=generated_data["script"],
            category=tone,
            content_type=content_type,
            status="draft",
            hooks=generated_data["hooks"],
            captions=generated_data["captions"],
            quality_score=generated_data["quality_score"],
            virality_prediction=generated_data["virality_potential"],
            metadata={
                "generated_with_ai": True,
                "tone": tone,
                "language": language,
                "target_platforms": platforms,
                "generated_at": datetime.utcnow().isoformat(),
            }
        )
        
        db.add(post)
        db.commit()
        db.refresh(post)
        
        self.update_state(state='SUCCESS', meta={
            'progress': 100,
            'post_id': post.id,
            'stage': 'complete'
        })
        
        logger.info(f"Content generated successfully for user {user_id}, post ID: {post.id}")
        
        return {
            "post_id": post.id,
            "title": generated_data["title"],
            "script": generated_data["script"],
            "hooks": generated_data["hooks"],
            "hashtags": generated_data["hashtags"],
            "quality_score": generated_data["quality_score"],
            "virality_potential": generated_data["virality_potential"],
            "generated_at": datetime.utcnow().isoformat(),
        }
        
    except Exception as e:
        logger.error(f"Content generation failed for user {user_id}: {str(e)}", exc_info=True)
        self.update_state(state='FAILURE', meta={'error': str(e)})
        raise
        
    finally:
        db.close()


# ============================================================================
# Batch Content Generation
# ============================================================================

@shared_task(bind=True, name='app.tasks.content_tasks.generate_batch_content')
def generate_batch_content(self, user_id: int, topics: list, content_type: str, 
                          platforms: list, tone: str = "professional"):
    """
    Generate multiple content pieces in batch.
    
    Args:
        user_id: User ID
        topics: List of topics for content
        content_type: Type of content
        platforms: Target platforms
        tone: Content tone
    
    Returns:
        dict: Results for all generated content
    """
    db = SessionLocal()
    results = []
    
    try:
        total_topics = len(topics)
        
        for idx, topic in enumerate(topics):
            progress = int((idx / total_topics) * 100)
            self.update_state(state='PROCESSING', meta={
                'progress': progress,
                'current_topic': topic,
                'completed': idx,
                'total': total_topics
            })
            
            # Call generate_content for each topic
            result = generate_content.apply_async(
                args=[user_id, topic, content_type, platforms, tone]
            )
            
            results.append({
                "topic": topic,
                "task_id": result.id,
                "status": result.status
            })
        
        logger.info(f"Batch content generation completed for user {user_id}")
        
        return {
            "batch_id": self.request.id,
            "user_id": user_id,
            "total_topics": total_topics,
            "results": results,
            "generated_at": datetime.utcnow().isoformat(),
        }
        
    except Exception as e:
        logger.error(f"Batch content generation failed: {str(e)}", exc_info=True)
        raise
        
    finally:
        db.close()


# ============================================================================
# Content Optimization Task
# ============================================================================

@shared_task(bind=True, name='app.tasks.content_tasks.optimize_content')
def optimize_content(self, post_id: int, optimization_type: str = "seo"):
    """
    Optimize existing content for better performance.
    
    Optimization types:
    - seo: SEO optimization
    - engagement: Maximize engagement
    - viral: Maximize virality potential
    - accessibility: Improve accessibility
    
    Args:
        post_id: Post ID to optimize
        optimization_type: Type of optimization
    
    Returns:
        dict: Optimization results and recommendations
    """
    db = SessionLocal()
    
    try:
        self.update_state(state='PROCESSING', meta={'progress': 20, 'stage': 'analyzing'})
        
        post = db.query(Post).filter(Post.id == post_id).first()
        if not post:
            raise ValueError(f"Post {post_id} not found")
        
        logger.info(f"Optimizing post {post_id} for {optimization_type}")
        
        time.sleep(1)  # Simulate optimization processing
        
        self.update_state(state='PROCESSING', meta={'progress': 60, 'stage': 'generating_recommendations'})
        
        # Generate optimization recommendations
        recommendations = {
            "seo": [
                "Add target keywords to title",
                "Include primary keyword in first sentence",
                "Optimize hashtags for search",
            ],
            "engagement": [
                "Move hook earlier in script",
                "Add more questions to engage audience",
                "Include CTA within first 30 seconds",
            ],
            "viral": [
                "Increase hook intensity",
                "Add trending elements",
                "Optimize for platform algorithm",
            ],
            "accessibility": [
                "Add captions/subtitles",
                "Include alt text for images",
                "Use sufficient color contrast",
            ],
        }
        
        optimization_data = recommendations.get(optimization_type, recommendations["seo"])
        
        # Update post quality score
        post.quality_score = min(post.quality_score + random.uniform(5, 15), 100)
        db.commit()
        
        self.update_state(state='SUCCESS', meta={
            'progress': 100,
            'post_id': post_id,
            'optimization_type': optimization_type
        })
        
        logger.info(f"Post {post_id} optimization completed")
        
        return {
            "post_id": post_id,
            "optimization_type": optimization_type,
            "recommendations": optimization_data,
            "quality_score_improved_to": post.quality_score,
            "optimized_at": datetime.utcnow().isoformat(),
        }
        
    except Exception as e:
        logger.error(f"Content optimization failed: {str(e)}", exc_info=True)
        raise
        
    finally:
        db.close()


# ============================================================================
# Learning Engine Tasks
# ============================================================================

@shared_task(bind=True, name='app.tasks.content_tasks.update_skip_analysis')
def update_skip_analysis(self) -> Dict[str, Any]:
    """
    Periodic task to update skip analysis patterns and templates.
    Run daily to analyze accumulated skip data.
    """
    try:
        self.update_state(state='PROCESSING', meta={'progress': 25, 'stage': 'analyzing_patterns'})

        engine = get_engine("skip_analysis")
        patterns = engine.analyze_patterns()

        self.update_state(state='PROCESSING', meta={'progress': 75, 'stage': 'updating_templates'})

        template_updates = engine.update_templates()

        self.update_state(state='SUCCESS', meta={'progress': 100})

        logger.info("Skip analysis update completed")

        return {
            "patterns_analyzed": patterns,
            "templates_updated": template_updates,
            "updated_at": datetime.utcnow().isoformat(),
        }

    except Exception as e:
        logger.error(f"Skip analysis update failed: {str(e)}", exc_info=True)
        self.update_state(state='FAILURE', meta={'error': str(e)})
        raise


@shared_task(bind=True, name='app.tasks.content_tasks.update_best_time_learning')
def update_best_time_learning(self) -> Dict[str, Any]:
    """
    Periodic task to update best time predictions and scheduler.
    Run daily to incorporate new engagement data.
    """
    try:
        self.update_state(state='PROCESSING', meta={'progress': 50, 'stage': 'updating_scheduler'})

        engine = get_engine("best_time")
        scheduler_updates = engine.auto_update_scheduler()

        self.update_state(state='SUCCESS', meta={'progress': 100})

        logger.info("Best time learning update completed")

        return {
            "scheduler_updates": scheduler_updates,
            "updated_at": datetime.utcnow().isoformat(),
        }

    except Exception as e:
        logger.error(f"Best time learning update failed: {str(e)}", exc_info=True)
        self.update_state(state='FAILURE', meta={'error': str(e)})
        raise


@shared_task(bind=True, name='app.tasks.content_tasks.update_hashtag_learning')
def update_hashtag_learning(self, threshold_engagement: float = 0.5) -> Dict[str, Any]:
    """
    Periodic task to clean up underperforming hashtags.
    Run weekly to maintain hashtag quality.
    """
    try:
        self.update_state(state='PROCESSING', meta={'progress': 50, 'stage': 'cleaning_hashtags'})

        engine = get_engine("hashtag_learning")
        cleanup_results = engine.drop_poor_hashtags(threshold_engagement)

        self.update_state(state='SUCCESS', meta={'progress': 100})

        logger.info("Hashtag learning cleanup completed")

        return {
            "cleanup_results": cleanup_results,
            "threshold_used": threshold_engagement,
            "updated_at": datetime.utcnow().isoformat(),
        }

    except Exception as e:
        logger.error(f"Hashtag learning update failed: {str(e)}", exc_info=True)
        self.update_state(state='FAILURE', meta={'error': str(e)})
        raise


@shared_task(bind=True, name='app.tasks.content_tasks.bulk_update_learning_engines')
def bulk_update_learning_engines(self) -> Dict[str, Any]:
    """
    Bulk update all learning engines.
    Run as a maintenance task.
    """
    results = {}

    try:
        # Update skip analysis
        self.update_state(state='PROCESSING', meta={'progress': 25, 'stage': 'updating_skip_analysis'})
        skip_result = update_skip_analysis()
        results["skip_analysis"] = skip_result

        # Update best time learning
        self.update_state(state='PROCESSING', meta={'progress': 50, 'stage': 'updating_best_time'})
        best_time_result = update_best_time_learning()
        results["best_time"] = best_time_result

        # Update hashtag learning
        self.update_state(state='PROCESSING', meta={'progress': 75, 'stage': 'updating_hashtags'})
        hashtag_result = update_hashtag_learning()
        results["hashtag_learning"] = hashtag_result

        self.update_state(state='SUCCESS', meta={'progress': 100})

        logger.info("Bulk learning engine update completed")

        return {
            "results": results,
            "completed_at": datetime.utcnow().isoformat(),
        }

    except Exception as e:
        logger.error(f"Bulk learning engine update failed: {str(e)}", exc_info=True)
        self.update_state(state='FAILURE', meta={'error': str(e)})
        raise
