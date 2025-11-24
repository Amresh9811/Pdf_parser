"""
Django models for structured data storage.
"""

from django.db import models
from django.core.validators import MinValueValidator
from django.utils import timezone


class BaseModel(models.Model):
    """Abstract base model with common fields."""
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        abstract = True


class Document(BaseModel):
    """Track processed documents."""
    file_name = models.CharField(max_length=255)
    file_path = models.CharField(max_length=500)
    document_type = models.CharField(max_length=100)
    status = models.CharField(
        max_length=50,
        choices=[
            ('pending', 'Pending'),
            ('processing', 'Processing'),
            ('completed', 'Completed'),
            ('failed', 'Failed'),
        ],
        default='pending'
    )
    processed_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(null=True, blank=True)
    
    class Meta:
        db_table = 'documents'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.file_name} ({self.status})"


class ProjectTask(BaseModel):
    """
    Schema 1: Project Schedule Document
    Stores structured task data from Gantt-like project schedules.
    """
    document = models.ForeignKey(
        Document,
        on_delete=models.CASCADE,
        related_name='tasks'
    )
    task_id = models.IntegerField(
        help_text="Unique task ID from the document"
    )
    task_name = models.CharField(
        max_length=500,
        help_text="Name/description of the task"
    )
    duration_days = models.IntegerField(
        validators=[MinValueValidator(0)],
        help_text="Duration in days"
    )
    start_date = models.DateField(
        null=True,  # CHANGED: Allow null
        blank=True,  # CHANGED: Allow blank
        help_text="Task start date"
    )
    finish_date = models.DateField(
        null=True,  # CHANGED: Allow null
        blank=True,  # CHANGED: Allow blank
        help_text="Task finish date"
    )
    predecessor = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        help_text="Predecessor task IDs"
    )
    resource_names = models.TextField(
        null=True,
        blank=True,
        help_text="Resources assigned to the task"
    )
    
    class Meta:
        db_table = 'project_tasks'
        ordering = ['task_id']
        indexes = [
            models.Index(fields=['task_id']),
            models.Index(fields=['start_date', 'finish_date']),
        ]
    
    
    def __str__(self):
        return f"Task {self.task_id}: {self.task_name}"


class CostItem(BaseModel):
    """
    Schema 1: Construction Planning and Costing
    Stores cost breakdown items with quantities and pricing.
    """
    document = models.ForeignKey(
        Document,
        on_delete=models.CASCADE,
        related_name='cost_items'
    )
    item_name = models.CharField(
        max_length=500,
        help_text="Description of the cost item"
    )
    quantity = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        help_text="Quantity of the item"
    )
    unit = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        help_text="Unit of measurement (e.g., t, m3, m2)"
    )
    unit_price_yen = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        help_text="Unit price in Japanese Yen"
    )
    total_cost_yen = models.DecimalField(
        max_digits=20,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        help_text="Total cost in Japanese Yen"
    )
    cost_type = models.CharField(
        max_length=50,
        choices=[
            ('foreign', 'Foreign Cost'),
            ('local', 'Local Cost'),
            ('other', 'Other'),
        ],
        help_text="Type of cost (foreign/local)"
    )
    category = models.CharField(
        max_length=200,
        null=True,
        blank=True,
        help_text="Cost category or section"
    )
    
    class Meta:
        db_table = 'cost_items'
        ordering = ['-total_cost_yen']
        indexes = [
            models.Index(fields=['cost_type']),
            models.Index(fields=['total_cost_yen']),
            models.Index(fields=['category']),
        ]
    
    def __str__(self):
        return f"{self.item_name}: ¥{self.total_cost_yen:,.2f}"


class RegulatoryRule(BaseModel):
    """
    Schema 1: URA Circular on GFA Area Definition (optional)
    Stores regulatory rules and clarifications.
    """
    document = models.ForeignKey(
        Document,
        on_delete=models.CASCADE,
        related_name='rules'
    )
    rule_id = models.CharField(
        max_length=50,
        help_text="Unique rule identifier (e.g., Q1, Q2)"
    )
    rule_summary = models.TextField(
        help_text="Concise summary of the rule"
    )
    measurement_basis = models.CharField(
        max_length=500,
        null=True,
        blank=True,
        help_text="Key measurement principle"
    )
    full_text = models.TextField(
        null=True,
        blank=True,
        help_text="Complete rule text"
    )
    
    class Meta:
        db_table = 'regulatory_rules'
        ordering = ['rule_id']
        indexes = [
            models.Index(fields=['rule_id']),
        ]
    
    def __str__(self):
        return f"Rule {self.rule_id}: {self.rule_summary[:50]}"


class DocumentChunk(BaseModel):
    """
    Schema 2: Stores document chunks for semantic search.
    Links PostgreSQL records to ChromaDB vectors.
    """
    document = models.ForeignKey(
        Document,
        on_delete=models.CASCADE,
        related_name='chunks'
    )
    chunk_id = models.CharField(
        max_length=100,
        unique=True,
        help_text="Unique identifier matching ChromaDB"
    )
    content = models.TextField(
        help_text="The text content of this chunk"
    )
    chunk_index = models.IntegerField(
        help_text="Position of chunk in document"
    )
    page_number = models.IntegerField(
        null=True,
        blank=True,
        help_text="Source page number if applicable"
    )
    metadata = models.JSONField(
        default=dict,
        help_text="Additional metadata stored as JSON"
    )
    
    class Meta:
        db_table = 'document_chunks'
        ordering = ['document', 'chunk_index']
        indexes = [
            models.Index(fields=['chunk_id']),
            models.Index(fields=['document', 'chunk_index']),
        ]
    
    def __str__(self):
        return f"Chunk {self.chunk_index} of {self.document.file_name}"


class PipelineRun(BaseModel):
    """Track pipeline execution history."""
    run_id = models.CharField(max_length=100, unique=True)
    status = models.CharField(
        max_length=50,
        choices=[
            ('started', 'Started'),
            ('running', 'Running'),
            ('completed', 'Completed'),
            ('failed', 'Failed'),
        ],
        default='started'
    )
    documents_processed = models.IntegerField(default=0)
    tasks_extracted = models.IntegerField(default=0)
    cost_items_extracted = models.IntegerField(default=0)
    chunks_created = models.IntegerField(default=0)
    started_at = models.DateTimeField(default=timezone.now)
    completed_at = models.DateTimeField(null=True, blank=True)
    error_log = models.TextField(null=True, blank=True)
    
    class Meta:
        db_table = 'pipeline_runs'
        ordering = ['-started_at']
    
    def __str__(self):
        return f"Pipeline Run {self.run_id} ({self.status})"
    
    @property
    def duration_seconds(self):
        if self.completed_at and self.started_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None