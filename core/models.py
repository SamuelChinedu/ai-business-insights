from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver

class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    business_name = models.CharField(max_length=200, blank=True)

    def __str__(self):
        return f"{self.user.username} - {self.business_name or 'No business name'}"

class Analysis(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    business_type = models.CharField(max_length=100)
    data_summary = models.JSONField()
    raw_data_hash = models.CharField(max_length=100)
    uploaded_file = models.FileField(upload_to='user_uploads/%Y/%m/%d/', null=True, blank=True)
    title = models.CharField(max_length=200, blank=True, default="Untitled Analysis")

    def __str__(self):
        return f"{self.user.username} - {self.business_type} - {self.created_at.date()}"

# Auto-create profile when user registers
@receiver(post_save, sender=User)
def create_profile(sender, instance, created, **kwargs):
    if created:
        Profile.objects.create(user=instance)

@receiver(post_save, sender=User)
def save_profile(sender, instance, **kwargs):
    if hasattr(instance, 'profile'):
        instance.profile.save()