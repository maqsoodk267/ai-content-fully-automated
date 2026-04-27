"""
SQLAlchemy ORM Models for AI Content Platform

Comprehensive data models for multi-tenant SaaS content automation platform.
Database: PostgreSQL with JSONB support
"""

from datetime import datetime, timedelta
from typing import List, Optional
from sqlalchemy import (
    BigInteger, Boolean, Column, Date, DateTime, Enum, Float, ForeignKey,
    Index, Integer, Interval, JSON, LargeBinary, String, Table,
    Text, UniqueConstraint, func, text, Numeric
)
from sqlalchemy.dialects.postgresql import JSONB, ARRAY, INET
from sqlalchemy.orm import relationship, declarative_base
from sqlalchemy.sql import expression
import enum

Base = declarative_base()


# =====================================================================
# Enum Definitions
# =====================================================================

class UserPlan(str, enum.Enum):
    """User subscription plans"""
    FREE = "free"
    PRO = "pro"
    ENTERPRISE = "enterprise"


class SubscriptionStatus(str, enum.Enum):
    """Subscription status"""
    ACTIVE = "active"
    PAUSED = "paused"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class Platform(str, enum.Enum):
    """Supported social media platforms"""
    INSTAGRAM = "instagram"
    TIKTOK = "tiktok"
    YOUTUBE = "youtube"
    FACEBOOK = "facebook"
    X = "x"  # Twitter
    LINKEDIN = "linkedin"
    TELEGRAM = "telegram"
    PINTEREST = "pinterest"


class PostStatus(str, enum.Enum):
    """Post workflow status"""
    DRAFT = "draft"
    REVIEW = "review"
    APPROVED = "approved"
    SCHEDULED = "scheduled"
    PUBLISHED = "published"
    FAILED = "failed"
    ARCHIVED = "archived"


class ContentType(str, enum.Enum):
    """Content format types"""
    REEL = "reel"
    SHORT = "short"
    CAROUSEL = "carousel"
    STORY = "story"
    POST = "post"
    LONG_FORM = "long_form"
    LIVE = "live"
    CLIP = "clip"


class AssetType(str, enum.Enum):
    """Media asset types"""
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    DOCUMENT = "document"


class AssetSource(str, enum.Enum):
    """Asset source"""
    PEXELS = "pexels"
    PIXABAY = "pixabay"
    USER_UPLOADED = "user_uploaded"
    GENERATED = "generated"
    EXTERNAL = "external"


class ProcessingStatus(str, enum.Enum):
    """Asset processing status"""
    PENDING = "pending"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class ScheduleStatus(str, enum.Enum):
    """Publishing schedule status"""
    PENDING = "pending"
    PROCESSING = "processing"
    PUBLISHED = "published"
    FAILED = "failed"
    CANCELLED = "cancelled"


class DuplicateAction(str, enum.Enum):
    """Action taken on duplicate detection"""
    WARNING = "warning"
    BLOCKED = "blocked"
    MERGED = "merged"
    ARCHIVED = "archived"
    IGNORED = "ignored"


class CampaignStatus(str, enum.Enum):
    """Campaign status"""
    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    ARCHIVED = "archived"


class CampaignObjective(str, enum.Enum):
    """Campaign objectives"""
    AWARENESS = "awareness"
    ENGAGEMENT = "engagement"
    CONVERSION = "conversion"
    RETENTION = "retention"


class LogActionCategory(str, enum.Enum):
    """Log action categories"""
    USER_ACTION = "user_action"
    SYSTEM_ACTION = "system_action"
    ERROR = "error"
    SECURITY = "security"


class LogStatus(str, enum.Enum):
    """Log status"""
    SUCCESS = "success"
    FAILURE = "failure"
    WARNING = "warning"


# =====================================================================
# Association Tables (M:N relationships)
# =====================================================================

post_hashtags = Table(
    'post_hashtags',
    Base.metadata,
    Column('post_id', BigInteger, ForeignKey('posts.id', ondelete='CASCADE'), primary_key=True),
    Column('hashtag_id', BigInteger, ForeignKey('hashtags.id'), primary_key=True),
    Column('used_at', DateTime(timezone=True), server_default=func.now()),
    Index('idx_post_hashtags_hashtag_id', 'hashtag_id'),
)


# =====================================================================
# 1. Users Table
# =====================================================================

