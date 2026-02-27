from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('upload/', views.upload_leads, name='upload_leads'),
    path('search/', views.search_leads, name='search_leads'),
    path('ai-lead-generation/', views.ai_lead_generation, name='ai_lead_generation'),
    path('prompt-builder/', views.prompt_builder, name='prompt_builder'),
    path('lead/<int:pk>/', views.lead_detail, name='lead_detail'),
    path('lead/<int:pk>/delete/', views.delete_lead, name='delete_lead'),
    path('export/', views.export_leads, name='export_leads'),
    path('all-leads/', views.all_leads, name='all_leads'),
    path('clear-chat/<int:pk>/', views.clear_chat_history, name='clear_chat_history'),
]