from django import forms
from room.models import Room

class RoomForm(forms.ModelForm):
    class Meta:
        model = Room
        fields = ['name','cover_image']