class User(Base):
    """Multi-tenant SaaS user account management"""
    __tablename__ = 'users'
    
    id = Column(BigInteger, primary_key=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    username = Column(String(100), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    first_name = Column(String(100))
    last_name = Column(String(100))
    avatar_url = Column(Text)
    
    # Settings
    plan = Column(String(50), default=UserPlan.FREE.value)
    subscription_status = Column(String(50), default=SubscriptionStatus.ACTIVE.value)
    max_posts_per_day = Column(Integer, default=10)
    max_accounts = Column(Integer, default=3)
    api_key = Column(String(200), unique=True, index=True)
    api_key_hash = Column(String(255))
    
    # Organization
    organization_name = Column(String(255))
    timezone = Column(String(50), default='UTC')
    language = Column(String(10), default='en')
    
    # Status
    is_active = Column(Boolean, default=True, index=True)
    is_verified = Column(Boolean, default=False)
    email_verified_at = Column(DateTime(timezone=True))
    last_login_at = Column(DateTime(timezone=True))
    
    # Metadata
    preferences = Column(JSONB, default=dict)
    
    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())
    deleted_at = Column(DateTime(timezone=True))
    
    # Relationships
    accounts = relationship("Account", back_populates="user", cascade="all, delete-orphan")
    posts = relationship("Post", back_populates="user", cascade="all, delete-orphan", foreign_keys="Post.user_id")
    campaigns = relationship("Campaign", back_populates="user", cascade="all, delete-orphan")
    assets = relationship("Asset", back_populates="user", cascade="all, delete-orphan")
    schedules = relationship("Schedule", back_populates="user", cascade="all, delete-orphan")
    logs = relationship("Log", back_populates="user", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<User(id={self.id}, email='{self.email}', username='{self.username}')>"


# =====================================================================
# 2. Accounts Table
# =====================================================================

class Account(Base):
    """Social media accounts linked to users"""
    __tablename__ = 'accounts'
    
    id = Column(BigInteger, primary_key=True)
    user_id = Column(BigInteger, ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    
    # Platform Info
    platform = Column(String(50), nullable=False, index=True)
    platform_user_id = Column(String(255), nullable=False)
    username = Column(String(255), nullable=False)
    display_name = Column(String(255))
    avatar_url = Column(Text)
    bio = Column(Text)
    
    # Authentication
    access_token = Column(String(2000))
    refresh_token = Column(String(2000))
    token_type = Column(String(50))
    token_expires_at = Column(DateTime(timezone=True))
    token_scopes = Column(JSONB, default=list)
    
    # Account Status
    is_active = Column(Boolean, default=True, index=True)
    is_verified = Column(Boolean, default=False)
    is_shadowbanned = Column(Boolean, default=False, index=True)
    shadowban_detected_at = Column(DateTime(timezone=True))
    
    # Metrics
    followers = Column(Integer, default=0)
    engagement_rate = Column(Float, default=0.0)
    last_sync_at = Column(DateTime(timezone=True))
    
    # Platform-Specific Data
    extra_metadata = Column("metadata", JSONB, default=dict)
    
    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())
    deleted_at = Column(DateTime(timezone=True))
    
    # Constraints
    __table_args__ = (
        UniqueConstraint('user_id', 'platform', 'platform_user_id', name='uq_user_platform_account'),
        Index('idx_account_platform', 'platform'),
        Index('idx_account_is_shadowbanned', 'is_shadowbanned'),
    )
    
    # Relationships
    user = relationship("User", back_populates="accounts")
    posts = relationship("Post", back_populates="account", cascade="all, delete-orphan")
    schedules = relationship("Schedule", back_populates="account", cascade="all, delete-orphan")
    analytics = relationship("Analytics", back_populates="account")
    
    def __repr__(self):
        return f"<Account(id={self.id}, platform='{self.platform}', username='{self.username}')>"


# =====================================================================
# 3. Posts Table
# =====================================================================

class Post(Base):
    """Generated and published content"""
    __tablename__ = 'posts'
    
    id = Column(BigInteger, primary_key=True)
    user_id = Column(BigInteger, ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    account_id = Column(BigInteger, ForeignKey('accounts.id', ondelete='SET NULL'))
    
    # Content
    title = Column(String(500))
    script = Column(Text)
    caption = Column(Text)
    hooks = Column(JSONB, default=list)  # Array of hooks
    cta_text = Column(String(500))
    
    # Media References
    primary_asset_id = Column(BigInteger, ForeignKey('assets.id', ondelete='SET NULL'))
    asset_ids = Column(ARRAY(BigInteger), default=list)
    
    # Classification
    category = Column(String(100), index=True)
    content_type = Column(String(50))
    language = Column(String(10))
    
    # Platform & Publishing
    platforms = Column(JSONB, default=dict)  # Platform-specific data
    platform_post_ids = Column(JSONB, default=dict)  # Post IDs after publishing
    
    # Quality & Analytics
    quality_score = Column(Float, default=0.0)
    engagement_prediction = Column(Float, default=0.0)
    estimated_reach = Column(Integer)
    
    # Trend & Campaign
    trend_id = Column(BigInteger, ForeignKey('trends.id', ondelete='SET NULL'))
    campaign_id = Column(BigInteger, ForeignKey('campaigns.id', ondelete='SET NULL'))
    
    # Status
    status = Column(String(50), default=PostStatus.DRAFT.value, index=True)
    review_notes = Column(Text)
    reviewer_id = Column(BigInteger, ForeignKey('users.id', ondelete='SET NULL'))
    
    # Publishing Timeline
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    scheduled_at = Column(DateTime(timezone=True))
    published_at = Column(DateTime(timezone=True), index=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())
    deleted_at = Column(DateTime(timezone=True))
    
    # Metadata
    extra_metadata = Column("metadata", JSONB, default=dict)
    
    # Indexes
    __table_args__ = (
        Index('idx_post_user_status', 'user_id', 'status'),
        Index('idx_post_created_at', 'created_at'),
        Index('idx_post_published_at', 'published_at'),
        Index('idx_post_category', 'category'),
    )
    
    # Relationships
    user = relationship("User", back_populates="posts", foreign_keys=[user_id])
    account = relationship("Account", back_populates="posts")
    trend = relationship("Trend", back_populates="posts")
    campaign = relationship("Campaign", back_populates="posts")
    primary_asset = relationship("Asset", foreign_keys=[primary_asset_id])
    hashtags = relationship("Hashtag", secondary=post_hashtags, back_populates="posts")
    analytics = relationship("Analytics", back_populates="post", cascade="all, delete-orphan")
    duplicates = relationship("Duplicate", back_populates="primary_post", foreign_keys='Duplicate.primary_post_id', cascade="all, delete-orphan")
    duplicate_of = relationship("Duplicate", back_populates="duplicate_post", foreign_keys='Duplicate.duplicate_post_id')
    schedules = relationship("Schedule", back_populates="post", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<Post(id={self.id}, title='{self.title}', status='{self.status}')>"


# =====================================================================
# 4. Analytics Table
# =====================================================================

class Analytics(Base):
    """Track post performance across platforms"""
    __tablename__ = 'analytics'
    
    id = Column(BigInteger, primary_key=True)
    post_id = Column(BigInteger, ForeignKey('posts.id', ondelete='CASCADE'), nullable=False, index=True)
    account_id = Column(BigInteger, ForeignKey('accounts.id', ondelete='CASCADE'), nullable=False, index=True)
    
    # Platform & Post IDs
    platform = Column(String(50), nullable=False, index=True)
    platform_post_id = Column(String(255))
    platform_account_id = Column(String(255))
    
    # Engagement Metrics
    views = Column(Integer, default=0)
    likes = Column(Integer, default=0)
    comments = Column(Integer, default=0)
    shares = Column(Integer, default=0)
    saves = Column(Integer, default=0)
    click_count = Column(Integer, default=0)
    
    # Derived Metrics
    engagement_rate = Column(Float, default=0.0, index=True)
    comment_rate = Column(Float, default=0.0)
    share_rate = Column(Float, default=0.0)
    ctr = Column(Float, default=0.0)  # Click-through rate
    
    # Video-Specific Metrics
    watch_time_total = Column(Integer, default=0)  # seconds
    watch_time_avg = Column(Float, default=0.0)    # seconds
    completion_rate = Column(Float, default=0.0)   # percentage
    skip_rate_3s = Column(Float, default=0.0)
    skip_rate_10s = Column(Float, default=0.0)
    skip_rate_30s = Column(Float, default=0.0)
    
    # Demographic Insights
    top_countries = Column(JSONB, default=list)
    top_cities = Column(JSONB, default=list)
    audience_age = Column(JSONB, default=dict)
    audience_gender = Column(JSONB, default=dict)
    
    # Timing
    tracked_at = Column(DateTime(timezone=True), server_default=func.now())
    synced_at = Column(DateTime(timezone=True))
    
    # Metadata
    extra_metadata = Column("metadata", JSONB, default=dict)
    
    # Constraints
    __table_args__ = (
        UniqueConstraint('post_id', 'platform', name='uq_post_platform_analytics'),
        Index('idx_analytics_post_date', 'post_id', 'tracked_at'),
    )
    
    # Relationships
    post = relationship("Post", back_populates="analytics")
    account = relationship("Account", back_populates="analytics")
    
    def __repr__(self):
        return f"<Analytics(id={self.id}, post_id={self.post_id}, platform='{self.platform}')>"


# =====================================================================
# 5. Trends Table
# =====================================================================

class Trend(Base):
    """Store discovered and tracked trends"""
    __tablename__ = 'trends'
    
    id = Column(BigInteger, primary_key=True)
    
    # Trend Info
    title = Column(String(500), nullable=False)
    description = Column(Text)
    slug = Column(String(500), unique=True)
    
    # Metrics
    trend_score = Column(Float, default=0.0, index=True)
    viral_score = Column(Float, default=0.0, index=True)
    growth_rate = Column(Float, default=0.0)
    saturation_level = Column(Float, default=0.0)
    
    # Ranking
    rank = Column(Integer)
    rank_change = Column(Integer)
    
    # Source Info
    source = Column(String(100), index=True)
    primary_source = Column(String(100))
    secondary_sources = Column(JSONB, default=list)
    
    # Geographic & Language
    countries = Column(JSONB, default=list)
    languages = Column(JSONB, default=list)
    
    # Temporal
    detected_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    trend_starts_at = Column(DateTime(timezone=True))
    trend_peaks_at = Column(DateTime(timezone=True))
    trend_ends_at = Column(DateTime(timezone=True))
    
    # Content Guidance
    recommended_platforms = Column(JSONB, default=list)
    recommended_format = Column(String(50))
    recommended_duration_min = Column(Integer)
    recommended_duration_max = Column(Integer)
    
    # Related Data
    related_hashtags = Column(JSONB, default=list)
    related_audio = Column(JSONB, default=list)
    related_trends = Column(ARRAY(BigInteger), default=list)
    
    # Status
    is_active = Column(Boolean, default=True, index=True)
    is_rising = Column(Boolean, default=False, index=True)
    
    # Metadata
    extra_metadata = Column("metadata", JSONB, default=dict)
    
    # Relationships
    posts = relationship("Post", back_populates="trend")
    
    def __repr__(self):
        return f"<Trend(id={self.id}, title='{self.title}', trend_score={self.trend_score})>"


# =====================================================================
# 6. Hashtags Table
# =====================================================================

class Hashtag(Base):
    """Hashtag tracking and analytics"""
    __tablename__ = 'hashtags'
    
    id = Column(BigInteger, primary_key=True)
    
    # Hashtag Info
    tag = Column(String(200), unique=True, nullable=False)
    display_tag = Column(String(200))
    description = Column(Text)
    
    # Metrics
    post_count = Column(Integer, default=0)
    engagement_total = Column(BigInteger, default=0)
    avg_engagement = Column(Float, default=0.0)
    reach_total = Column(BigInteger, default=0)
    avg_reach = Column(Float, default=0.0)
    
    # Performance
    trending_score = Column(Float, default=0.0, index=True)
    is_trending = Column(Boolean, default=False, index=True)
    trend_rank = Column(Integer)
    
    # Classification
    category = Column(String(100), index=True)
    platform = Column(String(50))
    
    # Time Data
    detected_at = Column(DateTime(timezone=True), server_default=func.now())
    last_used_at = Column(DateTime(timezone=True), index=True)
    peaks_at_hour = Column(Integer)  # 0-23 UTC
    peaks_at_day = Column(String(10))  # Monday, Tuesday, etc.
    
    # Metadata
    extra_metadata = Column("metadata", JSONB, default=dict)
    
    # Indexes
    __table_args__ = (
        Index('idx_hashtag_tag', 'tag'),
        Index('idx_hashtag_trending', 'is_trending'),
    )
    
    # Relationships
    posts = relationship("Post", secondary=post_hashtags, back_populates="hashtags")
    
    def __repr__(self):
        return f"<Hashtag(id={self.id}, tag='{self.tag}', trending_score={self.trending_score})>"


# =====================================================================
# 7. Assets Table
# =====================================================================

class Asset(Base):
    """Media assets (images, videos, audio)"""
    __tablename__ = 'assets'
    
    id = Column(BigInteger, primary_key=True)
    user_id = Column(BigInteger, ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    
    # Asset Info
    filename = Column(String(500), nullable=False)
    mime_type = Column(String(100))
    asset_type = Column(String(50), index=True)
    
    # Storage
    s3_bucket = Column(String(255))
    s3_key = Column(String(500))
    s3_url = Column(Text)
    file_size = Column(BigInteger)  # bytes
    duration = Column(Integer)  # seconds (for video/audio)
    
    # Metadata
    width = Column(Integer)
    height = Column(Integer)
    fps = Column(Float)  # frames per second (video)
    resolution = Column(String(50))
    codec = Column(String(100))
    bitrate = Column(String(50))
    
    # Content Analysis
    has_text = Column(Boolean, default=False)
    has_faces = Column(Boolean, default=False)
    detected_objects = Column(ARRAY(String), default=list)
    dominant_colors = Column(JSONB, default=list)
    sentiment_score = Column(Float)
    
    # License & Rights
    source = Column(String(100), index=True)
    license_type = Column(String(50))
    attribution_required = Column(Boolean, default=False)
    attribution_text = Column(Text)
    
    # Status
    processing_status = Column(String(50), default=ProcessingStatus.PENDING.value, index=True)
    processing_error = Column(Text)
    is_active = Column(Boolean, default=True)
    
    # Temporal
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())
    deleted_at = Column(DateTime(timezone=True))
    
    # Metadata
    extra_metadata = Column("metadata", JSONB, default=dict)
    
    # Relationships
    user = relationship("User", back_populates="assets")
    
    def __repr__(self):
        return f"<Asset(id={self.id}, filename='{self.filename}', type='{self.asset_type}')>"


# =====================================================================
# 8. Schedules Table
# =====================================================================

class Schedule(Base):
    """Publishing schedule management"""
    __tablename__ = 'schedules'
    
    id = Column(BigInteger, primary_key=True)
    user_id = Column(BigInteger, ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    account_id = Column(BigInteger, ForeignKey('accounts.id', ondelete='CASCADE'), nullable=False)
    post_id = Column(BigInteger, ForeignKey('posts.id', ondelete='CASCADE'), nullable=False)
    
    # Schedule Info
    platform = Column(String(50), nullable=False, index=True)
    scheduled_time = Column(DateTime(timezone=True), nullable=False, index=True)
    
    # Publishing Details
    publish_method = Column(String(50))
    retry_count = Column(Integer, default=0)
    max_retries = Column(Integer, default=3)
    
    # Status
    status = Column(String(50), default=ScheduleStatus.PENDING.value, index=True)
    published_at = Column(DateTime(timezone=True))
    published_url = Column(Text)
    platform_response = Column(JSONB, default=dict)
    
    # Error Tracking
    error_message = Column(Text)
    error_code = Column(String(100))
    
    # Metadata
    extra_metadata = Column("metadata", JSONB, default=dict)
    
    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())
    
    # Indexes
    __table_args__ = (
        Index('idx_schedule_time_status', 'scheduled_time', 'status'),
    )
    
    # Relationships
    user = relationship("User", back_populates="schedules")
    account = relationship("Account", back_populates="schedules")
    post = relationship("Post", back_populates="schedules")
    
    def __repr__(self):
        return f"<Schedule(id={self.id}, platform='{self.platform}', status='{self.status}')>"


# =====================================================================
# 9. Duplicates Table
# =====================================================================

class Duplicate(Base):
    """Track duplicate content detection"""
    __tablename__ = 'duplicates'
    
    id = Column(BigInteger, primary_key=True)
    primary_post_id = Column(BigInteger, ForeignKey('posts.id', ondelete='CASCADE'), nullable=False, index=True)
    duplicate_post_id = Column(BigInteger, ForeignKey('posts.id', ondelete='CASCADE'), nullable=False, index=True)
    
    # Detection Method
    detection_method = Column(String(50))
    similarity_score = Column(Float, nullable=False, index=True)
    confidence = Column(Float)
    
    # Evidence
    matching_fields = Column(JSONB, default=list)
    hash_value = Column(String(255))
    text_hash = Column(String(255))
    
    # Action Taken
    action = Column(String(50))
    resolution_notes = Column(Text)
    
    # Temporal
    detected_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    resolved_at = Column(DateTime(timezone=True))
    
    # Metadata
    extra_metadata = Column("metadata", JSONB, default=dict)
    
    # Relationships
    primary_post = relationship("Post", foreign_keys=[primary_post_id], back_populates="duplicates")
    duplicate_post = relationship("Post", foreign_keys=[duplicate_post_id], back_populates="duplicate_of")
    
    def __repr__(self):
        return f"<Duplicate(id={self.id}, primary={self.primary_post_id}, duplicate={self.duplicate_post_id}, score={self.similarity_score})>"


# =====================================================================
# 10. Campaigns Table
# =====================================================================

class Campaign(Base):
    """Marketing and promotional campaigns"""
    __tablename__ = 'campaigns'
    
    id = Column(BigInteger, primary_key=True)
    user_id = Column(BigInteger, ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    
    # Campaign Info
    name = Column(String(255), nullable=False)
    description = Column(Text)
    slug = Column(String(255), unique=True)
    
    # Campaign Details
    objective = Column(String(100), index=True)
    campaign_type = Column(String(50))
    
    # Targeting
    target_audience = Column(JSONB, default=dict)
    target_platforms = Column(JSONB, default=list)
    target_countries = Column(JSONB, default=list)
    
    # Performance Goals
    goal_metric = Column(String(50))
    goal_value = Column(Integer)
    
    # Timeline
    start_date = Column(DateTime(timezone=True), nullable=False)
    end_date = Column(DateTime(timezone=True), nullable=False)
    
    # Budget (if applicable)
    budget = Column(Numeric(10, 2))
    spent = Column(Numeric(10, 2), default=0)
    currency = Column(String(3), default='USD')
    
    # Performance Metrics
    total_posts = Column(Integer, default=0)
    total_views = Column(BigInteger, default=0)
    total_engagements = Column(BigInteger, default=0)
    total_conversions = Column(Integer, default=0)
    roi = Column(Float, default=0.0)
    
    # Status
    status = Column(String(50), default=CampaignStatus.DRAFT.value, index=True)
    
    # Metadata
    extra_metadata = Column("metadata", JSONB, default=dict)
    
    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())
    deleted_at = Column(DateTime(timezone=True))
    
    # Relationships
    user = relationship("User", back_populates="campaigns")
    posts = relationship("Post", back_populates="campaign")
    
    def __repr__(self):
        return f"<Campaign(id={self.id}, name='{self.name}', status='{self.status}')>"


# =====================================================================
# 11. Logs Table
# =====================================================================

class Log(Base):
    """Audit trail and operational logging"""
    __tablename__ = 'logs'
    
    id = Column(BigInteger, primary_key=True)
    user_id = Column(BigInteger, ForeignKey('users.id', ondelete='SET NULL'), index=True)
    
    # Log Context
    entity_type = Column(String(100), index=True)
    entity_id = Column(BigInteger, index=True)
    
    # Action
    action = Column(String(100), index=True)
    action_category = Column(String(50))
    
    # Details
    description = Column(Text)
    old_values = Column(JSONB, default=dict)
    new_values = Column(JSONB, default=dict)
    
    # Request Context
    ip_address = Column(INET)
    user_agent = Column(Text)
    api_key_used = Column(String(200))
    
    # Status
    status = Column(String(50), index=True)
    error_message = Column(Text)
    error_code = Column(String(100))
    error_stack_trace = Column(Text)
    
    # Metadata
    extra_metadata = Column("metadata", JSONB, default=dict)
    
    # Temporal
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    
    # Relationships
    user = relationship("User", back_populates="logs")
    
    def __repr__(self):
        return f"<Log(id={self.id}, entity_type='{self.entity_type}', action='{self.action}')>"


# =====================================================================
# Learning Engine Models
# =====================================================================

class SkipEvent(Base):
    """Track viewer skip events for content optimization"""
    __tablename__ = 'skip_events'

    id = Column(BigInteger, primary_key=True)
    post_id = Column(BigInteger, ForeignKey('posts.id', ondelete='CASCADE'), nullable=False, index=True)
    account_id = Column(BigInteger, ForeignKey('accounts.id', ondelete='CASCADE'), nullable=False, index=True)

    # Skip Details
    skip_time_seconds = Column(Float, nullable=False)
    platform = Column(String(50), nullable=False, index=True)
    category = Column(String(100), index=True)

    # Context
    video_duration = Column(Float)  # total video length
    viewer_count_at_skip = Column(Integer)  # how many viewers left at this point

    # Metadata
    extra_metadata = Column("metadata", JSONB, default=dict)

    # Temporal
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    # Indexes
    __table_args__ = (
        Index('idx_skip_event_post_platform', 'post_id', 'platform'),
        Index('idx_skip_event_category', 'category'),
        Index('idx_skip_event_created_at', 'created_at'),
    )

    # Relationships
    post = relationship("Post", backref="skip_events")
    account = relationship("Account", backref="skip_events")

    def __repr__(self):
        return f"<SkipEvent(id={self.id}, post_id={self.post_id}, skip_time={self.skip_time_seconds}s, platform='{self.platform}')>"


class BestTimeMetric(Base):
    """Store engagement metrics per hour/day for optimal posting times"""
    __tablename__ = 'best_time_metrics'

    id = Column(BigInteger, primary_key=True)
    account_id = Column(BigInteger, ForeignKey('accounts.id', ondelete='CASCADE'), nullable=False, index=True)
    user_id = Column(BigInteger, ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)

    # Time Context
    platform = Column(String(50), nullable=False, index=True)
    hour_utc = Column(Integer, nullable=False)  # 0-23
    day_of_week = Column(Integer)  # 0=Monday, 6=Sunday
    timezone = Column(String(50), default='UTC')

    # Performance Metrics
    post_count = Column(Integer, default=0)
    total_engagement = Column(Float, default=0.0)
    avg_engagement = Column(Float, default=0.0)
    total_views = Column(BigInteger, default=0)
    avg_views = Column(Float, default=0.0)

    # Learning Data
    engagement_samples = Column(JSONB, default=list)  # list of engagement rates
    confidence_score = Column(Float, default=0.0)  # based on sample size

    # Metadata
    extra_metadata = Column("metadata", JSONB, default=dict)

    # Temporal
    last_updated = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Indexes
    __table_args__ = (
        Index('idx_best_time_account_platform', 'account_id', 'platform'),
        Index('idx_best_time_hour', 'hour_utc'),
        Index('idx_best_time_platform_hour', 'platform', 'hour_utc'),
        UniqueConstraint('account_id', 'platform', 'hour_utc', name='uq_account_platform_hour'),
    )

    # Relationships
    account = relationship("Account", backref="best_time_metrics")
    user = relationship("User", backref="best_time_metrics")

    def __repr__(self):
        return f"<BestTimeMetric(account_id={self.account_id}, platform='{self.platform}', hour={self.hour_utc}, avg_engagement={self.avg_engagement})>"


class HashtagPerformance(Base):
    """Track hashtag performance across platforms and categories"""
    __tablename__ = 'hashtag_performance'

    id = Column(BigInteger, primary_key=True)
    hashtag = Column(String(200), nullable=False, index=True)

    # Context
    platform = Column(String(50), nullable=False, index=True)
    category = Column(String(100), index=True)

    # Performance Metrics
    usage_count = Column(Integer, default=0)
    total_impressions = Column(BigInteger, default=0)
    total_engagement = Column(Float, default=0.0)
    avg_impressions = Column(Float, default=0.0)
    avg_engagement = Column(Float, default=0.0)

    # Learning Data
    impression_samples = Column(JSONB, default=list)  # list of impression counts
    engagement_samples = Column(JSONB, default=list)  # list of engagement rates
    performance_score = Column(Float, default=0.0)  # calculated score

    # Status
    is_active = Column(Boolean, default=True, index=True)
    last_performance_check = Column(DateTime(timezone=True))

    # Metadata
    extra_metadata = Column("metadata", JSONB, default=dict)

    # Temporal
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())

    # Indexes
    __table_args__ = (
        Index('idx_hashtag_perf_hashtag_platform', 'hashtag', 'platform'),
        Index('idx_hashtag_perf_category', 'category'),
        Index('idx_hashtag_perf_score', 'performance_score'),
        Index('idx_hashtag_perf_active', 'is_active'),
        UniqueConstraint('hashtag', 'platform', 'category', name='uq_hashtag_platform_category'),
    )

    def __repr__(self):
        return f"<HashtagPerformance(hashtag='{self.hashtag}', platform='{self.platform}', score={self.performance_score})>"


class APICall(Base):
    """Track API calls and their costs for billing and usage monitoring"""
    __tablename__ = 'api_calls'

    id = Column(BigInteger, primary_key=True)
    user_id = Column(BigInteger, ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    account_id = Column(BigInteger, ForeignKey('accounts.id', ondelete='CASCADE'), nullable=False, index=True)

    # API Call Details
    service = Column(String(100), nullable=False, index=True)  # openai, anthropic, etc.
    operation = Column(String(100), nullable=False)  # text_generation, image_generation, etc.
    endpoint = Column(String(255))  # Specific API endpoint called

    # Cost Information
    cost_usd = Column(Numeric(10, 6), nullable=False, default=0)  # Cost in USD
    tokens_used = Column(Integer)  # For text models
    images_generated = Column(Integer)  # For image models
    audio_duration_seconds = Column(Float)  # For speech synthesis

    # Request/Response Metadata
    request_size_bytes = Column(Integer)  # Request payload size
    response_size_bytes = Column(Integer)  # Response payload size
    processing_time_ms = Column(Integer)  # Time to complete

    # Context
    content_type = Column(String(50))  # post, asset, analysis, etc.
    content_id = Column(BigInteger)  # Related content ID
    platform = Column(String(50))  # Target platform if applicable

    # Status
    success = Column(Boolean, default=True)
    error_message = Column(Text)

    # Metadata
    extra_metadata = Column("metadata", JSONB, default=dict)

    # Temporal
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    # Indexes
    __table_args__ = (
        Index('idx_api_call_user_service', 'user_id', 'service'),
        Index('idx_api_call_created_at', 'created_at'),
        Index('idx_api_call_service_operation', 'service', 'operation'),
        Index('idx_api_call_cost', 'cost_usd'),
    )

    # Relationships
    user = relationship("User", backref="api_calls")
    account = relationship("Account", backref="api_calls")

    def __repr__(self):
        return f"<APICall(id={self.id}, user_id={self.user_id}, service='{self.service}', cost=${self.cost_usd})>"


class UserBudget(Base):
    """User budget limits and usage tracking"""
    __tablename__ = 'user_budgets'

    id = Column(BigInteger, primary_key=True)
    user_id = Column(BigInteger, ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)

    # Budget Settings
    monthly_budget_usd = Column(Numeric(10, 2), nullable=False)
    daily_budget_usd = Column(Numeric(10, 2))

    # Current Usage (reset periodically)
    current_month_usage = Column(Numeric(10, 2), default=0)
    current_day_usage = Column(Numeric(10, 2), default=0)

    # Period Tracking
    budget_period_start = Column(DateTime(timezone=True), server_default=func.now())
    last_reset_date = Column(Date, server_default=func.current_date())

    # Alerts
    alert_threshold_percent = Column(Float, default=80.0)  # Alert at 80% usage
    alerts_enabled = Column(Boolean, default=True)

    # Status
    is_active = Column(Boolean, default=True)

    # Metadata
    extra_metadata = Column("metadata", JSONB, default=dict)

    # Temporal
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())

    # Indexes
    __table_args__ = (
        Index('idx_user_budget_user', 'user_id'),
        UniqueConstraint('user_id', name='uq_user_budget_user'),
    )

    # Relationships
    user = relationship("User", backref="budget")

    def __repr__(self):
        return f"<UserBudget(user_id={self.user_id}, monthly=${self.monthly_budget_usd}, current=${self.current_month_usage})>"


class QuarantinedContent(Base):
    """Content flagged for moderation review"""
    __tablename__ = 'quarantined_content'

    id = Column(BigInteger, primary_key=True)
    content_id = Column(String(255), nullable=False, index=True)  # Could be post_id or asset_id
    content_type = Column(String(50), nullable=False)  # post, asset, etc.

    # Moderation Details
    quarantine_reason = Column(String(255), nullable=False)
    severity = Column(String(50), default='medium')  # low, medium, high
    flagged_by = Column(String(100))  # Engine or user that flagged it

    # Content Preview (for review)
    content_preview = Column(Text)  # Truncated content text
    metadata_snapshot = Column(JSONB)  # Content metadata at time of quarantine

    # Review Status
    reviewed = Column(Boolean, default=False, index=True)
    reviewer_id = Column(BigInteger, ForeignKey('users.id', ondelete='SET NULL'))
    review_decision = Column(String(50))  # approve, reject, modify
    review_notes = Column(Text)

    # Appeal Process
    appealed = Column(Boolean, default=False)
    appeal_reason = Column(Text)
    appeal_resolved = Column(Boolean, default=False)

    # Metadata
    extra_metadata = Column("metadata", JSONB, default=dict)

    # Temporal
    quarantined_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    reviewed_at = Column(DateTime(timezone=True))
    appeal_deadline = Column(DateTime(timezone=True))

    # Indexes
    __table_args__ = (
        Index('idx_quarantined_content_type', 'content_type'),
        Index('idx_quarantined_reviewed', 'reviewed'),
        Index('idx_quarantined_severity', 'severity'),
    )

    # Relationships
    reviewer = relationship("User", foreign_keys=[reviewer_id])

    def __repr__(self):
        return f"<QuarantinedContent(id={self.id}, content_id='{self.content_id}', reason='{self.quarantine_reason}', reviewed={self.reviewed})>"


# =====================================================================
# Export all models
# =====================================================================

__all__ = [
    'Base',
    'User',
    'Account',
    'Post',
    'Analytics',
    'Trend',
    'Hashtag',
    'Asset',
    'Schedule',
    'Duplicate',
    'Campaign',
    'Log',
    'SkipEvent',
    'BestTimeMetric',
    'HashtagPerformance',
    'APICall',
    'UserBudget',
    'QuarantinedContent',
    'post_hashtags',
    # Enums
    'UserPlan',
    'SubscriptionStatus',
    'Platform',
    'PostStatus',
    'ContentType',
    'AssetType',
    'AssetSource',
    'ProcessingStatus',
    'ScheduleStatus',
    'DuplicateAction',
    'CampaignStatus',
    'CampaignObjective',
    'LogActionCategory',
    'LogStatus',
]
