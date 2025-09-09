from django import forms

class JoinRoomForm(forms.Form):
    code = forms.CharField(label='รหัสเชิญ', max_length=6)