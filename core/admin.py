from django.contrib import admin
from django.contrib.auth.models import User
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.http import HttpResponse
import csv
from .models import Analysis, Profile

# Fix User admin to show email and business name
admin.site.unregister(User)

@admin.register(User)
class CustomUserAdmin(BaseUserAdmin):
    list_display = ('username', 'email', 'business_name', 'date_joined', 'last_login')
    list_filter = ('date_joined', 'last_login')
    search_fields = ('username', 'email', 'profile__business_name')
    ordering = ('-date_joined',)

    def business_name(self, obj):
        try:
            return obj.profile.business_name
        except:
            return "No business name"
    business_name.short_description = "Business Name"

@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'business_name')
    search_fields = ('user__username', 'business_name')

@admin.register(Analysis)
class AnalysisAdmin(admin.ModelAdmin):
    list_display = ('user', 'business_type', 'created_at', 'total_revenue', 'growth', 'download_file')
    list_filter = ('business_type', 'created_at')
    search_fields = ('user__username', 'business_type')
    readonly_fields = ('created_at', 'data_summary', 'raw_data_hash')
    date_hierarchy = 'created_at'

    def total_revenue(self, obj):
        return f"₦{obj.data_summary.get('total_revenue', 0):,.0f}" if obj.data_summary else "N/A"
    total_revenue.short_description = "Total Revenue"

    def growth(self, obj):
        g = obj.data_summary.get('growth', 0) if obj.data_summary else 0
        return f"{g:+.1f}%"
    growth.short_description = "Growth"

    def download_file(self, obj):
        if obj.uploaded_file:
            return f'<a href="{obj.uploaded_file.url}" class="btn btn-success btn-sm">Download File</a>'
        return "No file"
    download_file.short_description = "Original File"
    download_file.allow_tags = True