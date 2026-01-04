from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('login/', views.user_login, name='login'),
    path('register/', views.register, name='register'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('logout/', views.user_logout, name='logout'),  # add this view below
    path('ocr/', views.ocr_process, name='ocr_process'),
    path('analysis/<int:pk>/', views.analysis_detail, name='analysis_detail'),
    path('direct-upload/', views.direct_upload, name='direct_upload'),
    path('process-mapping/', views.process_with_mapping, name='process_with_mapping'),
    path('upload-file/', views.upload_file, name='upload_file'),
    path('analysis/<int:pk>/download-pdf/', views.download_analysis_pdf, name='download_analysis_pdf'),
    path('delete-analysis/<int:pk>/', views.delete_analysis, name='delete_analysis'),
]