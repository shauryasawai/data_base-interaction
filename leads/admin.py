from django.contrib import admin
from .models import Lead, UploadHistory


@admin.register(Lead)
class LeadAdmin(admin.ModelAdmin):
    list_display = [
        'name',
        'email',
        'company',
        'role',
        'match_score',
        'created_at'
    ]
    list_filter = ['created_at', 'company']
    search_fields = ['name', 'email', 'skills', 'company']
    ordering = ['-created_at']


@admin.register(UploadHistory)
class UploadHistoryAdmin(admin.ModelAdmin):
    list_display = [
        'filename',
        'uploaded_at',
        'records_imported',
        'records_updated'
    ]
    list_filter = ['uploaded_at']
    ordering = ['-uploaded_at']
