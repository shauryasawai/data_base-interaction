from django.db import models
from django.contrib.postgres.fields import ArrayField

class Lead(models.Model):
    name = models.CharField(max_length=200)
    email = models.EmailField(unique=True, blank=True, null=True)
    phone = models.CharField(max_length=20, blank=True)
    role = models.CharField(max_length=200, blank=True, help_text="Job role/position")
    company = models.CharField(max_length=200, blank=True)
    linkedin_url = models.URLField(max_length=500, blank=True, help_text="LinkedIn profile URL")
    location = models.CharField(max_length=200, blank=True)
    skills = models.TextField(blank=True, help_text="Comma-separated skills")
    experience_years = models.IntegerField(default=0)
    notes = models.TextField(blank=True)
    match_score = models.FloatField(default=0.0)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-match_score', '-created_at']

    def __str__(self):
        return f"{self.name} - {self.role} at {self.company}"

    def get_skills_list(self):
        """Return skills as a list"""
        if not self.skills:
            return []
        return [skill.strip() for skill in self.skills.split(',') if skill.strip()]

    def calculate_match_score(self, required_skills):
        """Calculate match percentage based on required skills"""
        lead_skills = set(skill.lower().strip() for skill in self.get_skills_list())
        required = set(skill.lower().strip() for skill in required_skills)
        
        if not required:
            return 0.0
        
        matched = lead_skills.intersection(required)
        score = (len(matched) / len(required)) * 100
        return round(score, 2)


class UploadHistory(models.Model):
    filename = models.CharField(max_length=255)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    records_imported = models.IntegerField(default=0)
    records_updated = models.IntegerField(default=0)
    
    class Meta:
        ordering = ['-uploaded_at']
        verbose_name_plural = "Upload Histories"

    def __str__(self):
        return f"{self.filename} - {self.uploaded_at.strftime('%Y-%m-%d %H:%M')}"